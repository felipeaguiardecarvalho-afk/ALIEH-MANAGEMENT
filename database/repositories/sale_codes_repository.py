"""Códigos de venda (#####V) e sequência."""

from __future__ import annotations

import re

from database.connection import DbConnection
from database.sql_compat import db_execute
from database.tenancy import DEFAULT_TENANT_ID


def format_sale_code(n: int) -> str:
    return f"{int(n):05d}V"


def _next_sale_sequence(
    conn: DbConnection, tenant_id: str = DEFAULT_TENANT_ID
) -> int:
    cur = db_execute(conn,
        """
        UPDATE sale_sequence_counter
        SET last_value = last_value + 1
        WHERE tenant_id = ? AND id = 1
        RETURNING last_value;
        """,
        (tenant_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("Contador de sequência de venda não inicializado.")
    return int(row["last_value"])


def sync_sale_sequence_counter_from_sales(
    conn: DbConnection, tenant_id: str = DEFAULT_TENANT_ID
) -> None:
    max_n = 0
    for row in db_execute(conn,
        """
        SELECT sale_code FROM sales
        WHERE tenant_id = ?
          AND sale_code IS NOT NULL AND TRIM(sale_code) != '';
        """,
        (tenant_id,),
    ):
        s = str(row["sale_code"] or "").strip().upper()
        m = re.match(r"^(\d{5})V$", s)
        if m:
            max_n = max(max_n, int(m.group(1)))
    row2 = db_execute(conn,
        "SELECT last_value FROM sale_sequence_counter WHERE tenant_id = ? AND id = 1;",
        (tenant_id,),
    ).fetchone()
    cur = int(row2["last_value"] or 0) if row2 else 0
    db_execute(conn,
        "UPDATE sale_sequence_counter SET last_value = ? WHERE tenant_id = ? AND id = 1;",
        (max(max_n, cur), tenant_id),
    )
