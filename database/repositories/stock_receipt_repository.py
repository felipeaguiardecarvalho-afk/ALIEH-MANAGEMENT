"""Entradas de stock custeadas (receipt) — operações de persistência."""

from __future__ import annotations

from database.connection import DbConnection

from database.sql_compat import db_execute
from database.tenancy import effective_tenant_id_for_request


def fetch_product_batch_row(
    conn: DbConnection,
    product_id: int,
    tenant_id: str | None = None,
):
    tid = effective_tenant_id_for_request(tenant_id)
    return db_execute(conn,
        "SELECT id, sku, deleted_at FROM products WHERE tenant_id = ? AND id = ?;",
        (tid, int(product_id)),
    ).fetchone()


def fetch_sku_master_deleted_flag(
    conn: DbConnection,
    sku: str,
    tenant_id: str | None = None,
):
    tid = effective_tenant_id_for_request(tenant_id)
    return db_execute(conn,
        "SELECT deleted_at FROM sku_master WHERE tenant_id = ? AND sku = ?;",
        (tid, sku),
    ).fetchone()


def sum_active_stock_by_sku(
    conn: DbConnection,
    sku: str,
    tenant_id: str | None = None,
) -> float:
    tid = effective_tenant_id_for_request(tenant_id)
    return float(
        db_execute(conn,
            """
            SELECT COALESCE(SUM(stock), 0) FROM products
            WHERE tenant_id = ? AND sku = ? AND deleted_at IS NULL;
            """,
            (tid, sku),
        ).fetchone()[0]
    )


def fetch_sku_master_avg_unit_cost_row(
    conn: DbConnection,
    sku: str,
    tenant_id: str | None = None,
):
    tid = effective_tenant_id_for_request(tenant_id)
    return db_execute(conn,
        "SELECT avg_unit_cost FROM sku_master WHERE tenant_id = ? AND sku = ?;",
        (tid, sku),
    ).fetchone()


def insert_stock_cost_entry(
    conn: DbConnection,
    *,
    sku: str,
    product_id: int,
    qty: float,
    unit_cost: float,
    total_entry_cost: float,
    prev_total: float,
    new_total: float,
    prev_avg: float,
    new_avg: float,
    now: str,
    tenant_id: str | None = None,
) -> None:
    tid = effective_tenant_id_for_request(tenant_id)
    db_execute(conn,
        """
        INSERT INTO stock_cost_entries (
            tenant_id, sku, product_id, quantity, unit_cost, total_entry_cost,
            stock_before, stock_after, avg_cost_before, avg_cost_after, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            tid,
            sku,
            int(product_id),
            qty,
            float(unit_cost),
            total_entry_cost,
            prev_total,
            new_total,
            prev_avg,
            new_avg,
            now,
        ),
    )


def add_stock_to_product_row(
    conn: DbConnection,
    product_id: int,
    qty: float,
    tenant_id: str | None = None,
) -> None:
    tid = effective_tenant_id_for_request(tenant_id)
    db_execute(conn,
        "UPDATE products SET stock = stock + ? WHERE tenant_id = ? AND id = ?;",
        (qty, tid, int(product_id)),
    )


def set_products_cost_by_sku(
    conn: DbConnection,
    sku: str,
    new_avg: float,
    tenant_id: str | None = None,
) -> None:
    tid = effective_tenant_id_for_request(tenant_id)
    db_execute(conn,
        "UPDATE products SET cost = ? WHERE tenant_id = ? AND sku = ?;",
        (new_avg, tid, sku),
    )


def update_sku_master_stock_avg_and_timestamp(
    conn: DbConnection,
    *,
    sku: str,
    total_stock: float,
    avg_unit_cost: float,
    now: str,
    tenant_id: str | None = None,
) -> None:
    tid = effective_tenant_id_for_request(tenant_id)
    db_execute(conn,
        """
        UPDATE sku_master
        SET total_stock = ?, avg_unit_cost = ?, updated_at = ?
        WHERE tenant_id = ? AND sku = ?;
        """,
        (total_stock, avg_unit_cost, now, tid, sku),
    )
