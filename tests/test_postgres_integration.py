"""Integração real com PostgreSQL (producto → cliente → venda → leitura).

Opt-in: defina ``ALIEH_PG_INTEGRATION=1`` (ou ``true``/``yes``) e um ``DATABASE_URL``
apontando para uma instância Postgres (ex.: Supabase de staging) com ``schema.sql``
aplicado. Recomenda-se BD descartável: os testes inserem dados num ``tenant_id`` único
e removem-nos no final.

Não altera serviços nem repositórios — apenas orquestra chamadas existentes.
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest

from database.repositories.product_repository import get_distinct_skus_for_enter_code
from database.repositories.query_repository import fetch_customers_ordered, fetch_product_by_id
from database.repositories.sales_repository import get_recent_sales_rows

pytestmark = pytest.mark.skipif(
    os.environ.get("ALIEH_PG_INTEGRATION", "").strip().lower() not in ("1", "true", "yes"),
    reason=(
        "Integração Postgres desligada. Exporte ALIEH_PG_INTEGRATION=1 e DATABASE_URL "
        "para uma base com schema aplicado."
    ),
)


@pytest.fixture()
def pg_tenant_id() -> str:
    return f"itest_{uuid.uuid4().hex[:16]}"


@pytest.fixture()
def postgres_integration_tenant(pg_tenant_id: str) -> str:
    """Garante contadores por tenant e limpa linhas do tenant após o teste."""
    from database.connection import get_postgres_conn
    from database.sql_compat import db_execute

    tid = pg_tenant_id
    with get_postgres_conn() as conn:
        for stmt in (
            """
            INSERT INTO sku_sequence_counter (tenant_id, id, last_value)
            VALUES (?, 1, 0)
            ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            """
            INSERT INTO customer_sequence_counter (tenant_id, id, last_value)
            VALUES (?, 1, 0)
            ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            """
            INSERT INTO sale_sequence_counter (tenant_id, id, last_value)
            VALUES (?, 1, 0)
            ON CONFLICT (tenant_id, id) DO NOTHING
            """,
        ):
            db_execute(conn, stmt, (tid,))

    yield tid

    deletes = [
        "DELETE FROM sales WHERE tenant_id = ?",
        "DELETE FROM stock_cost_entries WHERE tenant_id = ?",
        "DELETE FROM sku_pricing_records WHERE tenant_id = ?",
        "DELETE FROM sku_cost_components WHERE tenant_id = ?",
        "DELETE FROM price_history WHERE tenant_id = ?",
        "DELETE FROM products WHERE tenant_id = ?",
        "DELETE FROM customers WHERE tenant_id = ?",
        "DELETE FROM sku_master WHERE tenant_id = ?",
        "DELETE FROM sku_sequence_counter WHERE tenant_id = ?",
        "DELETE FROM customer_sequence_counter WHERE tenant_id = ?",
        "DELETE FROM sale_sequence_counter WHERE tenant_id = ?",
    ]
    with get_postgres_conn() as conn:
        for q in deletes:
            db_execute(conn, q, (tid,))


def test_postgres_product_customer_sale_roundtrip(postgres_integration_tenant: str) -> None:
    import psycopg

    from database.connection import get_db_conn
    from database.repositories.customer_repository import get_customer_id_name_code
    from database.repositories.query_repository import fetch_products
    from services.customer_service import insert_customer_row
    from services.product_service import add_product, update_sku_selling_price
    from services.sales_service import record_sale

    tid = postgres_integration_tenant
    suffix = uuid.uuid4().hex[:8]
    product_name = f"PG integ óculos {suffix}"
    customer_name = f"Cliente integ {suffix}"

    with get_db_conn() as conn:
        assert isinstance(conn, psycopg.Connection), (
            "Esperada ligação psycopg; verifique DATABASE_URL e que não há fallback SQLite."
        )

    enter_code = add_product(
        product_name,
        stock=5.0,
        registered_date=date.today(),
        frame_color="Preto",
        lens_color="Cinza",
        style="Aviador",
        palette="Clássico",
        gender="Unissex",
        unit_cost=20.0,
        tenant_id=tid,
    )

    sku_rows = get_distinct_skus_for_enter_code(None, enter_code, tenant_id=tid)
    assert len(sku_rows) == 1
    sku = (sku_rows[0]["sku"] or "").strip()
    assert sku

    update_sku_selling_price(sku, 100.0, note="integration test", tenant_id=tid)

    customer_code = insert_customer_row(
        customer_name,
        cpf=None,
        rg=None,
        phone=None,
        email=None,
        instagram=None,
        zip_code=None,
        street=None,
        number=None,
        neighborhood=None,
        city=None,
        state=None,
        country=None,
        tenant_id=tid,
    )

    customers = fetch_customers_ordered(tenant_id=tid)
    match = [r for r in customers if str(r["customer_code"]) == str(customer_code)]
    assert len(match) == 1
    customer_id = int(match[0]["id"])

    products = fetch_products(tenant_id=tid)
    prod_row = next(p for p in products if (p["product_enter_code"] or "") == enter_code)
    product_id = int(prod_row["id"])
    assert float(prod_row["stock"] or 0) == 5.0

    sale_code, final_total = record_sale(
        product_id,
        2,
        customer_id,
        0.0,
        payment_method="Pix",
        tenant_id=tid,
    )
    assert sale_code
    assert abs(float(final_total) - 200.0) < 1e-6

    row_after = fetch_product_by_id(product_id, tenant_id=tid)
    assert row_after is not None
    assert abs(float(row_after["stock"] or 0) - 3.0) < 1e-6

    cust_read = get_customer_id_name_code(None, customer_id, tenant_id=tid)
    assert cust_read is not None
    assert str(cust_read["name"]) == customer_name
    assert str(cust_read["customer_code"]) == str(customer_code)

    recent = get_recent_sales_rows(None, limit=30, tenant_id=tid)
    assert recent, "lista de vendas não deve ser vazia"
    top = recent[0]
    assert str(top["sale_code"]) == str(sale_code)
    assert int(top["quantity"]) == 2
    assert abs(float(top["total"] or 0) - 200.0) < 1e-6
    assert customer_code in str(top["customer_label"])
    assert product_name.split()[0] in str(top["product_name"]) or product_name in str(
        top["product_name"]
    )
