import re
from typing import Optional

from database.constants import SALE_PAYMENT_OPTIONS
from utils.error_messages import (
    MSG_COMPONENT_UNIT_PRICE_QTY_NON_NEGATIVE,
    MSG_DISCOUNT_NON_NEGATIVE,
    MSG_LIST_PRICE_MUST_BE_POSITIVE,
    MSG_MARGIN_TAXES_CHARGES_NON_NEGATIVE,
    MSG_PAYMENT_METHOD_INVALID,
    MSG_PAYMENT_METHOD_REQUIRED,
    MSG_PRODUCT_NAME_REQUIRED,
    MSG_QTY_MUST_BE_POSITIVE,
    MSG_SKU_REQUIRED,
    MSG_STOCK_CANNOT_BE_NEGATIVE,
    MSG_STOCK_REQUIRES_POSITIVE_UNIT_COST,
    MSG_TARGET_PRICE_MUST_BE_POSITIVE,
    MSG_UNIT_COST_MUST_BE_POSITIVE,
)

# Alinhado a app.SELECT_LABEL / OTHER_LABEL (evita import circular).
SELECT_LABEL = "Selecione"
OTHER_LABEL = "Outro"


def dropdown_with_other(base_options):
    """[…opções…, 'Outro'] — 'Outro' é opção normal (valor literal salvo); placeholder no select."""
    return list(base_options) + [OTHER_LABEL]


def attribute_select_index(options, current_value) -> Optional[int]:
    """Índice do selectbox a partir do valor do BD, ou None = mostrar placeholder. Valores fora da lista → Outro."""
    value_stripped = (current_value or "").strip()
    if not value_stripped or value_stripped == SELECT_LABEL:
        return None
    if value_stripped in options:
        return options.index(value_stripped)
    if OTHER_LABEL in options:
        return options.index(OTHER_LABEL)
    return None


def resolve_attribute_value(choice, other_text, field_label):
    """
    Returns (value_or_none, error_message_or_none).

    Se "Outro" for selecionado, grava o rótulo literal (sem campo de texto extra).
    """
    if choice is None:
        return None, f"Selecione {field_label}."
    if choice == OTHER_LABEL:
        other_stripped = (other_text or "").strip()
        if other_stripped:
            return other_stripped, None
        return OTHER_LABEL, None
    return choice, None


def sanitize_cep_digits(cep: str) -> str:
    return re.sub(r"\D", "", cep or "")


def normalize_cpf_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_phone_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def validate_cpf_br(value: str) -> bool:
    """Brazil CPF check digits (returns False if empty after strip)."""
    cpf = normalize_cpf_digits(value)
    if len(cpf) != 11:
        return False
    if cpf == cpf[0] * 11:
        return False

    def calc_digit(base: str, factor_start: int) -> int:
        total = 0
        for i, ch in enumerate(base):
            total += int(ch) * (factor_start - i)
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    d1 = calc_digit(cpf[:9], 10)
    if int(cpf[9]) != d1:
        return False
    d2 = calc_digit(cpf[:9] + str(d1), 11)
    return int(cpf[10]) == d2


def validate_email_optional(email: str) -> bool:
    email_stripped = (email or "").strip()
    if not email_stripped:
        return True
    return bool(
        re.match(
            r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
            email_stripped,
        )
    )


def filter_customers_by_search(rows: list, query: str) -> list:
    """Filter customer rows by substring on name or customer_code (case-insensitive)."""
    needle = (query or "").strip().lower()
    if not needle:
        return list(rows)
    matching = []
    for row in rows:
        code = str(row["customer_code"] or "").lower()
        name = str(row["name"] or "").lower()
        if needle in code or needle in name:
            matching.append(row)
    return matching


def parse_cost_quantity_text(raw: str) -> tuple[float, Optional[str]]:
    """Non-negative quantity, up to 4 decimal places. Empty -> 0."""
    s = (raw or "").strip().replace(",", ".")
    if s == "":
        return 0.0, None
    for c in s:
        if c not in "0123456789.":
            return 0.0, "Use apenas dígitos e um ponto decimal."
    if s.count(".") > 1:
        return 0.0, "Permitido apenas um ponto decimal."
    if s == ".":
        return 0.0, None
    parts = s.split(".")
    if len(parts) == 2 and len(parts[1]) > 4:
        return 0.0, "No máximo 4 casas decimais na quantidade."
    try:
        quantity_value = float(s)
    except ValueError:
        return 0.0, "Número inválido."
    if quantity_value < 0:
        return 0.0, "A quantidade não pode ser negativa."
    return round(quantity_value, 4), None


def parse_cost_unit_price_value(value: float) -> tuple[float, Optional[str]]:
    """Unit price: non-negative, rounded to 2 decimals."""
    try:
        unit_price_value = float(value)
    except (TypeError, ValueError):
        return 0.0, "Preço unitário inválido."
    if unit_price_value < 0:
        return 0.0, "Preço unitário não pode ser negativo."
    return round(unit_price_value, 2), None


def _sku_search_sanitize_text(raw_query: str) -> str:
    """Lowercase substring for LIKE; strip wildcard chars to avoid pattern injection."""
    return (raw_query or "").strip().lower().replace("%", "").replace("_", "")


def require_positive_integer_sale_quantity(quantity: int) -> int:
    qty = int(quantity)
    if qty < 1:
        raise ValueError(MSG_QTY_MUST_BE_POSITIVE)
    return qty


def validate_stock_receipt_quantity_and_unit_cost(
    quantity: float, unit_cost: float
) -> float:
    qty = round(float(quantity), 4)
    if qty <= 0:
        raise ValueError(MSG_QTY_MUST_BE_POSITIVE)
    if unit_cost <= 0:
        raise ValueError(MSG_UNIT_COST_MUST_BE_POSITIVE)
    return qty


def require_non_negative_sale_discount(discount_amount) -> float:
    discount = float(discount_amount)
    if discount < 0:
        raise ValueError(MSG_DISCOUNT_NON_NEGATIVE)
    return discount


def normalize_and_require_sale_payment_method(payment_method: str) -> str:
    method_stripped = (payment_method or "").strip()
    if not method_stripped:
        raise ValueError(MSG_PAYMENT_METHOD_REQUIRED)
    if method_stripped not in SALE_PAYMENT_OPTIONS:
        raise ValueError(MSG_PAYMENT_METHOD_INVALID)
    return method_stripped


def require_nonempty_sku_before_selling_price(sku: str) -> None:
    if not sku or not str(sku).strip():
        raise ValueError(MSG_SKU_REQUIRED)


def require_positive_sku_list_price(new_price: float) -> None:
    if new_price <= 0:
        raise ValueError(MSG_LIST_PRICE_MUST_BE_POSITIVE)


def require_add_product_stock_and_unit_cost_consistency(stock, unit_cost) -> None:
    if float(stock) > 0 and float(unit_cost) <= 0:
        raise ValueError(MSG_STOCK_REQUIRES_POSITIVE_UNIT_COST)
    if float(stock) < 0:
        raise ValueError(MSG_STOCK_CANNOT_BE_NEGATIVE)


def require_non_negative_sku_pricing_inputs(
    markup_pct: float, taxes_pct: float, interest_pct: float
) -> None:
    if markup_pct < 0 or taxes_pct < 0 or interest_pct < 0:
        raise ValueError(MSG_MARGIN_TAXES_CHARGES_NON_NEGATIVE)


def require_non_negative_cost_component_line(unit_price: float, quantity: float) -> None:
    if unit_price < 0 or quantity < 0:
        raise ValueError(MSG_COMPONENT_UNIT_PRICE_QTY_NON_NEGATIVE)


def require_positive_computed_pricing_target(target: float) -> None:
    if target <= 0:
        raise ValueError(MSG_TARGET_PRICE_MUST_BE_POSITIVE)


def require_non_empty_product_name(name: str) -> None:
    if not name:
        raise ValueError(MSG_PRODUCT_NAME_REQUIRED)
