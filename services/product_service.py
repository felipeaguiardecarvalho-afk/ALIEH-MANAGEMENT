from datetime import datetime
from typing import Optional

from database.connection import DbConnection
from database.repositories.session import connection_scope, write_transaction
from database.tenancy import effective_tenant_id_for_request
from database.constants import DUPLICATE_SKU_BASE_ERROR_MSG
from database.cost_components_repo import (
    ensure_sku_cost_component_rows,
    recompute_sku_structured_cost_total,
    update_sku_cost_component_line,
)
from database.product_write_repo import (
    apply_target_selling_price_to_master_products_history,
    clear_cost_price_unlock_by_enter_code,
    count_instock_locked_batch_rows,
    deactivate_sku_pricing_records,
    decrement_product_stock_manual,
    fetch_distinct_skus_for_enter_code,
    fetch_other_product_with_sku,
    fetch_product_id_by_sku,
    fetch_product_name_sku_by_id,
    fetch_same_batch_product_row,
    fetch_sku_master_selling_and_avg_cost,
    fetch_sku_master_selling_price_row,
    insert_price_history_entry,
    insert_product_zero_stock_row,
    insert_sku_pricing_record_active,
    reset_stock_cost_price_unlock_by_enter_code,
    sku_master_exists,
    update_instock_batch_pricing_lock,
    update_product_attributes_and_sku,
    update_product_cost_price_by_id,
    update_product_image_path_by_id,
    update_products_price_where_sku,
    update_sku_master_selling_price_updated_at,
)
from database.stock_receipt_repo import (
    add_stock_to_product_row,
    fetch_product_batch_row,
    fetch_sku_master_avg_unit_cost_row,
    fetch_sku_master_deleted_flag,
    insert_stock_cost_entry,
    set_products_cost_by_sku,
    sum_active_stock_by_sku,
    update_sku_master_stock_avg_and_timestamp,
)
from database.product_codes import make_product_enter_code
from database.product_images import save_product_image_file
from database.sku_codec import (
    _next_sku_sequence,
    build_product_sku_body,
    format_sku_sequence_int,
    sku_base_body_exists,
)
from database.repositories.product_repository import get_product_stock_name_sku_by_id
from database.sku_master_repo import ensure_sku_master, sync_sku_master_totals
from utils.critical_log import log_critical_event
from utils.error_messages import (
    MSG_CMP_NOT_AVAILABLE,
    MSG_PRODUCT_LOT_NOT_FOUND,
    MSG_PRODUCT_NOT_FOUND,
    MSG_PRODUCT_SKU_MISMATCH_BATCH,
    MSG_SKU_NOT_IN_MASTER,
    MSG_SKU_NOT_IN_STOCK_LINE,
    MSG_STOCK_RECEIPT_INACTIVE_LOT,
    MSG_STOCK_RECEIPT_INACTIVE_SKU,
    format_duplicate_sku_attr_conflict,
    format_sku_already_exists,
)
from utils.validators import (
    require_add_product_stock_and_unit_cost_consistency,
    require_non_negative_cost_component_line,
    require_non_negative_sku_pricing_inputs,
    require_nonempty_sku_before_selling_price,
    require_positive_computed_pricing_target,
    require_positive_sku_list_price,
    validate_stock_receipt_quantity_and_unit_cost,
)


def fetch_product_stock_name_sku(
    product_id: int,
    *,
    tenant_id: Optional[str] = None,
):
    """Leitura usada na UI de vendas (estoque / nome / SKU do lote)."""
    tid = effective_tenant_id_for_request(tenant_id)
    return get_product_stock_name_sku_by_id(None, int(product_id), tenant_id=tid)


def _apply_stock_receipt_assert_product_batch(
    conn: DbConnection,
    sku: str,
    product_id: int,
    tenant_id: str | None = None,
) -> None:
    product_row = fetch_product_batch_row(conn, int(product_id), tenant_id=tenant_id)
    if product_row is None:
        raise ValueError(MSG_PRODUCT_LOT_NOT_FOUND)
    if (product_row["sku"] or "").strip() != sku:
        raise ValueError(MSG_PRODUCT_SKU_MISMATCH_BATCH)
    if product_row["deleted_at"]:
        raise ValueError(MSG_STOCK_RECEIPT_INACTIVE_LOT)


def _apply_stock_receipt_assert_sku_active(
    conn: DbConnection, sku: str, tenant_id: str | None = None
) -> None:
    sm_del = fetch_sku_master_deleted_flag(conn, sku, tenant_id=tenant_id)
    if sm_del and sm_del["deleted_at"]:
        raise ValueError(MSG_STOCK_RECEIPT_INACTIVE_SKU)


def _apply_stock_receipt_weighted_averages(
    conn: DbConnection,
    sku: str,
    qty: float,
    unit_cost: float,
    tenant_id: str | None = None,
) -> tuple[float, float, float, float, float, str]:
    ensure_sku_master(conn, sku, tenant_id=tenant_id)
    prev_total = sum_active_stock_by_sku(conn, sku, tenant_id=tenant_id)
    sku_master_row = fetch_sku_master_avg_unit_cost_row(conn, sku, tenant_id=tenant_id)
    prev_avg = float(sku_master_row["avg_unit_cost"] or 0.0)

    new_total = prev_total + qty
    new_avg = (
        ((prev_total * prev_avg) + (qty * float(unit_cost))) / new_total
        if new_total > 0
        else 0.0
    )
    total_entry_cost = round(qty * float(unit_cost), 2)
    now = datetime.now().isoformat(timespec="seconds")
    return prev_total, prev_avg, new_total, new_avg, total_entry_cost, now


def _apply_stock_receipt_write_mutations(
    conn: DbConnection,
    sku: str,
    product_id: int,
    qty: float,
    unit_cost: float,
    prev_total: float,
    new_total: float,
    prev_avg: float,
    new_avg: float,
    total_entry_cost: float,
    now: str,
    tenant_id: str | None = None,
) -> None:
    insert_stock_cost_entry(
        conn,
        sku=sku,
        product_id=int(product_id),
        qty=qty,
        unit_cost=float(unit_cost),
        total_entry_cost=total_entry_cost,
        prev_total=prev_total,
        new_total=new_total,
        prev_avg=prev_avg,
        new_avg=new_avg,
        now=now,
        tenant_id=tenant_id,
    )

    add_stock_to_product_row(conn, int(product_id), qty, tenant_id=tenant_id)
    set_products_cost_by_sku(conn, sku, new_avg, tenant_id=tenant_id)

    actual_total = sum_active_stock_by_sku(conn, sku, tenant_id=tenant_id)
    update_sku_master_stock_avg_and_timestamp(
        conn,
        sku=sku,
        total_stock=actual_total,
        avg_unit_cost=new_avg,
        now=now,
        tenant_id=tenant_id,
    )


def apply_stock_receipt(
    conn: DbConnection,
    sku: str,
    product_id: int,
    quantity: float,
    unit_cost: float,
    tenant_id: str | None = None,
) -> None:
    """
    Weighted-average inventory cost update for a stock receipt.
    New avg = ((prev_total * prev_avg) + (qty * unit_cost)) / (prev_total + qty)
    """
    qty = validate_stock_receipt_quantity_and_unit_cost(quantity, unit_cost)
    sku = sku.strip()

    _apply_stock_receipt_assert_product_batch(conn, sku, product_id, tenant_id)
    _apply_stock_receipt_assert_sku_active(conn, sku, tenant_id)

    prev_total, prev_avg, new_total, new_avg, total_entry_cost, now = (
        _apply_stock_receipt_weighted_averages(conn, sku, qty, unit_cost, tenant_id)
    )
    _apply_stock_receipt_write_mutations(
        conn,
        sku,
        product_id,
        qty,
        unit_cost,
        prev_total,
        new_total,
        prev_avg,
        new_avg,
        total_entry_cost,
        now,
        tenant_id,
    )


def update_sku_selling_price(
    sku: str,
    new_price: float,
    note: str = "",
    *,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> None:
    """Set selling price for a SKU (does not change inventory cost). History is appended."""
    require_nonempty_sku_before_selling_price(sku)
    require_positive_sku_list_price(new_price)
    sku = sku.strip()
    tid = effective_tenant_id_for_request(tenant_id)
    with connection_scope() as conn:
        row = fetch_sku_master_selling_price_row(conn, sku, tenant_id=tid)
        if row is None:
            raise ValueError(MSG_SKU_NOT_IN_STOCK_LINE)
        previous_selling_price = float(row["selling_price"] or 0.0)
        now = datetime.now().isoformat(timespec="seconds")
        insert_price_history_entry(
            conn,
            sku,
            previous_selling_price,
            float(new_price),
            now,
            note or "",
            tenant_id=tid,
        )
        update_sku_master_selling_price_updated_at(
            conn, float(new_price), now, sku, tenant_id=tid
        )
        update_products_price_where_sku(conn, float(new_price), sku, tenant_id=tid)
    log_critical_event(
        "price_change",
        user_id=user_id,
        channel="sku_selling_price",
        sku=sku,
        old_price=previous_selling_price,
        new_price=float(new_price),
        note=(note or "").strip() or None,
    )


def compute_sku_pricing_targets(
    avg_cost: float,
    markup_val: float,
    taxes_val: float,
    interest_val: float,
    *,
    markup_absolute: bool = False,
    taxes_absolute: bool = False,
    interest_absolute: bool = False,
) -> tuple[float, float, float]:
    """
    Fluxo de precificação.

    - Modo percentual: valores como número “cheio” (ex.: 10,5 = 10,5%).
    - Modo absoluto (R$): acréscimo em reais sobre a base imediata (CMP; depois o
      subtotal antes de impostos; depois o subtotal com impostos).
    """
    avg_cost_value = float(avg_cost)
    if markup_absolute:
        price_before = avg_cost_value + float(markup_val)
    else:
        markup_rate = float(markup_val) / 100.0
        price_before = avg_cost_value + (avg_cost_value * markup_rate)
    if taxes_absolute:
        price_with_taxes = price_before + float(taxes_val)
    else:
        tax_rate = float(taxes_val) / 100.0
        price_with_taxes = price_before + (price_before * tax_rate)
    if interest_absolute:
        target = price_with_taxes + float(interest_val)
    else:
        interest_rate = float(interest_val) / 100.0
        target = price_with_taxes + (price_with_taxes * interest_rate)
    return round(price_before, 2), round(price_with_taxes, 2), round(target, 2)


def _save_sku_pricing_normalize_inputs(
    sku: str,
    markup_pct: float,
    taxes_pct: float,
    interest_pct: float,
    *,
    markup_kind: int,
    taxes_kind: int,
    interest_kind: int,
) -> tuple[str, float, float, float, int, int, int]:
    sku = sku.strip()
    markup_pct = round(float(markup_pct), 2)
    taxes_pct = round(float(taxes_pct), 2)
    interest_pct = round(float(interest_pct), 2)
    mk = 1 if int(markup_kind) else 0
    tk = 1 if int(taxes_kind) else 0
    ik = 1 if int(interest_kind) else 0
    require_non_negative_sku_pricing_inputs(markup_pct, taxes_pct, interest_pct)
    return sku, markup_pct, taxes_pct, interest_pct, mk, tk, ik


def _save_sku_pricing_load_master_row(
    conn: DbConnection, sku: str, *, tenant_id: str | None = None
):
    row = fetch_sku_master_selling_and_avg_cost(conn, sku, tenant_id=tenant_id)
    if row is None:
        raise ValueError(MSG_SKU_NOT_IN_MASTER)
    return row


def _save_sku_pricing_targets_from_row(
    row,
    markup_pct: float,
    taxes_pct: float,
    interest_pct: float,
    mk: int,
    tk: int,
    ik: int,
) -> tuple[float, float, float, float, float]:
    avg_cost = float(row["avg_unit_cost"] or 0.0)
    if avg_cost <= 0:
        raise ValueError(MSG_CMP_NOT_AVAILABLE)
    old_sell = float(row["selling_price"] or 0.0)
    pb, pwt, target = compute_sku_pricing_targets(
        avg_cost,
        markup_pct,
        taxes_pct,
        interest_pct,
        markup_absolute=bool(mk),
        taxes_absolute=bool(tk),
        interest_absolute=bool(ik),
    )
    require_positive_computed_pricing_target(target)
    return avg_cost, old_sell, pb, pwt, target


def _save_sku_pricing_persist_all(
    conn: DbConnection,
    sku: str,
    *,
    avg_cost: float,
    markup_pct: float,
    taxes_pct: float,
    interest_pct: float,
    mk: int,
    tk: int,
    ik: int,
    pb: float,
    pwt: float,
    target: float,
    old_sell: float,
    now: str,
    tenant_id: str | None = None,
) -> int:
    deactivate_sku_pricing_records(conn, sku, tenant_id=tenant_id)
    new_id = insert_sku_pricing_record_active(
        conn,
        sku=sku,
        avg_cost=avg_cost,
        markup_pct=markup_pct,
        taxes_pct=taxes_pct,
        interest_pct=interest_pct,
        mk=mk,
        tk=tk,
        ik=ik,
        pb=pb,
        pwt=pwt,
        target=target,
        now=now,
        tenant_id=tenant_id,
    )
    apply_target_selling_price_to_master_products_history(
        conn,
        sku=sku,
        target=target,
        old_sell=old_sell,
        now=now,
        history_note="Pricing workflow (markup / taxes / interest)",
        tenant_id=tenant_id,
    )
    return new_id


def save_sku_pricing_workflow(
    sku: str,
    markup_pct: float,
    taxes_pct: float,
    interest_pct: float,
    *,
    markup_kind: int = 0,
    taxes_kind: int = 0,
    interest_kind: int = 0,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> int:
    """
    Append-only pricing record; deactivates prior rows for this SKU and sets the new row active.
    Applies target_price to sku_master.selling_price and products.price (sales use this price).

    ``*_kind``: 0 = valor em %, 1 = valor absoluto em R$ (armazenado nas colunas ``*_pct``).
    """
    sku, markup_pct, taxes_pct, interest_pct, mk, tk, ik = (
        _save_sku_pricing_normalize_inputs(
            sku,
            markup_pct,
            taxes_pct,
            interest_pct,
            markup_kind=markup_kind,
            taxes_kind=taxes_kind,
            interest_kind=interest_kind,
        )
    )

    tid = effective_tenant_id_for_request(tenant_id)
    with write_transaction() as conn:
        row = _save_sku_pricing_load_master_row(conn, sku, tenant_id=tid)
        avg_cost, old_sell, pb, pwt, target = _save_sku_pricing_targets_from_row(
            row,
            markup_pct,
            taxes_pct,
            interest_pct,
            mk,
            tk,
            ik,
        )
        now = datetime.now().isoformat(timespec="seconds")
        new_id = _save_sku_pricing_persist_all(
            conn,
            sku,
            avg_cost=avg_cost,
            markup_pct=markup_pct,
            taxes_pct=taxes_pct,
            interest_pct=interest_pct,
            mk=mk,
            tk=tk,
            ik=ik,
            pb=pb,
            pwt=pwt,
            target=target,
            old_sell=old_sell,
            now=now,
            tenant_id=tid,
        )
    log_critical_event(
        "price_change",
        user_id=user_id,
        channel="pricing_workflow",
        sku=sku,
        pricing_record_id=new_id,
        target_price=target,
        previous_selling_price=old_sell,
    )
    return new_id


def add_stock_receipt(
    sku: str,
    product_id: int,
    quantity: float,
    unit_cost: float,
    *,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> None:
    """Apply a stock receipt at SKU level (weighted-average inventory cost)."""
    tid = effective_tenant_id_for_request(tenant_id)
    with write_transaction() as conn:
        apply_stock_receipt(
            conn, sku, product_id, float(quantity), float(unit_cost), tid
        )


def _update_product_attrs_strip(
    frame_color: str,
    lens_color: str,
    style: str,
    palette: str,
    gender: str,
) -> tuple[str, str, str, str, str]:
    frame_color = (frame_color or "").strip()
    lens_color = (lens_color or "").strip()
    style = (style or "").strip()
    palette = (palette or "").strip()
    gender = (gender or "").strip()
    return frame_color, lens_color, style, palette, gender


def _update_product_attrs_load_product(
    conn: DbConnection,
    product_id: int,
    tenant_id: str | None = None,
) -> tuple[str, str]:
    row = fetch_product_name_sku_by_id(conn, int(product_id), tenant_id=tenant_id)
    if row is None:
        raise ValueError(MSG_PRODUCT_NOT_FOUND)
    name = str(row["name"] or "").strip()
    old_sku = str(row["sku"] or "").strip()
    return name, old_sku


def _update_product_attrs_resolve_new_sku(
    conn: DbConnection,
    product_id: int,
    name: str,
    old_sku: str,
    frame_color: str,
    lens_color: str,
    style: str,
    palette: str,
    gender: str,
    *,
    user_id: Optional[str] = None,
    tenant_id: str | None = None,
) -> str:
    base_sku = build_product_sku_body(
        name, frame_color, lens_color, gender, palette, style
    )
    if sku_base_body_exists(
        conn,
        base_sku,
        exclude_product_id=product_id,
        tenant_id=tenant_id,
    ):
        raise ValueError(DUPLICATE_SKU_BASE_ERROR_MSG)
    oparts = old_sku.split("-")
    if oparts and oparts[0].isdigit():
        return f"{oparts[0]}-{base_sku}"
    return generate_product_sku(
        name,
        frame_color,
        lens_color,
        gender,
        palette,
        style,
        exclude_product_id=product_id,
        user_id=user_id,
        tenant_id=tenant_id,
    )


def _update_product_attrs_assert_unique_sku(
    conn: DbConnection,
    product_id: int,
    new_sku: str,
    tenant_id: str | None = None,
) -> None:
    conflicting_product_row = fetch_other_product_with_sku(
        conn, new_sku, int(product_id), tenant_id=tenant_id
    )
    if conflicting_product_row is not None:
        raise ValueError(format_duplicate_sku_attr_conflict(new_sku))


def _update_product_attrs_execute_update(
    conn: DbConnection,
    product_id: int,
    frame_color: str,
    lens_color: str,
    style: str,
    palette: str,
    gender: str,
    new_sku: str,
    tenant_id: str | None = None,
) -> None:
    update_product_attributes_and_sku(
        conn,
        frame_color=frame_color,
        lens_color=lens_color,
        style=style,
        palette=palette,
        gender=gender,
        new_sku=new_sku,
        product_id=int(product_id),
        tenant_id=tenant_id,
    )


def update_product_attributes(
    product_id: int,
    frame_color: str,
    lens_color: str,
    style: str,
    palette: str,
    gender: str,
    *,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> None:
    """
    Update attributes and recalculate SKU from product name + attributes.
    Raises ValueError if another product already shares the same SKU base (body without SEQ),
    or the same full SKU.
    """
    (
        stripped_frame_color,
        stripped_lens_color,
        stripped_style,
        stripped_palette,
        stripped_gender,
    ) = _update_product_attrs_strip(
        frame_color, lens_color, style, palette, gender
    )
    tid = effective_tenant_id_for_request(tenant_id)
    with connection_scope() as conn:
        name, old_sku = _update_product_attrs_load_product(conn, product_id, tid)
        new_sku = _update_product_attrs_resolve_new_sku(
            conn,
            product_id,
            name,
            old_sku,
            stripped_frame_color,
            stripped_lens_color,
            stripped_style,
            stripped_palette,
            stripped_gender,
            user_id=user_id,
            tenant_id=tid,
        )
        _update_product_attrs_assert_unique_sku(conn, product_id, new_sku, tid)
        _update_product_attrs_execute_update(
            conn,
            product_id,
            stripped_frame_color,
            stripped_lens_color,
            stripped_style,
            stripped_palette,
            stripped_gender,
            new_sku,
            tid,
        )


def generate_product_sku(
    product_name: str,
    frame_color: str,
    lens_color: str,
    gender: str,
    palette: str,
    style: str,
    *,
    exclude_product_id: Optional[int] = None,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> str:
    """
    SKU completo: [SEQ]-[PP]-[FC]-[LC]-[GG]-[PA]-[ST]. SEQ = contador persistente (001+).
    """
    tid = effective_tenant_id_for_request(tenant_id)
    with write_transaction(immediate=True) as conn:
        body = build_product_sku_body(
            product_name, frame_color, lens_color, gender, palette, style
        )
        if sku_base_body_exists(
            conn,
            body,
            exclude_product_id=exclude_product_id,
            tenant_id=tid,
        ):
            raise ValueError(DUPLICATE_SKU_BASE_ERROR_MSG)
        next_sequence = _next_sku_sequence(conn, tid)
        full_sku = f"{format_sku_sequence_int(next_sequence)}-{body}"
    return full_sku


def _save_sku_cost_assert_master_and_ensure_rows(
    conn: DbConnection,
    sku: str,
    tenant_id: str | None = None,
) -> None:
    if sku_master_exists(conn, sku, tenant_id=tenant_id) is None:
        raise ValueError(MSG_SKU_NOT_IN_MASTER)
    ensure_sku_cost_component_rows(conn, sku, tenant_id=tenant_id)


def _save_sku_cost_apply_component_lines(
    conn: DbConnection,
    sku: str,
    component_inputs: list,
    now: str,
    tenant_id: str | None = None,
) -> None:
    for component_key, unit_price, quantity in component_inputs:
        unit_price = round(float(unit_price), 2)
        quantity = round(float(quantity), 4)
        require_non_negative_cost_component_line(unit_price, quantity)
        line_total = round(unit_price * quantity, 2)
        update_sku_cost_component_line(
            conn,
            sku,
            component_key,
            unit_price,
            quantity,
            line_total,
            now,
            tenant_id=tenant_id,
        )


def save_sku_cost_structure(
    sku: str,
    component_inputs: list,
    *,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> float:
    """
    Persist component lines. component_inputs: list of (component_key, unit_price, unit_quantity).
    Returns stored structured total SKU cost.
    """
    sku = sku.strip()
    tid = effective_tenant_id_for_request(tenant_id)
    with write_transaction() as conn:
        _save_sku_cost_assert_master_and_ensure_rows(conn, sku, tenant_id=tid)
        now = datetime.now().isoformat(timespec="seconds")
        _save_sku_cost_apply_component_lines(
            conn, sku, component_inputs, now, tenant_id=tid
        )
        total = recompute_sku_structured_cost_total(conn, sku, tenant_id=tid)
    return float(total)


def _add_product_prepare_identity_and_validate(
    name: str,
    registered_date,
    frame_color: str,
    lens_color: str,
    style: str,
    palette: str,
    gender: str,
    stock: float,
    unit_cost: float,
) -> tuple[str, str, str, str, str, str, str]:
    product_enter_code = make_product_enter_code(
        product_name=name, registered_date=registered_date
    )
    name = name.strip()
    frame_color = (frame_color or "").strip()
    lens_color = (lens_color or "").strip()
    style = (style or "").strip()
    palette = (palette or "").strip()
    gender = (gender or "").strip()

    require_add_product_stock_and_unit_cost_consistency(stock, unit_cost)

    return (
        product_enter_code,
        name,
        frame_color,
        lens_color,
        style,
        palette,
        gender,
    )


def _add_product_select_existing_same_batch(
    conn: DbConnection,
    name: str,
    registered_date_text: str,
    frame_color: str,
    lens_color: str,
    style: str,
    palette: str,
    gender: str,
    tenant_id: str | None = None,
):
    return fetch_same_batch_product_row(
        conn,
        name,
        registered_date_text,
        frame_color,
        lens_color,
        style,
        palette,
        gender,
        tenant_id=tenant_id,
    )


def _add_product_insert_fresh_lot(
    conn: DbConnection,
    *,
    name: str,
    registered_date_text: str,
    product_enter_code: str,
    frame_color: str,
    lens_color: str,
    style: str,
    palette: str,
    gender: str,
    stock: float,
    unit_cost: float,
    product_image_bytes: Optional[bytes],
    product_image_filename: str,
    tenant_id: str | None = None,
) -> None:
    tid = effective_tenant_id_for_request(tenant_id)
    body = build_product_sku_body(
        name, frame_color, lens_color, gender, palette, style
    )
    if sku_base_body_exists(conn, body, tenant_id=tid):
        raise ValueError(DUPLICATE_SKU_BASE_ERROR_MSG)
    next_sequence = _next_sku_sequence(conn, tid)
    sku = f"{format_sku_sequence_int(next_sequence)}-{body}"
    existing_sku_row = fetch_product_id_by_sku(conn, sku, tenant_id=tid)
    if existing_sku_row is not None:
        raise ValueError(format_sku_already_exists(sku))
    created_now = datetime.now().isoformat(timespec="seconds")
    pid = insert_product_zero_stock_row(
        conn,
        name=name,
        sku=sku,
        registered_date_text=registered_date_text,
        product_enter_code=product_enter_code,
        frame_color=frame_color,
        lens_color=lens_color,
        style=style,
        palette=palette,
        gender=gender,
        created_at=created_now,
        tenant_id=tid,
    )
    if product_image_bytes:
        rel_img = save_product_image_file(
            pid,
            product_image_bytes,
            product_image_filename or "foto.jpg",
        )
        update_product_image_path_by_id(conn, rel_img, pid, tenant_id=tid)
    if float(stock) > 0:
        ensure_sku_master(conn, sku, tenant_id=tid)
        apply_stock_receipt(conn, sku, pid, float(stock), float(unit_cost), tid)
    else:
        ensure_sku_master(conn, sku, tenant_id=tid)


def add_product(
    name: str,
    stock: float,
    registered_date,
    frame_color: str,
    lens_color: str,
    style: str,
    palette: str,
    gender: str,
    unit_cost: float,
    *,
    product_image_bytes: Optional[bytes] = None,
    product_image_filename: str = "",
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> str:
    """
    Registra um lote. SKU: [SEQ]-[PP]-[FC]-[LC]-[GG]-[PA]-[ST].

    Product registration typically uses stock=0; add stock via the Costing page (stock receipts).
    If stock > 0 here, unit_cost must be > 0 (weighted-average receipt).

    Não insere novo lote se já existir lote com o mesmo nome + data + atributos, nem se já existir
    o mesmo corpo de SKU (atributos), ignorando apenas o prefixo numérico SEQ.

    Returns the product enter code (slug + date). Raises ValueError or sqlite errors if not mergeable / DB fails.
    """
    (
        product_enter_code,
        name,
        frame_color,
        lens_color,
        style,
        palette,
        gender,
    ) = _add_product_prepare_identity_and_validate(
        name,
        registered_date,
        frame_color,
        lens_color,
        style,
        palette,
        gender,
        stock,
        unit_cost,
    )

    tid = effective_tenant_id_for_request(tenant_id)
    with write_transaction(immediate=True) as conn:
        registered_date_text = registered_date.isoformat()
        existing = _add_product_select_existing_same_batch(
            conn,
            name,
            registered_date_text,
            frame_color,
            lens_color,
            style,
            palette,
            gender,
            tenant_id=tid,
        )

        if existing is not None:
            # Mesmo lote (nome + data + atributos): não re-cadastrar; evita "sucesso" sem linha nova.
            raise ValueError(DUPLICATE_SKU_BASE_ERROR_MSG)
        _add_product_insert_fresh_lot(
            conn,
            name=name,
            registered_date_text=registered_date_text,
            product_enter_code=product_enter_code,
            frame_color=frame_color,
            lens_color=lens_color,
            style=style,
            palette=palette,
            gender=gender,
            stock=stock,
            unit_cost=unit_cost,
            product_image_bytes=product_image_bytes,
            product_image_filename=product_image_filename,
            tenant_id=tid,
        )
    return product_enter_code


def set_product_pricing(
    product_id: int,
    cost: float,
    price: float,
    *,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> None:
    tid = effective_tenant_id_for_request(tenant_id)
    with connection_scope() as conn:
        update_product_cost_price_by_id(conn, cost, price, product_id, tenant_id=tid)
    log_critical_event(
        "price_change",
        user_id=user_id,
        channel="product_row",
        product_id=product_id,
        cost=cost,
        price=price,
    )


def set_product_pricing_for_batch(
    product_name: str,
    sku: str,
    registered_date_text: str,
    cost: float,
    price: float,
    *,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> int:
    """
    Freeze cost/price for all rows that belong to the same "batch":
    (product name + registered date + SKU) and still have stock in inventory.

    - cost: subtotal cost from the pricing worksheet (sum of lines).
    - price: **final unit price** from pricing (incl. markup, taxes & interest) — used for Sales and stock value.

    Returns how many product rows were updated.
    """
    tid = effective_tenant_id_for_request(tenant_id)
    with connection_scope() as conn:
        # If there's already a priced in-stock batch for this code,
        # we must not overwrite it (unless the batch was excluded from stock/reset).
        locked = count_instock_locked_batch_rows(
            conn, product_name, sku, registered_date_text, tenant_id=tid
        )

        if int(locked) > 0:
            return -1

        rows_updated = update_instock_batch_pricing_lock(
            conn,
            cost,
            price,
            product_name,
            sku,
            registered_date_text,
            tenant_id=tid,
        )
        log_critical_event(
            "price_change",
            user_id=user_id,
            channel="batch_pricing_lock",
            product_name=product_name,
            sku=sku,
            registered_date=registered_date_text,
            rows_updated=rows_updated,
            cost=cost,
            price=price,
        )
        return rows_updated


def reset_batch_pricing_and_exclude(
    product_enter_code: str,
    *,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> int:
    """
    Exclude the batch from stock and clear its pricing so it can be repriced later.
    Syncs SKU-level total_stock after stock is cleared.
    """
    tid = effective_tenant_id_for_request(tenant_id)
    with connection_scope() as conn:
        skus = [
            str(r["sku"]).strip()
            for r in fetch_distinct_skus_for_enter_code(
                conn, product_enter_code, tenant_id=tid
            )
        ]
        updated_row_count = reset_stock_cost_price_unlock_by_enter_code(
            conn, product_enter_code, tenant_id=tid
        )
        for sku in skus:
            sync_sku_master_totals(conn, sku, tenant_id=tid)
        log_critical_event(
            "data_deletion",
            user_id=user_id,
            entity="batch_stock_and_pricing_reset",
            product_enter_code=product_enter_code,
            rows_cleared=updated_row_count,
            skus_affected=",".join(skus) if skus else "",
        )
        return updated_row_count


def clear_batch_pricing_only(
    product_enter_code: str,
    *,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> int:
    """Clear cost/price only (keep stock as-is) for the given entering code."""
    tid = effective_tenant_id_for_request(tenant_id)
    with connection_scope() as conn:
        n_cleared = clear_cost_price_unlock_by_enter_code(
            conn, product_enter_code, tenant_id=tid
        )
        log_critical_event(
            "data_deletion",
            user_id=user_id,
            entity="batch_pricing_fields_cleared",
            product_enter_code=product_enter_code,
            rows_updated=n_cleared,
        )
        return n_cleared


def apply_manual_stock_write_down(
    product_id: int,
    quantity: float,
    *,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> float:
    """Baixa manual de stock do lote: apenas reduz ``products.stock``; custo e preço inalterados."""
    tid = effective_tenant_id_for_request(tenant_id)
    with write_transaction() as conn:
        new_stock = decrement_product_stock_manual(
            conn, int(product_id), float(quantity), tenant_id=tid
        )
    log_critical_event(
        "STOCK_MANUAL_WRITE_DOWN",
        user_id=user_id,
        product_id=int(product_id),
        quantity=float(quantity),
        stock_after=new_stock,
    )
    return new_stock
