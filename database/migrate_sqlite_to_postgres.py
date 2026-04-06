"""Migração de dados SQLite → PostgreSQL (preserva IDs, tenant_id, valores; idempotente).

Fluxo limpo (PostgreSQL vazio + ``schema.sql`` + dados)::

    python -m database.migrate_sqlite_to_postgres --full-reset --sqlite C:/abs/path/business.db

Cada tabela: ``COUNT(*)`` completo, depois ``SELECT * FROM table`` e ``fetchall()`` — sem
``WHERE`` / ``LIMIT`` / ``OFFSET`` nos dados. Logs: ``SQLite rows found: N`` antes e
``Inserted: N`` após os ``INSERT``. Idempotência: ``ON CONFLICT DO NOTHING`` (inalterado).

Não altera schema nem lógica de negócio. Requer ``schema.sql`` já aplicado no destino.

Uso típico::

    python -m database.migrate_sqlite_to_postgres --sqlite C:/caminho/absoluto/business.db

Variáveis: ``DATABASE_URL`` / cadeia DSN habitual para Postgres; ``.env`` na raiz carregado
automaticamente. ``--sqlite`` e ``ALIEH_MIGRATE_SQLITE`` devem ser **caminhos absolutos**;
o defeito ``sqlite_db_path()`` é resolvido para absoluto na raiz do projecto.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env", override=False)

from database.config import sqlite_db_path
from database.connection import get_postgres_conn

_logger = logging.getLogger(__name__)


def _resolve_sqlite_file_for_migration(
    sqlite_path: Path | None,
) -> tuple[Path, str]:
    """
    Devolve ``(caminho absoluto resolvido, texto do input para diagnóstico)``.

    Recusa caminhos **relativos** em ``--sqlite`` e ``ALIEH_MIGRATE_SQLITE`` para evitar
    ficheiros errados conforme o CWD. O defeito ``sqlite_db_path()`` é normalizado para absoluto.
    """
    if sqlite_path is not None:
        raw = Path(sqlite_path).expanduser()
        label = str(sqlite_path)
        if not raw.is_absolute():
            raise ValueError(
                "O caminho SQLite (--sqlite) tem de ser absoluto; caminhos relativos são "
                f"recusados (recebido: {label!r})."
            )
        return raw.resolve(), label
    env_path = (os.environ.get("ALIEH_MIGRATE_SQLITE") or "").strip()
    if env_path:
        raw = Path(env_path).expanduser()
        if not raw.is_absolute():
            raise ValueError(
                "ALIEH_MIGRATE_SQLITE tem de ser um caminho absoluto "
                f"(recebido: {env_path!r})."
            )
        return raw.resolve(), env_path
    raw = Path(sqlite_db_path()).expanduser().resolve()
    return raw, str(raw)


def _log_sqlite_file_identity(resolved: Path, input_label: str) -> None:
    """Caminho recebido vs absoluto e tamanho (MB); também ``print`` para visibilidade imediata."""
    resolved_s = str(resolved)
    print(f"sqlite_path: {input_label}")
    print(f"Path(sqlite_path).resolve(): {resolved_s}")
    _logger.info("sqlite_path %s", input_label)
    _logger.info("Path(sqlite_path).resolve() %s", resolved_s)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"Ficheiro SQLite inexistente ou não é ficheiro: {resolved_s}"
        )
    size_mb = resolved.stat().st_size / (1024 * 1024)
    _logger.info("SQLite file size: %.2f MB", size_mb)


# Ordem respeitando FKs do schema Postgres (schema.sql).
# Núcleo: customers → products → sku_master → tabelas dependentes de SKU → stock → sales.
_MIGRATION_TABLE_ORDER: tuple[str, ...] = (
    "app_schema_migrations",
    "users",
    "customers",
    "sku_sequence_counter",
    "customer_sequence_counter",
    "sale_sequence_counter",
    "products",
    "sku_master",
    "price_history",
    "sku_cost_components",
    "sku_pricing_records",
    "stock_cost_entries",
    "sales",
    "sku_deletion_audit",
    "login_user_throttle",
    "login_attempt_audit",
    "uat_manual_checklist",
)

# Cláusula ON CONFLICT (deve coincidir com PK ou UNIQUE deferível no Postgres).
_CONFLICT_TARGET: dict[str, str] = {
    "app_schema_migrations": "(id)",
    "users": "(id)",
    "customers": "(id)",
    "sku_sequence_counter": "(tenant_id, id)",
    "customer_sequence_counter": "(tenant_id, id)",
    "sale_sequence_counter": "(tenant_id, id)",
    "sku_master": "(tenant_id, sku)",
    "products": "(id)",
    "price_history": "(id)",
    "sku_cost_components": "(tenant_id, sku, component_key)",
    "sku_pricing_records": "(id)",
    "stock_cost_entries": "(id)",
    "sales": "(id)",
    "sku_deletion_audit": "(id)",
    "login_user_throttle": "(tenant_id, username_norm)",
    "login_attempt_audit": "(id)",
    "uat_manual_checklist": "(id)",
}

_RETURNING_EXPR: dict[str, str] = {
    "app_schema_migrations": "id",
    "users": "id",
    "customers": "id",
    "sku_sequence_counter": "tenant_id, id",
    "customer_sequence_counter": "tenant_id, id",
    "sale_sequence_counter": "tenant_id, id",
    "sku_master": "tenant_id, sku",
    "products": "id",
    "price_history": "id",
    "sku_cost_components": "tenant_id, sku, component_key",
    "sku_pricing_records": "id",
    "stock_cost_entries": "id",
    "sales": "id",
    "sku_deletion_audit": "id",
    "login_user_throttle": "tenant_id, username_norm",
    "login_attempt_audit": "id",
    "uat_manual_checklist": "id",
}

_SEQUENCES_TO_SYNC: tuple[tuple[str, str], ...] = (
    ("users", "id"),
    ("customers", "id"),
    ("products", "id"),
    ("price_history", "id"),
    ("sku_pricing_records", "id"),
    ("stock_cost_entries", "id"),
    ("sales", "id"),
    ("sku_deletion_audit", "id"),
    ("login_attempt_audit", "id"),
    ("uat_manual_checklist", "id"),
)


@dataclass
class TableMigrationStats:
    table: str
    source_rows: int = 0
    inserted: int = 0
    skipped: int = 0


@dataclass
class MigrationSummary:
    tables: list[TableMigrationStats] = field(default_factory=list)
    sqlite_path: str = ""
    ok: bool = True


def _open_sqlite(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=120.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF;")  # cópia bruta; FK validadas no destino
    return conn


def _sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;",
        (table,),
    ).fetchone()
    return row is not None


def _log_sqlite_preflight_product_sales_counts(conn: sqlite3.Connection) -> None:
    """Antes da migração: contagens de referência em ``products`` e ``sales``."""
    for tbl in ("products", "sales"):
        if not _sqlite_table_exists(conn, tbl):
            _logger.warning("SQLite preflight: tabela %s não existe (COUNT omitido)", tbl)
            continue
        row = conn.execute(f"SELECT COUNT(*) AS c FROM {tbl};").fetchone()
        n = int(row[0]) if row is not None else 0
        _logger.info("SQLite preflight SELECT COUNT(*) FROM %s: %d", tbl, n)


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    return [str(r[1]) for r in rows]


def _pg_table_exists(pg_conn: Any, table: str) -> bool:
    cur = pg_conn.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        LIMIT 1;
        """,
        (table.lower(),),
    )
    return cur.fetchone() is not None


def _pg_columns(pg_conn: Any, table: str) -> set[str]:
    cur = pg_conn.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s;
        """,
        (table.lower(),),
    )
    return {str(r["column_name"]) for r in cur.fetchall()}


def _normalize_row(row: sqlite3.Row, colnames: Sequence[str]) -> tuple[Any, ...]:
    """Converte valor SQLite para tipos aceites pelo psycopg (NUMERIC, texto, int)."""
    out: list[Any] = []
    for c in colnames:
        v = row[c]
        if v is None:
            out.append(None)
        elif isinstance(v, memoryview):
            out.append(bytes(v))
        elif isinstance(v, (bytes, bytearray)):
            out.append(bytes(v))
        else:
            out.append(v)
    return tuple(out)


def _migrate_one_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn: Any,
    table: str,
) -> TableMigrationStats:
    stats = TableMigrationStats(table=table)
    if table not in _CONFLICT_TARGET or table not in _RETURNING_EXPR:
        _logger.warning("Migrating table: %s — ignorada (sem metadados ON CONFLICT)", table)
        return stats

    if not _sqlite_table_exists(sqlite_conn, table):
        _logger.info("Migrating table: %s — omitida (não existe no SQLite)", table)
        return stats

    if not _pg_table_exists(pg_conn, table):
        _logger.warning("Migrating table: %s — omitida (não existe em public no Postgres)", table)
        return stats

    lc_set = _pg_columns(pg_conn, table)
    # Mesma ordem física do PRAGMA table_info (= ordem de SELECT * no SQLite).
    s_cols = [c for c in _sqlite_columns(sqlite_conn, table) if c.lower() in lc_set]
    if not s_cols:
        _logger.warning("Migrating table: %s — sem colunas comuns SQLite/Postgres", table)
        return stats

    col_list = ", ".join(c.lower() for c in s_cols)
    placeholders = ", ".join("%s" for _ in s_cols)
    conflict = _CONFLICT_TARGET[table]
    ret = _RETURNING_EXPR[table]

    sql = (
        f"INSERT INTO {table.lower()} ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT {conflict} DO NOTHING RETURNING {ret}"
    )

    _logger.info("Migrating table: %s", table)
    count_row = sqlite_conn.execute(f"SELECT COUNT(*) AS c FROM {table};").fetchone()
    n_sqlite = int(count_row[0]) if count_row is not None else 0
    _logger.info("SQLite rows found: %d", n_sqlite)

    # Leitura integral sem filtros (nenhum WHERE / LIMIT / OFFSET).
    rows = sqlite_conn.execute(f"SELECT * FROM {table};").fetchall()
    if len(rows) != n_sqlite:
        _logger.error(
            "SQLite read mismatch for %s: COUNT(*)=%d but fetchall() returned %d rows",
            table,
            n_sqlite,
            len(rows),
        )
        raise RuntimeError(
            f"Incomplete SQLite read for {table}: count {n_sqlite} != fetched {len(rows)}"
        )

    stats.source_rows = n_sqlite
    inserted = 0
    skipped = 0

    for row in rows:
        vals = _normalize_row(row, s_cols)
        cur = pg_conn.execute(sql, vals)
        if cur.fetchone() is not None:
            inserted += 1
        else:
            skipped += 1

    stats.inserted = inserted
    stats.skipped = skipped
    _logger.info("Inserted: %d", inserted)
    if skipped:
        _logger.info("Skipped (already in Postgres, ON CONFLICT DO NOTHING): %d", skipped)
    if inserted + skipped != n_sqlite:
        _logger.error(
            "Postgres row accounting mismatch for %s: inserted+skipped=%d, SQLite rows=%d",
            table,
            inserted + skipped,
            n_sqlite,
        )
        raise RuntimeError(
            f"Migration accounting failed for {table}: {inserted}+{skipped} != {n_sqlite}"
        )
    return stats


def _sync_serial_sequences(pg_conn: Any) -> None:
    """Alinha nextval com MAX(id) após INSERT explícitos de chaves (evita colisão futura)."""
    from psycopg import sql

    for tbl, col in _SEQUENCES_TO_SYNC:
        try:
            qseq = pg_conn.execute(
                sql.SQL("SELECT pg_get_serial_sequence({t}, {c}) AS s").format(
                    t=sql.Literal(tbl),
                    c=sql.Literal(col),
                )
            ).fetchone()
            seq_name = qseq["s"] if qseq else None
            if not seq_name:
                continue
            qmax = pg_conn.execute(
                sql.SQL("SELECT MAX({c}) AS m FROM {t}").format(
                    c=sql.Identifier(col),
                    t=sql.Identifier(tbl),
                )
            ).fetchone()
            m = qmax["m"]
            if m is not None and int(m) > 0:
                pg_conn.execute(
                    "SELECT setval(%s, %s, true);",
                    (seq_name, int(m)),
                )
            else:
                pg_conn.execute(
                    "SELECT setval(%s, 1, false);",
                    (seq_name,),
                )
        except Exception as exc:
            _logger.debug(
                "Sequence sync skipped for %s.%s: %s",
                tbl,
                col,
                type(exc).__name__,
            )


def migrate_all_data(
    *,
    sqlite_path: Path | None = None,
    sync_sequences: bool = True,
) -> MigrationSummary:
    """
    Copia dados do SQLite para Postgres, uma transacção por tabela (rollback em erro).

    Idempotência: ``ON CONFLICT DO NOTHING`` sobre a chave primária (ou UNIQUE composto
    equivalente ao PK em uso).
    """
    path, path_label = _resolve_sqlite_file_for_migration(sqlite_path)
    _log_sqlite_file_identity(path, path_label)

    summary = MigrationSummary(sqlite_path=str(path))
    sl_conn = _open_sqlite(path)
    _log_sqlite_preflight_product_sales_counts(sl_conn)

    try:
        with get_postgres_conn() as pg_conn:
            for table in _MIGRATION_TABLE_ORDER:
                try:
                    with pg_conn.transaction():
                        st = _migrate_one_table(sl_conn, pg_conn, table)
                        summary.tables.append(st)
                except Exception:
                    summary.ok = False
                    _logger.exception(
                        "Migração falhou na tabela %s — rollback da transacção desta tabela.",
                        table,
                    )
                    raise

            if sync_sequences and summary.ok:
                try:
                    with pg_conn.transaction():
                        _sync_serial_sequences(pg_conn)
                        _logger.info("Postgres serial sequences sincronizadas (MAX(id)).")
                except Exception:
                    _logger.warning(
                        "Aviso: sincronização de sequências falhou; verifique setval manualmente.",
                        exc_info=True,
                    )
    finally:
        sl_conn.close()

    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Migrar dados SQLite → PostgreSQL.")
    p.add_argument(
        "--sqlite",
        type=Path,
        default=None,
        help="Caminho absoluto do .db origem (relativos recusados; defeito: ALIEH_MIGRATE_SQLITE absoluto ou sqlite_db_path())",
    )
    p.add_argument(
        "--no-sync-sequences",
        action="store_true",
        help="Não ajustar sequências BIGSERIAL após a carga.",
    )
    p.add_argument(
        "--full-reset",
        action="store_true",
        help="Esvaziar public (CASCADE), reaplicar schema.sql (schema_apply) e migrar dados.",
    )
    args = p.parse_args()
    if args.full_reset:
        from database.schema_apply import apply_schema_to_postgres, reset_postgres_schema

        reset_postgres_schema()
        apply_schema_to_postgres()
    migrate_all_data(sqlite_path=args.sqlite, sync_sequences=not args.no_sync_sequences)
    _logger.info("Migração concluída.")


if __name__ == "__main__":
    main()
