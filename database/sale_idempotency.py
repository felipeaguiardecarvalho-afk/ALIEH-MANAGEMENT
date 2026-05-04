"""Tabela opcional de idempotência para gravação de vendas (retries seguros).

CREATE IF NOT EXISTS — não altera regras de negócio; apenas metadados de deduplicação.
Inclui ``expires_at`` (TTL configurável) e limpeza segura de registos expirados.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

_logger = logging.getLogger(__name__)

_TABLE_READY = False

_DDL_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS sale_idempotency_records (
        id BIGSERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        sale_code TEXT NOT NULL,
        final_total DOUBLE PRECISION NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_sale_idempotency_tenant_key
    ON sale_idempotency_records (tenant_id, idempotency_key)
    """,
)


def _ttl_hours() -> int:
    try:
        return min(max(int((os.environ.get("SALE_IDEMPOTENCY_TTL_HOURS") or "24").strip()), 1), 168)
    except ValueError:
        return 24


def _expires_at_utc() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=_ttl_hours())


def _column_exists_sqlite(conn, table: str, column: str) -> bool:
    from database.sql_compat import db_execute

    cur = db_execute(conn, f"PRAGMA table_info({table})", ())
    for row in cur.fetchall() or []:
        if hasattr(row, "keys"):
            if str(row.get("name") or "") == column:
                return True
        elif len(row) > 1 and str(row[1]) == column:
            return True
    return False


def _column_exists_postgres(conn, table: str, column: str) -> bool:
    from database.sql_compat import db_execute

    cur = db_execute(
        conn,
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        LIMIT 1;
        """,
        (table, column),
    )
    return cur.fetchone() is not None


def _ensure_expires_column(conn) -> None:
    from database.sql_compat import db_execute, is_sqlite_conn

    if is_sqlite_conn(conn):
        if not _column_exists_sqlite(conn, "sale_idempotency_records", "expires_at"):
            db_execute(conn, "ALTER TABLE sale_idempotency_records ADD COLUMN expires_at TEXT", ())
    else:
        if not _column_exists_postgres(conn, "sale_idempotency_records", "expires_at"):
            db_execute(
                conn,
                "ALTER TABLE sale_idempotency_records ADD COLUMN expires_at TIMESTAMPTZ",
                (),
            )


def _ensure_indexes(conn) -> None:
    from database.sql_compat import db_execute, is_sqlite_conn

    if is_sqlite_conn(conn):
        db_execute(
            conn,
            """
            CREATE INDEX IF NOT EXISTS idx_sale_idempotency_expires
            ON sale_idempotency_records (expires_at)
            """,
            (),
        )
        return
    db_execute(
        conn,
        """
        CREATE INDEX IF NOT EXISTS idx_sale_idempotency_expires
        ON sale_idempotency_records (expires_at)
        WHERE expires_at IS NOT NULL
        """,
        (),
    )


def _backfill_expires(conn) -> None:
    from database.sql_compat import db_execute, is_sqlite_conn

    h = _ttl_hours()
    if is_sqlite_conn(conn):
        db_execute(
            conn,
            """
            UPDATE sale_idempotency_records
            SET expires_at = datetime(created_at, '+' || ? || ' hours')
            WHERE expires_at IS NULL
            """,
            (str(h),),
        )
        return
    db_execute(
        conn,
        """
        UPDATE sale_idempotency_records
        SET expires_at = created_at + make_interval(hours => %s::int)
        WHERE expires_at IS NULL
        """,
        (h,),
    )


def ensure_sale_idempotency_table() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    from database.repositories.support import use_connection
    from database.sql_compat import db_execute, is_sqlite_conn

    try:
        with use_connection(None) as conn:
            for stmt in _DDL_STATEMENTS:
                sql = stmt.strip()
                if is_sqlite_conn(conn):
                    sql = (
                        sql.replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
                        .replace("BIGSERIAL", "INTEGER")
                        .replace(
                            "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
                            "TEXT NOT NULL DEFAULT (datetime('now'))",
                        )
                    )
                db_execute(conn, sql, ())
            _ensure_expires_column(conn)
            _ensure_indexes(conn)
            _backfill_expires(conn)
        _TABLE_READY = True
    except Exception:
        _logger.exception("sale_idempotency_records: ensure table failed")
        raise


def compute_sale_record_request_hash(
    *,
    product_id: int,
    quantity: int,
    customer_id: int,
    discount_amount: float,
    payment_method: str,
) -> str:
    """Hash estável do corpo lógico (2 casas no desconto)."""
    payload = {
        "customer_id": int(customer_id),
        "discount_amount": round(float(discount_amount) + 1e-12, 2),
        "payment_method": (payment_method or "").strip(),
        "product_id": int(product_id),
        "quantity": int(quantity),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _row_expired(expires_at: Any) -> bool:
    if expires_at is None:
        return False
    now = datetime.now(timezone.utc)
    if isinstance(expires_at, datetime):
        dt = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        return dt <= now
    try:
        s = str(expires_at).strip()
        if not s:
            return False
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt <= now
    except Exception:
        return False


def fetch_idempotency_row(
    conn,
    *,
    tenant_id: str,
    idempotency_key: str,
) -> Optional[dict[str, Any]]:
    from database.sql_compat import db_execute, is_sqlite_conn

    tid = (tenant_id or "").strip() or "default"
    key = (idempotency_key or "").strip()
    if not key:
        return None
    if is_sqlite_conn(conn):
        cur = db_execute(
            conn,
            """
            SELECT request_hash, sale_code, final_total, expires_at
            FROM sale_idempotency_records
            WHERE tenant_id = %s AND idempotency_key = %s
            """,
            (tid, key),
        )
    else:
        cur = db_execute(
            conn,
            """
            SELECT request_hash, sale_code, final_total, expires_at
            FROM sale_idempotency_records
            WHERE tenant_id = %s AND idempotency_key = %s
              AND (expires_at IS NULL OR expires_at > NOW())
            """,
            (tid, key),
        )
    row = cur.fetchone()
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {
        "request_hash": row[0],
        "sale_code": row[1],
        "final_total": row[2],
        "expires_at": row[3] if len(row) > 3 else None,
    }
    if is_sqlite_conn(conn) and _row_expired(d.get("expires_at")):
        return None
    return {
        "request_hash": d.get("request_hash"),
        "sale_code": d.get("sale_code"),
        "final_total": d.get("final_total"),
    }


def acquire_idempotency_transaction_lock(conn, *, tenant_id: str, idempotency_key: str) -> None:
    """Serializa o mesmo par tenant+chave entre transacções (PostgreSQL apenas)."""
    from database.sql_compat import db_execute, is_sqlite_conn

    if is_sqlite_conn(conn):
        return
    import hashlib as _hl

    raw = _hl.sha256(f"{tenant_id!s}:{idempotency_key}".encode()).digest()[:8]
    k = int.from_bytes(raw, "big", signed=False) % (2**62)
    db_execute(conn, "SELECT pg_advisory_xact_lock(%s);", (k,))


def insert_idempotency_row(
    conn,
    *,
    tenant_id: str,
    idempotency_key: str,
    request_hash: str,
    sale_code: str,
    final_total: float,
) -> None:
    from database.sql_compat import db_execute, is_sqlite_conn

    tid = (tenant_id or "").strip() or "default"
    exp = _expires_at_utc()
    if is_sqlite_conn(conn):
        exp_s = exp.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        db_execute(
            conn,
            """
            INSERT INTO sale_idempotency_records
                (tenant_id, idempotency_key, request_hash, sale_code, final_total, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (tid, idempotency_key.strip(), request_hash, sale_code, float(final_total), exp_s),
        )
        return
    db_execute(
        conn,
        """
        INSERT INTO sale_idempotency_records
            (tenant_id, idempotency_key, request_hash, sale_code, final_total, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (tid, idempotency_key.strip(), request_hash, sale_code, float(final_total), exp),
    )


def purge_expired_idempotency_rows() -> int:
    """Remove apenas linhas com ``expires_at`` no passado (não toca em linhas sem TTL)."""
    from database.repositories.support import use_connection
    from database.sql_compat import db_execute, is_sqlite_conn

    deleted = 0
    try:
        with use_connection(None) as conn:
            if is_sqlite_conn(conn):
                cur = db_execute(
                    conn,
                    "SELECT id, expires_at FROM sale_idempotency_records WHERE expires_at IS NOT NULL",
                    (),
                )
                ids = []
                for row in cur.fetchall() or []:
                    rid = row["id"] if hasattr(row, "keys") else row[0]
                    exp = row["expires_at"] if hasattr(row, "keys") else row[1]
                    if _row_expired(exp):
                        ids.append(int(rid))
                for rid in ids:
                    c2 = db_execute(
                        conn,
                        "DELETE FROM sale_idempotency_records WHERE id = %s",
                        (rid,),
                    )
                    deleted += int(getattr(c2, "rowcount", 0) or 0)
            else:
                cur = db_execute(
                    conn,
                    """
                    DELETE FROM sale_idempotency_records
                    WHERE expires_at IS NOT NULL AND expires_at < NOW()
                    """,
                    (),
                )
                deleted = int(getattr(cur, "rowcount", 0) or 0)
    except Exception:
        _logger.exception("purge_expired_idempotency_rows failed")
    return deleted
