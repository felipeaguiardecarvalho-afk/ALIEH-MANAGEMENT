from typing import Optional

from database.connection import DbConnection
from database.repositories.session import write_transaction
from database.tenancy import effective_tenant_id_for_request
from database.repositories.sales_repository import get_recent_sales_rows
from database.sales_repo import (
    fetch_customer_exists,
    fetch_product_row_for_sale,
    insert_sale_and_decrement_stock,
)
from utils.critical_log import log_critical_event
from utils.error_messages import (
    MSG_CLIENT_NOT_FOUND,
    MSG_PRODUCT_NOT_FOUND,
    MSG_SALE_DEFINE_LIST_PRICE_FIRST,
    MSG_SALE_DISCOUNT_EXCEEDS_BASE,
    MSG_SALE_PRODUCT_NO_SKU,
    MSG_SALE_PRODUCT_SKU_INACTIVE,
    format_insufficient_stock,
)
from utils.validators import (
    normalize_and_require_sale_payment_method,
    require_non_negative_sale_discount,
    require_positive_integer_sale_quantity,
)


def _record_sale_validate_pre_transaction(
    quantity: int,
    discount_amount: float,
    payment_method: str,
) -> tuple[int, float, str]:
    qty = require_positive_integer_sale_quantity(quantity)
    disc = require_non_negative_sale_discount(discount_amount)
    pm = normalize_and_require_sale_payment_method(payment_method)
    return qty, disc, pm


def _record_sale_assert_customer_exists(
    conn: DbConnection, customer_id: int, tenant_id: str
) -> None:
    customer_row = fetch_customer_exists(conn, customer_id, tenant_id=tenant_id)
    if customer_row is None:
        raise ValueError(MSG_CLIENT_NOT_FOUND)


def _record_sale_load_product_row(
    conn: DbConnection, product_id: int, tenant_id: str
):
    row = fetch_product_row_for_sale(conn, product_id, tenant_id=tenant_id)
    if row is None:
        raise ValueError(MSG_PRODUCT_NOT_FOUND)
    return row


def _record_sale_validate_row_and_compute_totals(
    row,
    qty: int,
    disc: float,
) -> tuple[str, float, float, float, float]:
    if row["p_del"] or row["sm_del"]:
        raise ValueError(MSG_SALE_PRODUCT_SKU_INACTIVE)

    sku = (row["sku"] or "").strip()
    if not sku:
        raise ValueError(MSG_SALE_PRODUCT_NO_SKU)

    selling_price = float(row["sp"])
    if selling_price <= 0:
        raise ValueError(MSG_SALE_DEFINE_LIST_PRICE_FIRST)

    stock = float(row["stock"] or 0)
    gross_total = selling_price * float(qty)

    if float(qty) > stock + 1e-9:
        raise ValueError(format_insufficient_stock(stock))

    if disc > gross_total + 1e-9:
        raise ValueError(MSG_SALE_DISCOUNT_EXCEEDS_BASE)

    final_total = gross_total - disc
    avg_cogs = float(row["avg_cogs"])
    cogs_total = float(qty) * avg_cogs
    return sku, selling_price, gross_total, final_total, cogs_total


def record_sale(
    product_id: int,
    quantity: int,
    customer_id: int,
    discount_amount: float,
    *,
    payment_method: str,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> tuple[str, float]:
    """
    Atomically:
    - validate customer exists
    - read SKU selling price from sku_master and WAC (COGS)
    - verify stock >= quantity
    - update stock and sku_master totals (WAC unchanged on sale)
    - allocate sequential sale_code (#####V) and insert full sale row

    Returns (sale_code, final_total_after_discount).
    """
    qty, disc, pm = _record_sale_validate_pre_transaction(
        quantity, discount_amount, payment_method
    )
    tid = effective_tenant_id_for_request(tenant_id)
    with write_transaction(immediate=True) as conn:
        _record_sale_assert_customer_exists(conn, customer_id, tid)
        row = _record_sale_load_product_row(conn, product_id, tid)
        (
            sku,
            selling_price,
            gross_total,
            final_total,
            cogs_total,
        ) = _record_sale_validate_row_and_compute_totals(row, qty, disc)
        sale_code, final_total_recorded = insert_sale_and_decrement_stock(
            conn,
            product_id=product_id,
            customer_id=customer_id,
            qty=qty,
            sku=sku,
            selling_price=selling_price,
            disc=disc,
            gross_total=gross_total,
            final_total=final_total,
            cogs_total=cogs_total,
            payment_method=pm,
            tenant_id=tid,
        )
    log_critical_event(
        "sale_recorded",
        user_id=user_id,
        sale_code=sale_code,
        product_id=product_id,
        customer_id=customer_id,
        quantity=qty,
        sku=sku,
        total=final_total_recorded,
        payment_method=pm,
    )
    return sale_code, final_total_recorded


def fetch_recent_sales_for_ui(
    *,
    limit: int = 20,
    tenant_id: Optional[str] = None,
):
    """Lista vendas recentes para tabela na página Vendas (mesmo SQL que a UI usava)."""
    tid = effective_tenant_id_for_request(tenant_id)
    return get_recent_sales_rows(None, limit=limit, tenant_id=tid)
