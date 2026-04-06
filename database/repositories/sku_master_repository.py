"""Mestre de SKU: existência e total de estoque por SKU."""

from __future__ import annotations

from datetime import datetime
from database.connection import DbConnection

from database.config import get_db_provider
from database.sql_compat import db_execute
from database.tenancy import DEFAULT_TENANT_ID, effective_tenant_id_for_request


def ensure_sku_master(
    conn: DbConnection,
    sku: str,
    tenant_id: str | None = None,
) -> None:
    if not sku or not str(sku).strip():
        raise ValueError("SKU é obrigatório para custeio de estoque.")
    sku = sku.strip()
    tid = effective_tenant_id_for_request(tenant_id)
    now = datetime.now().isoformat(timespec="seconds")
    if get_db_provider() == "sqlite":
        db_execute(
            conn,
            """
            INSERT OR IGNORE INTO sku_master (
                tenant_id, sku, total_stock, avg_unit_cost, selling_price, updated_at, deleted_at
            )
            VALUES (?, ?, 0, 0, 0, ?, NULL);
            """,
            (tid, sku, now),
        )
    else:
        db_execute(
            conn,
            """
            INSERT INTO sku_master (
                tenant_id, sku, total_stock, avg_unit_cost, selling_price, updated_at, deleted_at
            )
            VALUES (?, ?, 0, 0, 0, ?, NULL)
            ON CONFLICT (tenant_id, sku) DO NOTHING;
            """,
            (tid, sku, now),
        )


def sync_sku_master_totals(
    conn: DbConnection,
    sku: str,
    tenant_id: str | None = None,
) -> None:
    if not sku or not str(sku).strip():
        return
    sku = sku.strip()
    tid = effective_tenant_id_for_request(tenant_id)
    exists = db_execute(
        conn,
        "SELECT 1 FROM sku_master WHERE tenant_id = ? AND sku = ?;",
        (tid, sku),
    ).fetchone()
    if exists is None:
        ensure_sku_master(conn, sku, tenant_id=tid)
    total = float(
        db_execute(
            conn,
            """
            SELECT COALESCE(SUM(stock), 0) FROM products
            WHERE tenant_id = ? AND sku = ? AND deleted_at IS NULL;
            """,
            (tid, sku),
        ).fetchone()[0]
    )
    now = datetime.now().isoformat(timespec="seconds")
    db_execute(
        conn,
        """
        UPDATE sku_master SET total_stock = ?, updated_at = ?
        WHERE tenant_id = ? AND sku = ?;
        """,
        (total, now, tid, sku),
    )
