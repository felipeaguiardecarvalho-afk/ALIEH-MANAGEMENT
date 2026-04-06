from datetime import datetime
from typing import Optional

# Alinhado a app.CURRENCY_SYMBOL (evita import circular).
CURRENCY_SYMBOL = "R$"


def format_qty_display_4(q: float) -> str:
    """Format quantity for text inputs; empty string means zero."""
    v = round(float(q), 4)
    if abs(v) < 1e-12:
        return ""
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


def format_money(value: float) -> str:
    """Formata valor em pt-BR (ex.: R$ 1.234,56)."""
    try:
        v = float(value)
    except TypeError:
        v = float(value)
    sign = "-" if v < 0 else ""
    v = abs(v)
    s = f"{v:,.2f}"
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{sign}{CURRENCY_SYMBOL} {s}"


def format_product_created_display(iso_val: Optional[str]) -> str:
    """Format products.created_at (ISO) for tables; legacy rows may be empty."""
    if iso_val is None:
        return "—"
    s = str(iso_val).strip()
    if not s:
        return "—"
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return s
