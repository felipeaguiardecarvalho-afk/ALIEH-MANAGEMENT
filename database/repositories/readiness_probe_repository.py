"""Sequências e limpeza para o tenant descartável do probe de prontidão a produção."""

from __future__ import annotations

from database.connection import DbConnection
from database.sql_compat import db_execute
from database.tenancy import effective_tenant_id_for_request

__all__ = [
    "ensure_readiness_probe_sequence_counters",
    "delete_readiness_probe_tenant_data",
]


def ensure_readiness_probe_sequence_counters(
    conn: DbConnection,
    tenant_id: str,
) -> None:
    tid = effective_tenant_id_for_request(tenant_id)
    statements = (
        (
            """
            INSERT INTO sku_sequence_counter (tenant_id, id, last_value)
            VALUES (?, 1, 0)
            ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            (tid,),
        ),
        (
            """
            INSERT INTO customer_sequence_counter (tenant_id, id, last_value)
            VALUES (?, 1, 0)
            ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            (tid,),
        ),
        (
            """
            INSERT INTO sale_sequence_counter (tenant_id, id, last_value)
            VALUES (?, 1, 0)
            ON CONFLICT (tenant_id, id) DO NOTHING
            """,
            (tid,),
        ),
    )
    for sql, params in statements:
        db_execute(conn, sql, params)


def delete_readiness_probe_tenant_data(conn: DbConnection, tenant_id: str) -> None:
    """Apaga todas as linhas do tenant de probe (ordem segura de FKs)."""
    tid = effective_tenant_id_for_request(tenant_id)
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
    for q in deletes:
        db_execute(conn, q, (tid,))
