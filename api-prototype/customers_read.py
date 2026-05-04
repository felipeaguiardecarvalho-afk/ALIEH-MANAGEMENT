"""Read-only customer queries for api-prototype."""

from __future__ import annotations

from database.repositories.support import use_connection
from database.sql_compat import db_execute, sql_numeric_sort_key_text
from database.tenancy import effective_tenant_id_for_request


def list_customers(*, tenant_id: str | None = None) -> list:
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        order_expr = sql_numeric_sort_key_text("customer_code")
        return db_execute(
            conn,
            f"""
            SELECT id, customer_code, name, cpf, rg, phone, email, instagram,
                   zip_code, street, number, neighborhood, city, state, country,
                   created_at, updated_at
            FROM customers
            WHERE tenant_id = %s
            ORDER BY {order_expr};
            """,
            (tid,),
        ).fetchall()


def fetch_customer_full(*, customer_id: int, tenant_id: str | None = None):
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        return db_execute(
            conn,
            """
            SELECT id, customer_code, name, cpf, rg, phone, email, instagram,
                   zip_code, street, number, neighborhood, city, state, country,
                   created_at, updated_at
            FROM customers
            WHERE tenant_id = %s AND id = %s;
            """,
            (tid, int(customer_id)),
        ).fetchone()
