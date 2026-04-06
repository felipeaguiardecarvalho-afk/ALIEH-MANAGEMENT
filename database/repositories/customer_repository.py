"""Persistência de clientes — apenas acesso a dados (padrão get/create/update/delete).

``conn`` pode ser ``None`` para abrir ligação com :func:`~database.connection.get_db_conn`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional, Tuple

from database.connection import DbConnection
from database.repositories.support import use_connection
from database.sql_compat import db_execute
from database.tenancy import effective_tenant_id_for_request

__all__ = [
    "update_customer_sequence_next",
    "get_customer_duplicate_row",
    "create_customer",
    "update_customer",
    "get_customer_id_name_code",
    "get_customer_sales_count",
    "delete_customer",
]


def update_customer_sequence_next(
    conn: DbConnection | None,
    tenant_id: str | None = None,
) -> int:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        cur = db_execute(
            c,
            """
            UPDATE customer_sequence_counter
            SET last_value = last_value + 1
            WHERE tenant_id = ? AND id = 1
            RETURNING last_value;
            """,
            (tid,),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("Contador de sequência de cliente não inicializado.")
        return int(row["last_value"])


def get_customer_duplicate_row(
    conn: DbConnection | None,
    cpf_digits: str,
    phone_digits: str,
    exclude_id: Optional[int],
    tenant_id: str | None = None,
) -> Optional[Tuple[str, Mapping[str, Any]]]:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        if cpf_digits:
            q = "SELECT id, customer_code, name, cpf, phone FROM customers WHERE tenant_id = ? AND cpf = ?"
            params: list[Any] = [tid, cpf_digits]
            if exclude_id is not None:
                q += " AND id != ?"
                params.append(exclude_id)
            row = db_execute(c, q, params).fetchone()
            if row:
                return ("cpf", row)
        if phone_digits:
            q = "SELECT id, customer_code, name, cpf, phone FROM customers WHERE tenant_id = ? AND phone = ?"
            params = [tid, phone_digits]
            if exclude_id is not None:
                q += " AND id != ?"
                params.append(exclude_id)
            row = db_execute(c, q, params).fetchone()
            if row:
                return ("phone", row)
        return None


def create_customer(
    conn: DbConnection | None,
    *,
    code: str,
    name: str,
    cpf: Optional[str],
    rg: Optional[str],
    phone: Optional[str],
    email: Optional[str],
    instagram: Optional[str],
    zip_code: Optional[str],
    street: Optional[str],
    number: Optional[str],
    neighborhood: Optional[str],
    city: Optional[str],
    state: Optional[str],
    country: Optional[str],
    created_at: str,
    updated_at: str,
    tenant_id: str | None = None,
) -> None:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        db_execute(
            c,
            """
            INSERT INTO customers (
                tenant_id, customer_code, name, cpf, rg, phone, email, instagram,
                zip_code, street, number, neighborhood, city, state, country,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                tid,
                code,
                name,
                cpf,
                rg,
                phone,
                email,
                instagram,
                zip_code,
                street,
                number,
                neighborhood,
                city,
                state,
                country,
                created_at,
                updated_at,
            ),
        )


def update_customer(
    conn: DbConnection | None,
    customer_id: int,
    *,
    name: str,
    cpf: Optional[str],
    rg: Optional[str],
    phone: Optional[str],
    email: Optional[str],
    instagram: Optional[str],
    zip_code: Optional[str],
    street: Optional[str],
    number: Optional[str],
    neighborhood: Optional[str],
    city: Optional[str],
    state: Optional[str],
    country: Optional[str],
    updated_at: str,
    tenant_id: str | None = None,
) -> None:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        db_execute(
            c,
            """
            UPDATE customers SET
                name = ?, cpf = ?, rg = ?, phone = ?, email = ?, instagram = ?,
                zip_code = ?, street = ?, number = ?, neighborhood = ?,
                city = ?, state = ?, country = ?, updated_at = ?
            WHERE tenant_id = ? AND id = ?;
            """,
            (
                name,
                cpf,
                rg,
                phone,
                email,
                instagram,
                zip_code,
                street,
                number,
                neighborhood,
                city,
                state,
                country,
                updated_at,
                tid,
                customer_id,
            ),
        )


def get_customer_id_name_code(
    conn: DbConnection | None,
    customer_id: int,
    tenant_id: str | None = None,
):
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return db_execute(
            c,
            "SELECT id, customer_code, name FROM customers WHERE tenant_id = ? AND id = ?;",
            (tid, customer_id),
        ).fetchone()


def get_customer_sales_count(
    conn: DbConnection | None,
    customer_id: int,
    tenant_id: str | None = None,
) -> int:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return int(
            db_execute(
                c,
                "SELECT COUNT(*) AS c FROM sales WHERE tenant_id = ? AND customer_id = ?;",
                (tid, customer_id),
            ).fetchone()["c"]
        )


def delete_customer(
    conn: DbConnection | None,
    customer_id: int,
    tenant_id: str | None = None,
) -> None:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        db_execute(
            c,
            "DELETE FROM customers WHERE tenant_id = ? AND id = ?;",
            (tid, customer_id),
        )


# --- Compatibilidade (nomes legados) ---
customer_sequence_next = update_customer_sequence_next
find_customer_duplicate_row = get_customer_duplicate_row
insert_customer_row = create_customer
update_customer_row = update_customer
fetch_customer_id_name_code = get_customer_id_name_code
count_sales_for_customer = get_customer_sales_count
delete_customer_by_id = delete_customer

__all__ += [
    "customer_sequence_next",
    "find_customer_duplicate_row",
    "insert_customer_row",
    "update_customer_row",
    "fetch_customer_id_name_code",
    "count_sales_for_customer",
    "delete_customer_by_id",
]
