from datetime import datetime
from typing import Any, Optional, Tuple

from database.connection import DbConnection
from database.repositories.session import write_transaction
from database.tenancy import effective_tenant_id_for_request
from database.customer_repo import (
    count_sales_for_customer,
    customer_sequence_next,
    delete_customer_by_id,
    fetch_customer_id_name_code,
    find_customer_duplicate_row,
    insert_customer_row as insert_customer_in_db,
    update_customer_row as update_customer_in_db,
)
from database.customer_sync import format_customer_code
from utils.critical_log import log_critical_event
from utils.error_messages import (
    MSG_CLIENT_NOT_FOUND,
    format_customer_delete_has_sales,
    format_customer_duplicate_identity,
)


def find_customer_duplicate(
    conn: DbConnection,
    cpf_digits: str,
    phone_digits: str,
    exclude_id: Optional[int] = None,
    *,
    tenant_id: Optional[str] = None,
) -> Optional[Tuple[str, Any]]:
    """
    If cpf_digits or phone_digits is non-empty, check for another row with same value.
    Returns ("cpf"|"phone", row) or None.
    """
    return find_customer_duplicate_row(
        conn, cpf_digits, phone_digits, exclude_id, tenant_id=tenant_id
    )


def _insert_customer_raise_if_duplicate_cpf_phone(
    conn: DbConnection,
    cpf: Optional[str],
    phone: Optional[str],
    *,
    tenant_id: Optional[str] = None,
) -> None:
    dup = find_customer_duplicate(
        conn, cpf or "", phone or "", None, tenant_id=tenant_id
    )
    if dup:
        kind, row = dup
        label = "CPF" if kind == "cpf" else "Telefone"
        raise ValueError(
            format_customer_duplicate_identity(
                label, row["customer_code"], row["name"]
            )
        )


def _update_customer_raise_if_duplicate_cpf_phone(
    conn: DbConnection,
    customer_id: int,
    cpf: Optional[str],
    phone: Optional[str],
    *,
    tenant_id: Optional[str] = None,
) -> None:
    dup = find_customer_duplicate(
        conn, cpf or "", phone or "", customer_id, tenant_id=tenant_id
    )
    if dup:
        kind, row = dup
        label = "CPF" if kind == "cpf" else "Telefone"
        raise ValueError(
            format_customer_duplicate_identity(
                label, row["customer_code"], row["name"]
            )
        )


def insert_customer_row(
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
    *,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> str:
    """Allocate customer_code, insert row. Returns new customer_code."""
    tid = effective_tenant_id_for_request(tenant_id)
    now = datetime.now().isoformat(timespec="seconds")
    with write_transaction(immediate=True) as conn:
        _insert_customer_raise_if_duplicate_cpf_phone(
            conn, cpf, phone, tenant_id=tid
        )
        n = customer_sequence_next(conn, tenant_id=tid)
        code = format_customer_code(n)
        insert_customer_in_db(
            conn,
            code=code,
            name=name.strip(),
            cpf=cpf or None,
            rg=rg or None,
            phone=phone or None,
            email=email or None,
            instagram=instagram or None,
            zip_code=zip_code or None,
            street=street or None,
            number=number or None,
            neighborhood=neighborhood or None,
            city=city or None,
            state=state or None,
            country=country or None,
            created_at=now,
            updated_at=now,
            tenant_id=tid,
        )
    log_critical_event(
        "customer_created",
        user_id=user_id,
        customer_code=code,
        name=name.strip(),
    )
    return code


def update_customer_row(
    customer_id: int,
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
    *,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> None:
    tid = effective_tenant_id_for_request(tenant_id)
    now = datetime.now().isoformat(timespec="seconds")
    with write_transaction(immediate=True) as conn:
        _update_customer_raise_if_duplicate_cpf_phone(
            conn, customer_id, cpf, phone, tenant_id=tid
        )
        update_customer_in_db(
            conn,
            customer_id,
            name=name.strip(),
            cpf=cpf or None,
            rg=rg or None,
            phone=phone or None,
            email=email or None,
            instagram=instagram or None,
            zip_code=zip_code or None,
            street=street or None,
            number=number or None,
            neighborhood=neighborhood or None,
            city=city or None,
            state=state or None,
            country=country or None,
            updated_at=now,
            tenant_id=tid,
        )


def delete_customer_row(
    customer_id: int, *, user_id: Optional[str] = None, tenant_id: Optional[str] = None
) -> None:
    """Remove o cliente do banco. Falha se existir venda vinculada a `customer_id`."""
    cid = int(customer_id)
    tid = effective_tenant_id_for_request(tenant_id)
    with write_transaction(immediate=True) as conn:
        row = fetch_customer_id_name_code(conn, cid, tenant_id=tid)
        if row is None:
            raise ValueError(MSG_CLIENT_NOT_FOUND)
        n = count_sales_for_customer(conn, cid, tenant_id=tid)
        if n > 0:
            raise ValueError(format_customer_delete_has_sales(n))
        delete_customer_by_id(conn, cid, tenant_id=tid)
    log_critical_event(
        "data_deletion",
        user_id=user_id,
        entity="customer",
        customer_id=cid,
        customer_code=row["customer_code"],
        name=row["name"],
    )
