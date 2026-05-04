from typing import Optional

from database.connection import DbConnection
from database.repositories.customer_repository import fetch_customer_id_name_code
from database.repositories.support import use_connection
from database.repositories.session import write_transaction
from database.tenancy import effective_tenant_id_for_request
from database.repositories.sales_repository import get_recent_sales_rows
from database.sale_idempotency import (
    acquire_idempotency_transaction_lock,
    compute_sale_record_request_hash,
    ensure_sale_idempotency_table,
    fetch_idempotency_row,
    insert_idempotency_row,
)
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
    MSG_SALE_IDEMPOTENCY_PAYLOAD_MISMATCH,
    MSG_SALE_PREVIEW_MISMATCH,
    MSG_SALE_PRODUCT_NO_SKU,
    MSG_SALE_PRODUCT_SKU_INACTIVE,
    format_insufficient_stock,
)
from utils.validators import (
    normalize_and_require_sale_payment_method,
    require_non_negative_sale_discount,
    require_positive_integer_sale_quantity,
)


def compute_sale_discount_amount(
    base_price: float, discount_mode: str, discount_input: float
) -> float:
    """Espelha o cálculo de desconto da UI (percentual 0–100 ou fixo até ao subtotal)."""
    base = max(0.0, float(base_price))
    mode = (discount_mode or "percent").strip().lower()
    if mode == "fixed":
        dv = max(0.0, float(discount_input))
        return min(base, dv)
    pct = max(0.0, min(100.0, float(discount_input)))
    return min(base, base * (pct / 100.0))


def _normalize_discount_mode_input(
    discount_mode: str, discount_input: float
) -> tuple[str, float]:
    mode = (discount_mode or "percent").strip().lower()
    if mode == "fixed":
        return "fixed", max(0.0, float(discount_input))
    return "percent", max(0.0, min(100.0, float(discount_input)))


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
    conn: DbConnection, product_id: int, tenant_id: str, *, for_update: bool = False
):
    row = fetch_product_row_for_sale(
        conn, product_id, tenant_id=tenant_id, for_update=for_update
    )
    if row is None:
        raise ValueError(MSG_PRODUCT_NOT_FOUND)
    return row


def _money_close(a: float, b: float, *, eps: float = 0.02) -> bool:
    return abs(float(a) - float(b)) <= eps


def _preview_financials_match_expected(
    *,
    unit_price: float,
    final_total: float,
    discount_amount: float,
    expected_unit_price: Optional[float],
    expected_final_total: Optional[float],
    expected_discount_amount: Optional[float],
) -> None:
    """Garante paridade com o último preview quando o cliente envia os valores esperados."""
    if expected_unit_price is None:
        return
    if expected_final_total is None or expected_discount_amount is None:
        return
    if not (
        _money_close(unit_price, expected_unit_price)
        and _money_close(final_total, expected_final_total)
        and _money_close(discount_amount, expected_discount_amount)
    ):
        raise ValueError(MSG_SALE_PREVIEW_MISMATCH)


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
    idempotency_key: Optional[str] = None,
    expected_unit_price: Optional[float] = None,
    expected_final_total: Optional[float] = None,
    expected_discount_amount: Optional[float] = None,
) -> tuple[str, float]:
    """
    Atomically:
    - validate customer exists
    - read SKU selling price from sku_master and WAC (COGS)
    - verify stock >= quantity
    - update stock and sku_master totals (WAC unchanged on sale)
    - allocate sequential sale_code (#####V) and insert full sale row

    ``idempotency_key`` opcional: retries com a mesma chave e o mesmo corpo devolvem o mesmo
    ``sale_code`` sem duplicar venda. ``expected_*`` opcional: rejeita se os totais divergirem
    do preview (concorrência / alteração de preço).

    Returns (sale_code, final_total_after_discount).
    """
    qty, disc, pm = _record_sale_validate_pre_transaction(
        quantity, discount_amount, payment_method
    )
    tid = effective_tenant_id_for_request(tenant_id)
    key = (idempotency_key or "").strip()
    if key:
        ensure_sale_idempotency_table()
    req_hash = (
        compute_sale_record_request_hash(
            product_id=product_id,
            quantity=qty,
            customer_id=customer_id,
            discount_amount=disc,
            payment_method=pm,
        )
        if key
        else ""
    )
    sale_code: str = ""
    final_total_recorded: float = 0.0
    sku: str = ""
    from_idempotency_cache = False

    with write_transaction(immediate=True) as conn:
        if key:
            acquire_idempotency_transaction_lock(conn, tenant_id=tid, idempotency_key=key)
            existing = fetch_idempotency_row(conn, tenant_id=tid, idempotency_key=key)
            if existing is not None:
                if existing.get("request_hash") != req_hash:
                    raise ValueError(MSG_SALE_IDEMPOTENCY_PAYLOAD_MISMATCH)
                sale_code = str(existing.get("sale_code") or "")
                final_total_recorded = float(existing.get("final_total") or 0.0)
                from_idempotency_cache = True

        if not from_idempotency_cache:
            _record_sale_assert_customer_exists(conn, customer_id, tid)
            row = _record_sale_load_product_row(conn, product_id, tid, for_update=True)
            (
                sku,
                selling_price,
                gross_total,
                final_total,
                cogs_total,
            ) = _record_sale_validate_row_and_compute_totals(row, qty, disc)
            _preview_financials_match_expected(
                unit_price=selling_price,
                final_total=final_total,
                discount_amount=disc,
                expected_unit_price=expected_unit_price,
                expected_final_total=expected_final_total,
                expected_discount_amount=expected_discount_amount,
            )
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
            if key:
                insert_idempotency_row(
                    conn,
                    tenant_id=tid,
                    idempotency_key=key,
                    request_hash=req_hash,
                    sale_code=sale_code,
                    final_total=float(final_total_recorded),
                )

    if not from_idempotency_cache:
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


def preview_record_sale(
    *,
    product_id: int,
    quantity: int,
    customer_id: int,
    discount_mode: str,
    discount_input: float,
    payment_method: str,
    tenant_id: Optional[str] = None,
) -> dict:
    """
    Pré-visualização só leitura: mesmas validações e totais que ``record_sale``,
    sem gravar (releitura no submit continua dentro da transacção).
    """
    tid = effective_tenant_id_for_request(tenant_id)
    pm = normalize_and_require_sale_payment_method(payment_method)
    qty = require_positive_integer_sale_quantity(quantity)
    mode_norm, input_norm = _normalize_discount_mode_input(discount_mode, discount_input)

    with use_connection(None) as conn:
        _record_sale_assert_customer_exists(conn, customer_id, tid)
        crow = fetch_customer_id_name_code(conn, customer_id, tenant_id=tid)
        if crow is None:
            raise ValueError(MSG_CLIENT_NOT_FOUND)
        code = (crow.get("customer_code") or "").strip()
        name = (crow.get("name") or "").strip()
        if code and name:
            customer_label = f"{code} · {name}"
        elif name:
            customer_label = name
        elif code:
            customer_label = code
        else:
            customer_label = f"Cliente #{customer_id}"

        row = _record_sale_load_product_row(conn, product_id, tid)
        gross_pre = float(row["sp"]) * float(qty)
        disc = compute_sale_discount_amount(gross_pre, mode_norm, input_norm)
        disc = require_non_negative_sale_discount(disc)
        sku, unit_px, base_px, final_total, _cogs = _record_sale_validate_row_and_compute_totals(
            row, qty, disc
        )

    return {
        "product_id": int(product_id),
        "customer_id": int(customer_id),
        "base_price": base_px,
        "discount_amount": disc,
        "final_total": final_total,
        "unit_price": unit_px,
        "stock": float(row["stock"] or 0),
        "sku": sku,
        "quantity": qty,
        "discount_mode": mode_norm,
        "discount_input": input_norm,
        "payment_method": pm,
        "customer_label": customer_label,
    }


def fetch_recent_sales_for_ui(
    *,
    limit: int = 20,
    tenant_id: Optional[str] = None,
):
    """Lista vendas recentes para tabela na página Vendas (mesmo SQL que a UI usava)."""
    tid = effective_tenant_id_for_request(tenant_id)
    return get_recent_sales_rows(None, limit=limit, tenant_id=tid)
