"""Vendas — apenas acesso a dados (padrão get/create).

``conn`` pode ser ``None`` para abrir ligação com :func:`~database.connection.get_db_conn`.
"""

from __future__ import annotations

from datetime import datetime

from database.connection import DbConnection
from database.repositories.support import use_connection
from database.sale_codes import _next_sale_sequence, format_sale_code
from database.sku_master_repo import sync_sku_master_totals
from database.sql_compat import db_execute, is_sqlite_conn
from database.tenancy import effective_tenant_id_for_request

__all__ = [
    "get_customer_row_for_sale",
    "get_product_row_for_sale",
    "create_sale_with_stock_decrement",
    "get_recent_sales_rows",
    "fetch_sale_row_by_code",
]


def get_customer_row_for_sale(
    conn: DbConnection | None,
    customer_id: int,
    tenant_id: str | None = None,
):
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return db_execute(
            c,
            "SELECT id FROM customers WHERE tenant_id = %s AND id = %s;",
            (tid, int(customer_id)),
        ).fetchone()


def get_product_row_for_sale(
    conn: DbConnection | None,
    product_id: int,
    tenant_id: str | None = None,
    *,
    for_update: bool = False,
):
    """``for_update=True`` bloqueia a linha de ``products`` na transacção (PostgreSQL)."""
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        lock_sql = ""
        if for_update and not is_sqlite_conn(c):
            lock_sql = " FOR UPDATE OF p"
        return db_execute(
            c,
            f"""
            SELECT p.stock, p.sku, p.deleted_at AS p_del,
                   sm.deleted_at AS sm_del,
                   COALESCE(sm.selling_price, 0) AS sp,
                   COALESCE(sm.avg_unit_cost, 0) AS avg_cogs
            FROM products p
            LEFT JOIN sku_master sm ON sm.sku = p.sku AND sm.tenant_id = p.tenant_id
            WHERE p.tenant_id = %s AND p.id = %s{lock_sql};
            """,
            (tid, product_id),
        ).fetchone()


def create_sale_with_stock_decrement(
    conn: DbConnection | None,
    *,
    product_id: int,
    customer_id: int,
    qty: int,
    sku: str,
    selling_price: float,
    disc: float,
    gross_total: float,
    final_total: float,
    cogs_total: float,
    payment_method: str,
    tenant_id: str | None = None,
) -> tuple[str, float]:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        cur = db_execute(
            c,
            """
            UPDATE products
            SET stock = stock - %s
            WHERE tenant_id = %s AND id = %s AND deleted_at IS NULL AND stock >= %s
            RETURNING stock;
            """,
            (qty, tid, product_id, qty),
        )
        if cur.fetchone() is None:
            from utils.error_messages import format_insufficient_stock

            probe = db_execute(
                c,
                "SELECT stock FROM products WHERE tenant_id = %s AND id = %s;",
                (tid, product_id),
            ).fetchone()
            avail = float(probe["stock"] or 0) if probe else 0.0
            raise ValueError(format_insufficient_stock(avail))
        sync_sku_master_totals(c, sku, tenant_id=tid)

        seq_n = _next_sale_sequence(c, tid)
        sale_code = format_sale_code(seq_n)

        db_execute(
            c,
            """
            INSERT INTO sales (
                tenant_id, sale_code, product_id, customer_id, quantity, unit_price, discount_amount,
                base_amount, total, sold_at, sku, cogs_total, payment_method
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                tid,
                sale_code,
                product_id,
                int(customer_id),
                qty,
                selling_price,
                disc,
                gross_total,
                final_total,
                datetime.now().isoformat(timespec="seconds"),
                sku,
                cogs_total,
                payment_method,
            ),
        )
        return sale_code, final_total


def fetch_sale_row_by_code(
    conn: DbConnection | None,
    *,
    sale_code: str,
    tenant_id: str | None = None,
):
    """Uma linha de venda por ``sale_code`` e inquilino (validação / probes)."""
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return db_execute(
            c,
            """
            SELECT id, customer_id, product_id, quantity, total, sku
            FROM sales
            WHERE tenant_id = %s AND sale_code = %s;
            """,
            (tid, str(sale_code).strip()),
        ).fetchone()


def get_recent_sales_rows(
    conn: DbConnection | None,
    *,
    limit: int = 20,
    tenant_id: str | None = None,
):
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return db_execute(
            c,
            """
            SELECT
                s.sale_code,
                s.id,
                p.name AS product_name,
                s.sku,
                CASE
                    WHEN s.customer_id IS NULL THEN '—'
                    ELSE (COALESCE(c.customer_code, '') || ' — ' || COALESCE(c.name, ''))
                END AS customer_label,
                s.quantity,
                s.unit_price,
                s.discount_amount,
                s.total,
                s.sold_at,
                s.payment_method
            FROM sales s
            JOIN products p ON p.tenant_id = s.tenant_id AND p.id = s.product_id
            LEFT JOIN customers c ON c.tenant_id = s.tenant_id AND c.id = s.customer_id
            WHERE s.tenant_id = %s
            ORDER BY s.id DESC
            LIMIT %s;
            """,
            (tid, int(limit)),
        ).fetchall()


# --- Compatibilidade (nomes legados) ---
fetch_customer_exists = get_customer_row_for_sale
fetch_product_row_for_sale = get_product_row_for_sale
insert_sale_and_decrement_stock = create_sale_with_stock_decrement

__all__ += [
    "fetch_customer_exists",
    "fetch_product_row_for_sale",
    "insert_sale_and_decrement_stock",
]
