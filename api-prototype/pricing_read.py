"""Read-only pricing / sku_master helpers for api-prototype."""

from __future__ import annotations

from database.repositories.support import use_connection
from database.sql_compat import db_execute
from database.tenancy import effective_tenant_id_for_request


def fetch_sku_master_one(sku: str, *, tenant_id: str | None = None):
    tid = effective_tenant_id_for_request(tenant_id)
    s = (sku or "").strip()
    with use_connection(None) as conn:
        return db_execute(
            conn,
            """
            SELECT sku, total_stock, avg_unit_cost, selling_price, structured_cost_total, updated_at
            FROM sku_master
            WHERE tenant_id = %s AND TRIM(COALESCE(sku, '')) = %s AND deleted_at IS NULL;
            """,
            (tid, s),
        ).fetchone()
