"""Linhas de composição de custo por SKU."""

from __future__ import annotations

from datetime import datetime

from database.config import get_db_provider
from database.connection import DbConnection
from database.constants import SKU_COST_COMPONENT_DEFINITIONS
from database.sql_compat import db_execute
from database.tenancy import effective_tenant_id_for_request


def ensure_sku_cost_component_rows(
    conn: DbConnection,
    sku: str,
    tenant_id: str | None = None,
) -> None:
    if not sku or not str(sku).strip():
        return
    sku = sku.strip()
    tid = effective_tenant_id_for_request(tenant_id)
    now = datetime.now().isoformat(timespec="seconds")
    for key, label in SKU_COST_COMPONENT_DEFINITIONS:
        if get_db_provider() == "sqlite":
            db_execute(
                conn,
                """
                INSERT OR IGNORE INTO sku_cost_components (
                    tenant_id, sku, component_key, label, unit_price, quantity, line_total, updated_at
                ) VALUES (?, ?, ?, ?, 0, 0, 0, ?);
                """,
                (tid, sku, key, label, now),
            )
        else:
            db_execute(
                conn,
                """
                INSERT INTO sku_cost_components (
                    tenant_id, sku, component_key, label, unit_price, quantity, line_total, updated_at
                ) VALUES (?, ?, ?, ?, 0, 0, 0, ?)
                ON CONFLICT (tenant_id, sku, component_key) DO NOTHING;
                """,
                (tid, sku, key, label, now),
            )
        db_execute(
            conn,
            """
            UPDATE sku_cost_components SET label = ?
            WHERE tenant_id = ? AND sku = ? AND component_key = ?;
            """,
            (label, tid, sku, key),
        )


def update_sku_cost_component_line(
    conn: DbConnection,
    sku: str,
    component_key: str,
    unit_price: float,
    quantity: float,
    line_total: float,
    now: str,
    tenant_id: str | None = None,
) -> None:
    tid = effective_tenant_id_for_request(tenant_id)
    db_execute(
        conn,
        """
        UPDATE sku_cost_components
        SET unit_price = ?, quantity = ?, line_total = ?, updated_at = ?
        WHERE tenant_id = ? AND sku = ? AND component_key = ?;
        """,
        (unit_price, quantity, line_total, now, tid, sku, component_key),
    )


def recompute_sku_structured_cost_total(
    conn: DbConnection,
    sku: str,
    tenant_id: str | None = None,
) -> float:
    sku = sku.strip()
    tid = effective_tenant_id_for_request(tenant_id)
    row = db_execute(
        conn,
        """
        SELECT COALESCE(SUM(line_total), 0) AS t
        FROM sku_cost_components
        WHERE tenant_id = ? AND sku = ?;
        """,
        (tid, sku),
    ).fetchone()
    total = float(row["t"] or 0.0)
    now = datetime.now().isoformat(timespec="seconds")
    db_execute(
        conn,
        """
        UPDATE sku_master
        SET structured_cost_total = ?, updated_at = ?
        WHERE tenant_id = ? AND sku = ?;
        """,
        (total, now, tid, sku),
    )
    return total
