"""Geração de corpo de SKU e sequência numérica persistente."""

from __future__ import annotations

import re
import sqlite3


def _sku_alphanumeric_clean(text: object) -> str:
    # Session/widget state can occasionally be non-str; re.sub requires a string.
    s = "" if text is None else str(text)
    return re.sub(r"[^A-Za-z0-9]", "", s).upper()


def sku_segment_two_chars(source: str) -> str:
    c = _sku_alphanumeric_clean(source)
    if len(c) == 0:
        return "XX"
    if len(c) == 1:
        return c + "X"
    return c[:2]


def sku_color_segment_two_chars(color: object) -> str:
    raw = ("" if color is None else str(color)).strip()
    parts = [p.strip() for p in raw.split("/")]
    parts = [p for p in parts if p]
    if len(parts) >= 2:
        first = _sku_alphanumeric_clean(parts[0])
        second = _sku_alphanumeric_clean(parts[1])
        if first and second:
            return (first[0] + second[0])[:2]
    return sku_segment_two_chars(raw)


def format_sku_sequence_int(n: int) -> str:
    n = int(n)
    if n <= 999:
        return f"{n:03d}"
    return str(n)


def build_product_sku_body(
    product_name: object,
    frame_color: object,
    lens_color: object,
    gender: object,
    palette: object,
    style: object,
) -> str:
    """
    Corpo do SKU (sem SEQ): [PP]-[FC]-[LC]-[GG]-[PA]-[ST].
    FC = cor da armação, LC = cor da lente (dois caracteres cada, mesmas regras de segmento).
    """
    pp = sku_segment_two_chars("" if product_name is None else str(product_name))
    fc = sku_color_segment_two_chars(frame_color)
    lc = sku_color_segment_two_chars(lens_color)
    gg = sku_segment_two_chars("" if gender is None else str(gender))
    pa = sku_segment_two_chars("" if palette is None else str(palette))
    seg_st = sku_segment_two_chars("" if style is None else str(style))
    return f"{pp}-{fc}-{lc}-{gg}-{pa}-{seg_st}"


def _next_sku_sequence(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        """
        UPDATE sku_sequence_counter
        SET last_value = last_value + 1
        WHERE id = 1
        RETURNING last_value;
        """
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("Contador de sequência de SKU não inicializado.")
    return int(row["last_value"])


def sync_sku_sequence_counter_from_skus(conn: sqlite3.Connection) -> None:
    max_n = 0
    for row in conn.execute(
        "SELECT sku FROM products WHERE sku IS NOT NULL AND TRIM(sku) != '';"
    ):
        parts = str(row["sku"]).strip().split("-")
        if parts and parts[0].isdigit():
            try:
                max_n = max(max_n, int(parts[0]))
            except ValueError:
                pass
    for row in conn.execute(
        "SELECT sku FROM sku_master WHERE sku IS NOT NULL AND TRIM(sku) != '';"
    ):
        parts = str(row["sku"]).strip().split("-")
        if parts and parts[0].isdigit():
            try:
                max_n = max(max_n, int(parts[0]))
            except ValueError:
                pass
    row = conn.execute(
        "SELECT last_value FROM sku_sequence_counter WHERE id = 1;"
    ).fetchone()
    cur = int(row["last_value"] or 0) if row else 0
    conn.execute(
        "UPDATE sku_sequence_counter SET last_value = ? WHERE id = 1;",
        (max(max_n, cur),),
    )
