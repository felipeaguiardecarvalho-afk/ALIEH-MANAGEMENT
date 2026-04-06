"""Códigos de cliente e sequência."""

from database.connection import DbConnection
from database.sql_compat import db_execute, is_sqlite_conn
from database.tenancy import DEFAULT_TENANT_ID


def format_customer_code(n: int) -> str:
    return f"{int(n):05d}"


def sync_customer_sequence_counter_from_customers(
    conn: DbConnection, tenant_id: str = DEFAULT_TENANT_ID
) -> None:
    if is_sqlite_conn(conn):
        digit_filter = "AND customer_code GLOB '[0-9][0-9][0-9][0-9][0-9]'"
    else:
        digit_filter = "AND customer_code ~ '^[0-9]{5}$'"
    row = db_execute(
        conn,
        f"""
        SELECT MAX(CAST(customer_code AS INTEGER)) AS m
        FROM customers
        WHERE tenant_id = ?
          {digit_filter};
        """,
        (tenant_id,),
    ).fetchone()
    max_n = int(row["m"] or 0) if row else 0
    r2 = db_execute(
        conn,
        "SELECT last_value FROM customer_sequence_counter WHERE tenant_id = ? AND id = 1;",
        (tenant_id,),
    ).fetchone()
    cur = int(r2["last_value"] or 0) if r2 else 0
    db_execute(
        conn,
        "UPDATE customer_sequence_counter SET last_value = ? WHERE tenant_id = ? AND id = 1;",
        (max(max_n, cur), tenant_id),
    )
