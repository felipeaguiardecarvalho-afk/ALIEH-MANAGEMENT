import json
import math
import os
import re
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import streamlit as st


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "business.db"

CURRENCY_SYMBOL = "$"

# Planned SKU cost breakdown (extend by appending (stable_key, display_label) tuples).
SKU_COST_COMPONENT_DEFINITIONS = [
    ("glasses", "Glasses"),
    ("purchase_packaging", "Purchase Packaging"),
    ("purchase_freight", "Purchase Freight"),
    ("glasses_pouch", "Glasses Pouch"),
    ("retail_box", "Retail Box"),
    ("cleaning_cloth", "Cleaning Cloth"),
]

# Product registration — dropdown options
PRODUCT_GENDER_OPTIONS = ["Male", "Female", "Unisex"]

PRODUCT_PALETTE_OPTIONS = [
    "Spring",
    "Summer",
    "Autumn",
    "Winter",
]

# Frame / product style (dropdown on registration)
PRODUCT_STYLE_OPTIONS = [
    "Aviator",
    "Wayfarer",
    "Round",
    "Square",
    "Rectangle",
    "Cat Eye",
    "Oversized",
    "Butterfly",
    "Hexagonal",
    "Geometric",
    "Clubmaster",
    "Oval",
    "P3",
    "Retro",
    "Wraparound",
    "Shield",
    "Sport",
    "Flat Top",
    "Rimless",
    "Semi Rimless",
    "Narrow",
    "Futuristic",
]

# Standard product colors (simple names + common variations)
PRODUCT_COLOR_OPTIONS = [
    "Black",
    "Black / Matte",
    "Black / Gloss",
    "White",
    "White / Pearl",
    "Ivory",
    "Off-white",
    "Gray",
    "Gray / Light",
    "Gray / Charcoal",
    "Silver",
    "Silver / Metallic",
    "Gold",
    "Gold / Rose",
    "Rose Gold",
    "Copper",
    "Bronze",
    "Champagne",
    "Navy",
    "Navy / Midnight",
    "Royal Blue",
    "Sky Blue",
    "Blue / Cobalt",
    "Steel Blue",
    "Teal",
    "Turquoise",
    "Aqua",
    "Green",
    "Forest Green",
    "Olive Green",
    "Emerald",
    "Mint",
    "Sage",
    "Red",
    "Burgundy",
    "Wine",
    "Crimson",
    "Coral",
    "Pink",
    "Blush Pink",
    "Rose",
    "Magenta",
    "Purple",
    "Lavender",
    "Plum",
    "Violet",
    "Brown",
    "Tan / Beige",
    "Camel",
    "Khaki",
    "Taupe",
    "Coffee",
    "Chocolate",
    "Yellow",
    "Mustard",
    "Orange",
    "Peach",
    "Apricot",
    "Tortoise",
    "Tortoise / Havana",
    "Havana",
    "Honey",
    "Crystal",
    "Clear",
    "Transparent / Smoke",
    "Gradient / Gray",
    "Gradient / Brown",
    "Mirrored / Silver",
    "Mirrored / Blue",
    "Mirrored / Gold",
    "Matte",
    "Opaque",
]

# Dropdown UX: "Select" is placeholder text only (grey), not a real option; last option is "Other" (literal value)
SELECT_LABEL = "Select"
OTHER_LABEL = "Other"


def dropdown_with_other(base_options):
    """[…options…, 'Other'] — 'Other' is a normal option (stored as the label); use placeholder for hint text."""
    return list(base_options) + [OTHER_LABEL]


def attribute_select_index(options, current_value) -> Optional[int]:
    """Index for selectbox from DB value, or None = show placeholder. Custom values → Other."""
    cur = (current_value or "").strip()
    if not cur or cur == SELECT_LABEL:
        return None
    if cur in options:
        return options.index(cur)
    if OTHER_LABEL in options:
        return options.index(OTHER_LABEL)
    return None


def attribute_selectbox(label: str, options: list, *, key: str, current_value: str = "") -> object:
    """
    Selectbox with grey placeholder 'Select' when nothing chosen (Streamlit 1.29+).
    Returns None until the user picks a real option.
    """
    idx = attribute_select_index(options, current_value)
    if idx is None:
        return st.selectbox(
            label,
            options=options,
            index=None,
            placeholder=SELECT_LABEL,
            key=key,
        )
    return st.selectbox(
        label,
        options=options,
        index=idx,
        key=key,
    )


def resolve_attribute_value(choice, other_text, field_label):
    """
    Returns (value_or_none, error_message_or_none).

    If "Other" is selected, stores the literal label **Other** (no separate text field).
    If other_text is non-empty (legacy), it is still used when choice is Other.
    """
    if choice is None:
        return None, f"Please select {field_label}."
    if choice == OTHER_LABEL:
        t = (other_text or "").strip()
        if t:
            return t, None
        return OTHER_LABEL, None
    return choice, None


def _sku_alphanumeric_clean(text: str) -> str:
    """Strip spaces and special characters; keep letters and digits only; uppercase."""
    return re.sub(r"[^A-Za-z0-9]", "", text or "").upper()


def sku_segment_two_chars(source: str) -> str:
    """
    One SKU segment: exactly 2 uppercase alphanumeric characters.
    Empty / null → XX; one character → pad with X.
    """
    c = _sku_alphanumeric_clean(source)
    if len(c) == 0:
        return "XX"
    if len(c) == 1:
        return c + "X"
    return c[:2]


def sku_color_segment_two_chars(color: str) -> str:
    """
    Color segment: exactly 2 uppercase alphanumeric characters.
    If the value contains '/' with two non-empty sides (spaces around '/' ignored),
    use first letter of the first word + first letter of the second word.
    Otherwise use the standard rule (first two characters after alphanumeric clean).
    """
    raw = (color or "").strip()
    parts = [p.strip() for p in raw.split("/")]
    parts = [p for p in parts if p]
    if len(parts) >= 2:
        first = _sku_alphanumeric_clean(parts[0])
        second = _sku_alphanumeric_clean(parts[1])
        if first and second:
            return (first[0] + second[0])[:2]
    return sku_segment_two_chars(raw)


def format_sku_sequence_int(n: int) -> str:
    """3-digit zero padding up to 999; beyond that use full integer string (1000, 1001, ...)."""
    n = int(n)
    if n <= 999:
        return f"{n:03d}"
    return str(n)


def build_product_sku_body(
    product_name: str,
    color: str,
    gender: str,
    palette: str,
    style: str,
) -> str:
    """
    Body only: [PP]-[CC]-[GG]-[PA]-[ST] (5 segments × 2 chars).
    PP=name, CC=color, GG=gender, PA=palette, ST=style.
    """
    pp = sku_segment_two_chars(product_name or "")
    cc = sku_color_segment_two_chars(color or "")
    gg = sku_segment_two_chars(gender or "")
    pa = sku_segment_two_chars(palette or "")
    seg_st = sku_segment_two_chars(style or "")
    return f"{pp}-{cc}-{gg}-{pa}-{seg_st}"


def _next_sku_sequence(conn: sqlite3.Connection) -> int:
    """
    Atomically increment persistent SKU sequence and return the new value.
    Use inside BEGIN IMMEDIATE (e.g. add_product / generate_product_sku) for cross-connection safety.
    """
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
        raise RuntimeError("sku_sequence_counter is not initialized.")
    return int(row["last_value"])


def format_customer_code(n: int) -> str:
    """5-digit zero-padded customer code (00001, …)."""
    return f"{int(n):05d}"


def _next_customer_sequence(conn: sqlite3.Connection) -> int:
    """Atomically increment persistent customer sequence and return the new value."""
    cur = conn.execute(
        """
        UPDATE customer_sequence_counter
        SET last_value = last_value + 1
        WHERE id = 1
        RETURNING last_value;
        """
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("customer_sequence_counter is not initialized.")
    return int(row["last_value"])


def sync_customer_sequence_counter_from_customers(conn: sqlite3.Connection) -> None:
    """Ensure last_value is at least the highest numeric customer_code."""
    row = conn.execute(
        """
        SELECT MAX(CAST(customer_code AS INTEGER)) AS m
        FROM customers
        WHERE customer_code GLOB '[0-9][0-9][0-9][0-9][0-9]';
        """
    ).fetchone()
    max_n = int(row["m"] or 0) if row else 0
    r2 = conn.execute(
        "SELECT last_value FROM customer_sequence_counter WHERE id = 1;"
    ).fetchone()
    cur = int(r2["last_value"] or 0) if r2 else 0
    conn.execute(
        "UPDATE customer_sequence_counter SET last_value = ? WHERE id = 1;",
        (max(max_n, cur),),
    )


def sanitize_cep_digits(cep: str) -> str:
    return re.sub(r"\D", "", cep or "")


def fetch_viacep_address(cep: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    ViaCEP lookup. Returns (payload, error_message).
    payload keys: street, neighborhood, city, state.
    """
    digits = sanitize_cep_digits(cep)
    if len(digits) != 8:
        return None, "CEP must have exactly 8 digits."
    url = f"https://viacep.com.br/ws/{digits}/json/"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ALIEH-management/1.0"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        if data.get("erro"):
            return None, "CEP not found (ViaCEP)."
        return (
            {
                "street": (data.get("logradouro") or "").strip(),
                "neighborhood": (data.get("bairro") or "").strip(),
                "city": (data.get("localidade") or "").strip(),
                "state": (data.get("uf") or "").strip(),
            },
            None,
        )
    except urllib.error.HTTPError as e:
        return None, f"CEP lookup failed (HTTP {e.code})."
    except urllib.error.URLError as e:
        return None, f"CEP lookup failed: {e.reason}"
    except Exception as e:
        return None, f"CEP lookup failed: {e}"


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
    s = (email or "").strip()
    if not s:
        return True
    return bool(
        re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", s)
    )


def find_customer_duplicate(
    conn: sqlite3.Connection,
    cpf_digits: str,
    phone_digits: str,
    exclude_id: Optional[int] = None,
) -> Optional[Tuple[str, sqlite3.Row]]:
    """
    If cpf_digits or phone_digits is non-empty, check for another row with same value.
    Returns ("cpf"|"phone", row) or None.
    """
    if cpf_digits:
        q = "SELECT id, customer_code, name, cpf, phone FROM customers WHERE cpf = ?"
        params: list = [cpf_digits]
        if exclude_id is not None:
            q += " AND id != ?"
            params.append(exclude_id)
        row = conn.execute(q, params).fetchone()
        if row:
            return ("cpf", row)
    if phone_digits:
        q = "SELECT id, customer_code, name, cpf, phone FROM customers WHERE phone = ?"
        params = [phone_digits]
        if exclude_id is not None:
            q += " AND id != ?"
            params.append(exclude_id)
        row = conn.execute(q, params).fetchone()
        if row:
            return ("phone", row)
    return None


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
) -> str:
    """Allocate customer_code, insert row. Returns new customer_code."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE;")
        try:
            dup = find_customer_duplicate(conn, cpf or "", phone or "", None)
            if dup:
                kind, row = dup
                conn.execute("ROLLBACK;")
                label = "CPF" if kind == "cpf" else "phone number"
                raise ValueError(
                    f"Duplicate {label}: already used by customer **{row['customer_code']}** — {row['name']}."
                )
            n = _next_customer_sequence(conn)
            code = format_customer_code(n)
            conn.execute(
                """
                INSERT INTO customers (
                    customer_code, name, cpf, rg, phone, email, instagram,
                    zip_code, street, number, neighborhood, city, state, country,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    code,
                    name.strip(),
                    cpf or None,
                    rg or None,
                    phone or None,
                    email or None,
                    instagram or None,
                    zip_code or None,
                    street or None,
                    number or None,
                    neighborhood or None,
                    city or None,
                    state or None,
                    country or None,
                    now,
                    now,
                ),
            )
            conn.execute("COMMIT;")
            return code
        except Exception:
            conn.execute("ROLLBACK;")
            raise


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
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE;")
        try:
            dup = find_customer_duplicate(conn, cpf or "", phone or "", customer_id)
            if dup:
                kind, row = dup
                conn.execute("ROLLBACK;")
                label = "CPF" if kind == "cpf" else "phone number"
                raise ValueError(
                    f"Duplicate {label}: already used by customer **{row['customer_code']}** — {row['name']}."
                )
            conn.execute(
                """
                UPDATE customers SET
                    name = ?, cpf = ?, rg = ?, phone = ?, email = ?, instagram = ?,
                    zip_code = ?, street = ?, number = ?, neighborhood = ?,
                    city = ?, state = ?, country = ?, updated_at = ?
                WHERE id = ?;
                """,
                (
                    name.strip(),
                    cpf or None,
                    rg or None,
                    phone or None,
                    email or None,
                    instagram or None,
                    zip_code or None,
                    street or None,
                    number or None,
                    neighborhood or None,
                    city or None,
                    state or None,
                    country or None,
                    now,
                    customer_id,
                ),
            )
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise


def fetch_customers_ordered() -> list:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, customer_code, name, cpf, rg, phone, email, instagram,
                   zip_code, street, number, neighborhood, city, state, country,
                   created_at, updated_at
            FROM customers
            ORDER BY CAST(customer_code AS INTEGER);
            """
        ).fetchall()


def peek_next_customer_code_preview() -> str:
    """Read-only preview of the next code (does not consume sequence)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT last_value FROM customer_sequence_counter WHERE id = 1;"
        ).fetchone()
        n = int(row["last_value"] or 0) + 1 if row else 1
        return format_customer_code(n)


def format_sale_code(n: int) -> str:
    """Sequential sale id: 5 digits + trailing V (e.g. 00001V)."""
    return f"{int(n):05d}V"


def _next_sale_sequence(conn: sqlite3.Connection) -> int:
    """Atomically increment persistent sale sequence and return the new value."""
    cur = conn.execute(
        """
        UPDATE sale_sequence_counter
        SET last_value = last_value + 1
        WHERE id = 1
        RETURNING last_value;
        """
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("sale_sequence_counter is not initialized.")
    return int(row["last_value"])


def sync_sale_sequence_counter_from_sales(conn: sqlite3.Connection) -> None:
    """Ensure last_value is at least the highest numeric segment in sale_code (*#####V*)."""
    max_n = 0
    for row in conn.execute(
        """
        SELECT sale_code FROM sales
        WHERE sale_code IS NOT NULL AND TRIM(sale_code) != '';
        """
    ):
        s = str(row["sale_code"] or "").strip().upper()
        m = re.match(r"^(\d{5})V$", s)
        if m:
            max_n = max(max_n, int(m.group(1)))
    row2 = conn.execute(
        "SELECT last_value FROM sale_sequence_counter WHERE id = 1;"
    ).fetchone()
    cur = int(row2["last_value"] or 0) if row2 else 0
    conn.execute(
        "UPDATE sale_sequence_counter SET last_value = ? WHERE id = 1;",
        (max(max_n, cur),),
    )


def fetch_skus_available_for_sale() -> list:
    """SKUs with active price and positive aggregate stock (sku_master)."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT sm.sku,
                   COALESCE(sm.selling_price, 0) AS selling_price,
                   COALESCE(sm.total_stock, 0) AS total_stock,
                   (
                       SELECT p.name FROM products p
                       WHERE p.sku = sm.sku AND p.deleted_at IS NULL
                       ORDER BY p.id LIMIT 1
                   ) AS sample_name
            FROM sku_master sm
            WHERE sm.deleted_at IS NULL
              AND COALESCE(sm.selling_price, 0) > 0
              AND COALESCE(sm.total_stock, 0) > 0
            ORDER BY sm.sku COLLATE NOCASE;
            """
        ).fetchall()


def fetch_product_batches_for_sku(sku: str) -> list:
    """In-stock product batches for a SKU (FIFO order by product id)."""
    sku = (sku or "").strip()
    if not sku:
        return []
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT p.id, p.name, p.stock, p.product_enter_code,
                   p.color, p.style, p.palette, p.gender
            FROM products p
            WHERE p.sku = ? AND p.deleted_at IS NULL
              AND COALESCE(p.stock, 0) > 0
            ORDER BY p.id;
            """,
            (sku,),
        ).fetchall()


def filter_customers_by_search(rows: list, query: str) -> list:
    """Filter customer rows by substring on name or customer_code (case-insensitive)."""
    q = (query or "").strip().lower()
    if not q:
        return list(rows)
    out = []
    for r in rows:
        code = str(r["customer_code"] or "").lower()
        name = str(r["name"] or "").lower()
        if q in code or q in name:
            out.append(r)
    return out


def migrate_product_skus_to_generated(conn: sqlite3.Connection) -> None:
    """Recompute SKU from product name + attributes for every row (keeps legacy data consistent)."""
    rows = conn.execute(
        """
        SELECT id, name, color, gender, palette, style, sku
        FROM products
        ORDER BY id;
        """
    ).fetchall()
    for row in rows:
        body = build_product_sku_body(
            str(row["name"] or ""),
            row["color"] or "",
            row["gender"] or "",
            row["palette"] or "",
            row["style"] or "",
        )
        old_sku = str(row["sku"] or "").strip()
        oparts = old_sku.split("-")
        if len(oparts) >= 6 and oparts[0].isdigit():
            new_sku = f"{oparts[0]}-{body}"
        else:
            n = _next_sku_sequence(conn)
            new_sku = f"{format_sku_sequence_int(n)}-{body}"
        conn.execute(
            "UPDATE products SET sku = ? WHERE id = ?;",
            (new_sku, int(row["id"])),
        )


def backfill_sales_cogs(conn: sqlite3.Connection) -> None:
    """Populate cogs_total for legacy sales rows when missing."""
    rows = conn.execute(
        """
        SELECT s.id, s.quantity, p.cost
        FROM sales s
        JOIN products p ON p.id = s.product_id
        WHERE COALESCE(s.cogs_total, 0) = 0;
        """
    ).fetchall()
    for row in rows:
        q = int(row["quantity"])
        c = float(row["cost"] or 0.0)
        conn.execute(
            "UPDATE sales SET cogs_total = ? WHERE id = ?;",
            (float(q) * c, int(row["id"])),
        )


def backfill_sku_master_from_products(conn: sqlite3.Connection) -> None:
    """Build sku_master rows from existing products (weighted by stock)."""
    now = datetime.now().isoformat(timespec="seconds")
    skus = conn.execute(
        """
        SELECT DISTINCT sku FROM products
        WHERE sku IS NOT NULL AND TRIM(sku) != ''
          AND deleted_at IS NULL;
        """
    ).fetchall()
    for row in skus:
        sku = str(row["sku"]).strip()
        agg = conn.execute(
            """
            SELECT
                COALESCE(SUM(stock), 0) AS total_st,
                COALESCE(SUM(stock * COALESCE(cost, 0)), 0) AS cost_sum,
                COALESCE(SUM(stock * COALESCE(price, 0)), 0) AS price_sum
            FROM products
            WHERE sku = ? AND deleted_at IS NULL;
            """,
            (sku,),
        ).fetchone()
        total_st = float(agg["total_st"] or 0)
        cost_sum = float(agg["cost_sum"] or 0.0)
        price_sum = float(agg["price_sum"] or 0.0)
        avg_cost = (cost_sum / total_st) if total_st > 0 else 0.0
        sell_p = (price_sum / total_st) if total_st > 0 else 0.0
        conn.execute(
            """
            INSERT INTO sku_master (sku, total_stock, avg_unit_cost, selling_price, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(sku) DO UPDATE SET
                total_stock = excluded.total_stock,
                avg_unit_cost = excluded.avg_unit_cost,
                selling_price = CASE
                    WHEN excluded.selling_price > 0 THEN excluded.selling_price
                    ELSE sku_master.selling_price
                END,
                updated_at = excluded.updated_at;
            """,
            (sku, total_st, avg_cost, sell_p, now),
        )


def ensure_sku_master(conn: sqlite3.Connection, sku: str) -> None:
    if not sku or not str(sku).strip():
        raise ValueError("SKU is required for inventory costing.")
    sku = sku.strip()
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT OR IGNORE INTO sku_master (sku, total_stock, avg_unit_cost, selling_price, updated_at, deleted_at)
        VALUES (?, 0, 0, 0, ?, NULL);
        """,
        (sku, now),
    )


def sync_sku_master_totals(conn: sqlite3.Connection, sku: str) -> None:
    """Recompute total_stock for a SKU from product rows (avg cost unchanged)."""
    if not sku or not str(sku).strip():
        return
    sku = sku.strip()
    exists = conn.execute(
        "SELECT 1 FROM sku_master WHERE sku = ?;",
        (sku,),
    ).fetchone()
    if exists is None:
        ensure_sku_master(conn, sku)
    total = float(
        conn.execute(
            """
            SELECT COALESCE(SUM(stock), 0) FROM products
            WHERE sku = ? AND deleted_at IS NULL;
            """,
            (sku,),
        ).fetchone()[0]
    )
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        UPDATE sku_master SET total_stock = ?, updated_at = ? WHERE sku = ?;
        """,
        (total, now, sku),
    )


def apply_stock_receipt(
    conn: sqlite3.Connection,
    sku: str,
    product_id: int,
    quantity: float,
    unit_cost: float,
) -> None:
    """
    Weighted-average inventory cost update for a stock receipt.
    New avg = ((prev_total * prev_avg) + (qty * unit_cost)) / (prev_total + qty)
    """
    qty = round(float(quantity), 4)
    if qty <= 0:
        raise ValueError("Quantity must be greater than zero.")
    if unit_cost <= 0:
        raise ValueError("Unit cost must be greater than zero.")
    sku = sku.strip()

    prow = conn.execute(
        "SELECT id, sku, deleted_at FROM products WHERE id = ?;",
        (int(product_id),),
    ).fetchone()
    if prow is None:
        raise ValueError("Product batch not found.")
    if (prow["sku"] or "").strip() != sku:
        raise ValueError("Product SKU does not match the selected batch.")
    if prow["deleted_at"]:
        raise ValueError("Cannot add stock to an inactive (soft-deleted) product batch.")

    sm_del = conn.execute(
        "SELECT deleted_at FROM sku_master WHERE sku = ?;",
        (sku,),
    ).fetchone()
    if sm_del and sm_del["deleted_at"]:
        raise ValueError("Cannot add stock to an inactive (soft-deleted) SKU.")

    ensure_sku_master(conn, sku)
    prev_total = float(
        conn.execute(
            """
            SELECT COALESCE(SUM(stock), 0) FROM products
            WHERE sku = ? AND deleted_at IS NULL;
            """,
            (sku,),
        ).fetchone()[0]
    )
    sm = conn.execute(
        "SELECT avg_unit_cost FROM sku_master WHERE sku = ?;",
        (sku,),
    ).fetchone()
    prev_avg = float(sm["avg_unit_cost"] or 0.0)

    new_total = prev_total + qty
    new_avg = (
        ((prev_total * prev_avg) + (qty * float(unit_cost))) / new_total
        if new_total > 0
        else 0.0
    )
    total_entry_cost = round(qty * float(unit_cost), 2)

    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO stock_cost_entries (
            sku, product_id, quantity, unit_cost, total_entry_cost,
            stock_before, stock_after, avg_cost_before, avg_cost_after, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            sku,
            int(product_id),
            qty,
            float(unit_cost),
            total_entry_cost,
            prev_total,
            new_total,
            prev_avg,
            new_avg,
            now,
        ),
    )

    conn.execute(
        "UPDATE products SET stock = stock + ? WHERE id = ?;",
        (qty, int(product_id)),
    )
    conn.execute(
        "UPDATE products SET cost = ? WHERE sku = ?;",
        (new_avg, sku),
    )

    actual_total = float(
        conn.execute(
            """
            SELECT COALESCE(SUM(stock), 0) FROM products
            WHERE sku = ? AND deleted_at IS NULL;
            """,
            (sku,),
        ).fetchone()[0]
    )
    conn.execute(
        """
        UPDATE sku_master
        SET total_stock = ?, avg_unit_cost = ?, updated_at = ?
        WHERE sku = ?;
        """,
        (actual_total, new_avg, now, sku),
    )


def update_sku_selling_price(sku: str, new_price: float, note: str = "") -> None:
    """Set selling price for a SKU (does not change inventory cost). History is appended."""
    if not sku or not str(sku).strip():
        raise ValueError("SKU is required.")
    if new_price <= 0:
        raise ValueError("Selling price must be greater than zero.")
    sku = sku.strip()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT selling_price FROM sku_master WHERE sku = ?;",
            (sku,),
        ).fetchone()
        if row is None:
            raise ValueError(
                "SKU not found in inventory. Register a product or add a stock receipt first."
            )
        old = float(row["selling_price"] or 0.0)
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            """
            INSERT INTO price_history (sku, old_price, new_price, created_at, note)
            VALUES (?, ?, ?, ?, ?);
            """,
            (sku, old, float(new_price), now, note or ""),
        )
        conn.execute(
            """
            UPDATE sku_master SET selling_price = ?, updated_at = ? WHERE sku = ?;
            """,
            (float(new_price), now, sku),
        )
        conn.execute(
            """
            UPDATE products SET price = ? WHERE sku = ?;
            """,
            (float(new_price), sku),
        )


def compute_sku_pricing_targets(
    avg_cost: float,
    markup_pct: float,
    taxes_pct: float,
    interest_pct: float,
) -> tuple[float, float, float]:
    """
    Pricing workflow (percentages as whole numbers, e.g. 10.5 = 10.5%):
    1) Price before taxes = Avg cost + (Avg cost × Markup%)
    2) Price with taxes = Price before + (Price before × Taxes%)
    3) Target price = Price with taxes + (Price with taxes × Interest%)
    """
    ac = float(avg_cost)
    m = float(markup_pct) / 100.0
    t = float(taxes_pct) / 100.0
    i = float(interest_pct) / 100.0
    price_before = ac + (ac * m)
    price_with_taxes = price_before + (price_before * t)
    target = price_with_taxes + (price_with_taxes * i)
    return round(price_before, 2), round(price_with_taxes, 2), round(target, 2)


def save_sku_pricing_workflow(
    sku: str,
    markup_pct: float,
    taxes_pct: float,
    interest_pct: float,
) -> int:
    """
    Append-only pricing record; deactivates prior rows for this SKU and sets the new row active.
    Applies target_price to sku_master.selling_price and products.price (sales use this price).
    """
    sku = sku.strip()
    markup_pct = round(float(markup_pct), 2)
    taxes_pct = round(float(taxes_pct), 2)
    interest_pct = round(float(interest_pct), 2)
    if markup_pct < 0 or taxes_pct < 0 or interest_pct < 0:
        raise ValueError("Markup, taxes, and interest must be zero or greater.")

    with get_conn() as conn:
        conn.isolation_level = None
        try:
            conn.execute("BEGIN;")
            row = conn.execute(
                "SELECT selling_price, avg_unit_cost FROM sku_master WHERE sku = ?;",
                (sku,),
            ).fetchone()
            if row is None:
                raise ValueError("SKU not found in inventory master.")
            avg_cost = float(row["avg_unit_cost"] or 0.0)
            if avg_cost <= 0:
                raise ValueError(
                    "Average inventory cost is not available for this SKU. "
                    "Record stock receipts (Costing) so WAC is set before pricing."
                )
            old_sell = float(row["selling_price"] or 0.0)
            pb, pwt, target = compute_sku_pricing_targets(
                avg_cost, markup_pct, taxes_pct, interest_pct
            )
            if target <= 0:
                raise ValueError("Calculated target price must be greater than zero.")
            now = datetime.now().isoformat(timespec="seconds")
            conn.execute(
                "UPDATE sku_pricing_records SET is_active = 0 WHERE sku = ?;",
                (sku,),
            )
            cur = conn.execute(
                """
                INSERT INTO sku_pricing_records (
                    sku, avg_cost_snapshot, markup_pct, taxes_pct, interest_pct,
                    price_before_taxes, price_with_taxes, target_price, created_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                """,
                (
                    sku,
                    avg_cost,
                    markup_pct,
                    taxes_pct,
                    interest_pct,
                    pb,
                    pwt,
                    target,
                    now,
                ),
            )
            new_id = int(cur.lastrowid)
            conn.execute(
                """
                UPDATE sku_master SET selling_price = ?, updated_at = ? WHERE sku = ?;
                """,
                (target, now, sku),
            )
            conn.execute(
                """
                UPDATE products SET price = ? WHERE sku = ?;
                """,
                (target, sku),
            )
            conn.execute(
                """
                INSERT INTO price_history (sku, old_price, new_price, created_at, note)
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    sku,
                    old_sell,
                    target,
                    now,
                    "Pricing workflow (markup / taxes / interest)",
                ),
            )
            conn.execute("COMMIT;")
            return new_id
        except Exception:
            conn.execute("ROLLBACK;")
            raise


def fetch_sku_pricing_records_for_sku(sku: str, limit: int = 100):
    """Workflow pricing history for one SKU (newest first)."""
    sku = sku.strip()
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, sku, avg_cost_snapshot, markup_pct, taxes_pct, interest_pct,
                   price_before_taxes, price_with_taxes, target_price, created_at, is_active
            FROM sku_pricing_records
            WHERE sku = ?
            ORDER BY id DESC
            LIMIT ?;
            """,
            (sku, int(limit)),
        ).fetchall()


def fetch_active_sku_pricing_record(sku: str):
    """Most recent active workflow record for a SKU (if any)."""
    sku = sku.strip()
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, sku, avg_cost_snapshot, markup_pct, taxes_pct, interest_pct,
                   price_before_taxes, price_with_taxes, target_price, created_at, is_active
            FROM sku_pricing_records
            WHERE sku = ? AND is_active = 1
            ORDER BY id DESC
            LIMIT 1;
            """,
            (sku,),
        ).fetchone()


def add_stock_receipt(sku: str, product_id: int, quantity: float, unit_cost: float) -> None:
    """Apply a stock receipt at SKU level (weighted-average inventory cost)."""
    with get_conn() as conn:
        conn.isolation_level = None
        try:
            conn.execute("BEGIN;")
            apply_stock_receipt(conn, sku, product_id, float(quantity), float(unit_cost))
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise


def fetch_sku_master_rows():
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT sku, total_stock, avg_unit_cost, selling_price, structured_cost_total, updated_at
            FROM sku_master
            WHERE deleted_at IS NULL
            ORDER BY sku;
            """
        ).fetchall()


def fetch_recent_stock_cost_entries(limit: int = 50):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, sku, product_id, quantity, unit_cost, total_entry_cost, stock_before, stock_after,
                   avg_cost_before, avg_cost_after, created_at
            FROM stock_cost_entries
            ORDER BY id DESC
            LIMIT ?;
            """,
            (int(limit),),
        ).fetchall()


def get_persisted_structured_unit_cost(sku: str) -> float:
    """
    Planned unit cost per SKU from saved cost components (sku_master.structured_cost_total).
    Does not recompute from form state — user must save the cost breakdown first.
    """
    sku = sku.strip()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(structured_cost_total, 0) AS t, deleted_at FROM sku_master WHERE sku = ?;",
            (sku,),
        ).fetchone()
        if row is None:
            raise ValueError("SKU is not registered in inventory master.")
        if row["deleted_at"]:
            raise ValueError("SKU is inactive (soft-deleted).")
        return float(row["t"] or 0.0)


def fetch_product_batches_for_sku(sku: str) -> list:
    """Product rows (batches) for a given SKU — stock receipts apply to one batch."""
    sku = sku.strip()
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, name, sku, registered_date, product_enter_code, cost, price, pricing_locked, stock,
                   color, style, palette, gender
            FROM products
            WHERE TRIM(COALESCE(sku, '')) = ?
              AND deleted_at IS NULL
            ORDER BY id DESC;
            """,
            (sku,),
        ).fetchall()


def fetch_price_history_for_sku(sku: str, limit: int = 40):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, sku, old_price, new_price, created_at, note
            FROM price_history
            WHERE sku = ?
            ORDER BY id DESC
            LIMIT ?;
            """,
            (sku.strip(), int(limit)),
        ).fetchall()


def _maybe_preview_product_sku() -> Optional[str]:
    """Read-only preview from session_state (used below product form)."""
    name = (st.session_state.get("prod_reg_name") or "").strip()
    if not name:
        return None
    for k in ("prod_reg_color", "prod_reg_palette", "prod_reg_gender", "prod_reg_style"):
        if st.session_state.get(k) is None:
            return None
    c, ec = resolve_attribute_value(st.session_state["prod_reg_color"], "", "color")
    p, ep = resolve_attribute_value(st.session_state["prod_reg_palette"], "", "palette")
    g, eg = resolve_attribute_value(st.session_state["prod_reg_gender"], "", "gender")
    s, es = resolve_attribute_value(st.session_state["prod_reg_style"], "", "style")
    if ec or ep or eg or es:
        return None
    body = build_product_sku_body(name, c, g, p, s)
    return f"XXX-{body}"


def update_product_attributes(
    product_id: int,
    color: str,
    style: str,
    palette: str,
    gender: str,
) -> None:
    """
    Update attributes and recalculate SKU from product name + attributes.
    Raises ValueError if another product already uses the new SKU.
    """
    color = (color or "").strip()
    style = (style or "").strip()
    palette = (palette or "").strip()
    gender = (gender or "").strip()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name, sku FROM products WHERE id = ?;",
            (int(product_id),),
        ).fetchone()
        if row is None:
            raise ValueError("Product not found.")
        name = str(row["name"] or "").strip()
        old_sku = str(row["sku"] or "").strip()
        oparts = old_sku.split("-")
        if len(oparts) >= 6 and oparts[0].isdigit():
            new_sku = f"{oparts[0]}-{build_product_sku_body(name, color, gender, palette, style)}"
        else:
            new_sku = generate_product_sku(name, color, gender, palette, style)
        dup = conn.execute(
            """
            SELECT id FROM products
            WHERE sku = ? AND id != ?;
            """,
            (new_sku, int(product_id)),
        ).fetchone()
        if dup is not None:
            raise ValueError(
                f"Duplicate SKU `{new_sku}` would be created. "
                "Adjust product name or attributes to get a unique SKU."
            )
        conn.execute(
            """
            UPDATE products
            SET color = ?, style = ?, palette = ?, gender = ?, sku = ?
            WHERE id = ?;
            """,
            (color, style, palette, gender, new_sku, int(product_id)),
        )


def _slugify_code_part(text: str) -> str:
    """
    Create a stable code fragment from product name:
    - keep alphanumerics
    - convert spaces/dashes to '-'
    - collapse consecutive '-'
    - upper-case
    """
    cleaned_chars = []
    last_was_dash = False
    for ch in (text or "").strip():
        if ch.isalnum():
            cleaned_chars.append(ch.upper())
            last_was_dash = False
        elif ch in (" ", "-","_","/","\\"):
            if not last_was_dash:
                cleaned_chars.append("-")
                last_was_dash = True
        # ignore any other characters

    slug = "".join(cleaned_chars).strip("-")
    if not slug:
        slug = "ITEM"
    return slug


def make_product_enter_code(product_name: str, registered_date) -> str:
    """
    Product entering code = Product name + date entered.
    Stored as: <SLUGIFIED_NAME>-YYYYMMDD
    """
    date_part = registered_date.strftime("%Y%m%d")
    return f"{_slugify_code_part(product_name)}-{date_part}"


def format_qty_display_4(q: float) -> str:
    """Format quantity for text inputs; empty string means zero."""
    v = round(float(q), 4)
    if abs(v) < 1e-12:
        return ""
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


def parse_cost_quantity_text(raw: str) -> tuple[float, Optional[str]]:
    """Non-negative quantity, up to 4 decimal places. Empty -> 0."""
    s = (raw or "").strip().replace(",", ".")
    if s == "":
        return 0.0, None
    for c in s:
        if c not in "0123456789.":
            return 0.0, "Use only digits and one decimal point."
    if s.count(".") > 1:
        return 0.0, "Only one decimal point allowed."
    if s == ".":
        return 0.0, None
    parts = s.split(".")
    if len(parts) == 2 and len(parts[1]) > 4:
        return 0.0, "At most 4 decimal places for quantity."
    try:
        v = float(s)
    except ValueError:
        return 0.0, "Invalid number."
    if v < 0:
        return 0.0, "Quantity cannot be negative."
    return round(v, 4), None


def parse_cost_unit_price_value(value: float) -> tuple[float, Optional[str]]:
    """Unit price: non-negative, rounded to 2 decimals."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0, "Invalid unit price."
    if v < 0:
        return 0.0, "Unit price cannot be negative."
    return round(v, 2), None


def ensure_sku_cost_component_rows(conn: sqlite3.Connection, sku: str) -> None:
    if not sku or not str(sku).strip():
        return
    sku = sku.strip()
    now = datetime.now().isoformat(timespec="seconds")
    for key, label in SKU_COST_COMPONENT_DEFINITIONS:
        conn.execute(
            """
            INSERT OR IGNORE INTO sku_cost_components (
                sku, component_key, label, unit_price, quantity, line_total, updated_at
            ) VALUES (?, ?, ?, 0, 0, 0, ?);
            """,
            (sku, key, label, now),
        )
        conn.execute(
            "UPDATE sku_cost_components SET label = ? WHERE sku = ? AND component_key = ?;",
            (label, sku, key),
        )


def recompute_sku_structured_cost_total(conn: sqlite3.Connection, sku: str) -> float:
    sku = sku.strip()
    row = conn.execute(
        """
        SELECT COALESCE(SUM(line_total), 0) AS t
        FROM sku_cost_components
        WHERE sku = ?;
        """,
        (sku,),
    ).fetchone()
    total = float(row["t"] or 0.0)
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        UPDATE sku_master
        SET structured_cost_total = ?, updated_at = ?
        WHERE sku = ?;
        """,
        (total, now, sku),
    )
    return total


def get_conn() -> sqlite3.Connection:
    # Create a fresh connection per request; Streamlit may run code in multiple threads.
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enforce foreign keys (useful if you extend the app later).
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def generate_product_sku(
    product_name: str,
    color: str,
    gender: str,
    palette: str,
    style: str,
) -> str:
    """
    Full SKU: [SEQ]-[PP]-[CC]-[GG]-[PA]-[ST]. SEQ is a persistent sequential code (001+).
    Allocates the next sequence number atomically (BEGIN IMMEDIATE + counter update).
    """
    with get_conn() as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE;")
        try:
            n = _next_sku_sequence(conn)
            body = build_product_sku_body(
                product_name, color, gender, palette, style
            )
            conn.execute("COMMIT;")
            return f"{format_sku_sequence_int(n)}-{body}"
        except Exception:
            conn.execute("ROLLBACK;")
            raise


def sync_sku_sequence_counter_from_skus(conn: sqlite3.Connection) -> None:
    """
    Ensure last_value is at least the highest leading numeric segment in products/sku_master SKUs.
    """
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


def fetch_sku_cost_components_for_sku(sku: str) -> list:
    """Rows ordered like SKU_COST_COMPONENT_DEFINITIONS."""
    sku = sku.strip()
    with get_conn() as conn:
        ensure_sku_cost_component_rows(conn, sku)
        by_key = {}
        rows = conn.execute(
            """
            SELECT component_key, label, unit_price, quantity, line_total, updated_at
            FROM sku_cost_components
            WHERE sku = ?;
            """,
            (sku,),
        ).fetchall()
        for r in rows:
            by_key[r["component_key"]] = r
    out = []
    for key, label in SKU_COST_COMPONENT_DEFINITIONS:
        r = by_key.get(key)
        if r is None:
            out.append(
                {
                    "component_key": key,
                    "label": label,
                    "unit_price": 0.0,
                    "quantity": 0.0,
                    "line_total": 0.0,
                    "updated_at": None,
                }
            )
        else:
            out.append(
                {
                    "component_key": key,
                    "label": r["label"],
                    "unit_price": float(r["unit_price"] or 0),
                    "quantity": float(r["quantity"] or 0),
                    "line_total": float(r["line_total"] or 0),
                    "updated_at": r["updated_at"],
                }
            )
    return out


def save_sku_cost_structure(sku: str, component_inputs: list) -> float:
    """
    Persist component lines. component_inputs: list of (component_key, unit_price, unit_quantity).
    Returns stored structured total SKU cost.
    """
    sku = sku.strip()
    with get_conn() as conn:
        conn.isolation_level = None
        try:
            conn.execute("BEGIN;")
            sm = conn.execute(
                "SELECT 1 FROM sku_master WHERE sku = ?;",
                (sku,),
            ).fetchone()
            if sm is None:
                raise ValueError("SKU is not registered in inventory master.")
            ensure_sku_cost_component_rows(conn, sku)
            now = datetime.now().isoformat(timespec="seconds")
            for key, unit_price, quantity in component_inputs:
                unit_price = round(float(unit_price), 2)
                quantity = round(float(quantity), 4)
                if unit_price < 0 or quantity < 0:
                    raise ValueError("Unit price and quantity cannot be negative.")
                line_total = round(unit_price * quantity, 2)
                conn.execute(
                    """
                    UPDATE sku_cost_components
                    SET unit_price = ?, quantity = ?, line_total = ?, updated_at = ?
                    WHERE sku = ? AND component_key = ?;
                    """,
                    (unit_price, quantity, line_total, now, sku, key),
                )
            total = recompute_sku_structured_cost_total(conn, sku)
            conn.execute("COMMIT;")
            return float(total)
        except Exception:
            conn.execute("ROLLBACK;")
            raise


def migrate_sku_cost_component_rows(conn: sqlite3.Connection) -> None:
    """Ensure each SKU has a full cost component grid; recompute stored totals."""
    skus = conn.execute("SELECT sku FROM sku_master;").fetchall()
    for row in skus:
        sku = str(row["sku"]).strip()
        if not sku:
            continue
        ensure_sku_cost_component_rows(conn, sku)
        recompute_sku_structured_cost_total(conn, sku)


def migrate_inventory_decimal_v1(conn: sqlite3.Connection) -> None:
    """
    One-time migration: inventory quantities as REAL (up to 4 decimal places),
    stock_cost_entries with total_entry_cost, sku_master.total_stock as REAL.
    Preserves product ids (foreign keys from sales).
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_schema_migrations (
            id TEXT PRIMARY KEY
        );
        """
    )
    if conn.execute(
        "SELECT 1 FROM app_schema_migrations WHERE id = 'inventory_decimal_v1';"
    ).fetchone():
        return

    info = conn.execute("PRAGMA table_info(products);").fetchall()
    stock_col = next((r for r in info if r[1] == "stock"), None)
    need = False
    if stock_col is not None:
        t = (stock_col[2] or "").upper()
        if "INT" in t and "REAL" not in t and "FLOA" not in t:
            need = True

    if not need:
        conn.execute(
            "INSERT OR IGNORE INTO app_schema_migrations (id) VALUES ('inventory_decimal_v1');"
        )
        return

    conn.execute("PRAGMA foreign_keys = OFF;")

    # --- stock_cost_entries: backup then drop (references products) ---
    sce_rows = conn.execute("SELECT * FROM stock_cost_entries;").fetchall()
    conn.execute("DROP TABLE IF EXISTS stock_cost_entries;")

    # --- sku_master (no FK to products; drop before products for simpler ordering) ---
    sm_rows = conn.execute("SELECT * FROM sku_master;").fetchall()
    conn.execute("DROP TABLE IF EXISTS sku_master;")

    # --- products: copy to products_new, drop original, rename (FK OFF so sales -> products can be rebuilt) ---
    conn.execute(
        """
        CREATE TABLE products_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sku TEXT,
            registered_date TEXT,
            product_enter_code TEXT,
            cost REAL NOT NULL,
            price REAL NOT NULL,
            pricing_locked INTEGER NOT NULL DEFAULT 0 CHECK(pricing_locked IN (0, 1)),
            stock REAL NOT NULL CHECK(stock >= 0),
            color TEXT,
            style TEXT,
            palette TEXT,
            gender TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO products_new (
            id, name, sku, registered_date, product_enter_code, cost, price, pricing_locked,
            stock, color, style, palette, gender
        )
        SELECT
            id, name, sku, registered_date, product_enter_code, cost, price, pricing_locked,
            CAST(stock AS REAL), color, style, palette, gender
        FROM products;
        """
    )
    conn.execute("DROP TABLE products;")
    conn.execute("ALTER TABLE products_new RENAME TO products;")
    conn.execute("DELETE FROM sqlite_sequence WHERE name = 'products';")
    mx_prod = conn.execute("SELECT MAX(id) AS m FROM products;").fetchone()
    if mx_prod and mx_prod["m"] is not None and int(mx_prod["m"]) > 0:
        conn.execute(
            "INSERT INTO sqlite_sequence (name, seq) VALUES ('products', ?);",
            (int(mx_prod["m"]),),
        )

    # --- sku_master ---
    conn.execute(
        """
        CREATE TABLE sku_master (
            sku TEXT PRIMARY KEY,
            total_stock REAL NOT NULL DEFAULT 0,
            avg_unit_cost REAL NOT NULL DEFAULT 0,
            selling_price REAL NOT NULL DEFAULT 0,
            structured_cost_total REAL NOT NULL DEFAULT 0,
            updated_at TEXT
        );
        """
    )
    for r in sm_rows:
        sm_dict = dict(r)
        sct = float(sm_dict.get("structured_cost_total") or 0)
        conn.execute(
            """
            INSERT INTO sku_master (
                sku, total_stock, avg_unit_cost, selling_price, structured_cost_total, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                r["sku"],
                float(r["total_stock"] or 0),
                float(r["avg_unit_cost"] or 0),
                float(r["selling_price"] or 0),
                sct,
                r["updated_at"],
            ),
        )

    # --- stock_cost_entries ---
    conn.execute(
        """
        CREATE TABLE stock_cost_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            product_id INTEGER,
            quantity REAL NOT NULL CHECK(quantity > 0),
            unit_cost REAL NOT NULL,
            total_entry_cost REAL NOT NULL,
            stock_before REAL NOT NULL,
            stock_after REAL NOT NULL,
            avg_cost_before REAL NOT NULL,
            avg_cost_after REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (id)
        );
        """
    )
    for r in sce_rows:
        sce_dict = dict(r)
        q = float(r["quantity"] or 0)
        uc = float(r["unit_cost"] or 0)
        te = q * uc
        if sce_dict.get("total_entry_cost") is not None:
            try:
                te = float(sce_dict["total_entry_cost"])
            except (TypeError, ValueError):
                te = round(q * uc, 2)
        conn.execute(
            """
            INSERT INTO stock_cost_entries (
                id, sku, product_id, quantity, unit_cost, total_entry_cost,
                stock_before, stock_after, avg_cost_before, avg_cost_after, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                int(r["id"]),
                r["sku"],
                r["product_id"],
                q,
                uc,
                round(float(te), 2),
                float(r["stock_before"] or 0),
                float(r["stock_after"] or 0),
                float(r["avg_cost_before"] or 0),
                float(r["avg_cost_after"] or 0),
                r["created_at"],
            ),
        )
    conn.execute("DELETE FROM sqlite_sequence WHERE name = 'stock_cost_entries';")
    mx_row = conn.execute("SELECT MAX(id) AS m FROM stock_cost_entries;").fetchone()
    mx = int(mx_row["m"]) if mx_row and mx_row["m"] is not None else None
    if mx is not None and mx > 0:
        conn.execute(
            "INSERT INTO sqlite_sequence (name, seq) VALUES ('stock_cost_entries', ?);",
            (mx,),
        )

    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(
        "INSERT OR IGNORE INTO app_schema_migrations (id) VALUES ('inventory_decimal_v1');"
    )

    # Reconcile sku_master totals with migrated product rows
    skus = conn.execute(
        """
        SELECT DISTINCT sku FROM products
        WHERE sku IS NOT NULL AND TRIM(sku) != '';
        """
    ).fetchall()
    for row in skus:
        sync_sku_master_totals(conn, str(row["sku"]).strip())


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sku TEXT,
                registered_date TEXT,
                product_enter_code TEXT,
                cost REAL NOT NULL,
                price REAL NOT NULL,
                pricing_locked INTEGER NOT NULL DEFAULT 0 CHECK(pricing_locked IN (0, 1)),
                stock REAL NOT NULL CHECK(stock >= 0),
                color TEXT,
                style TEXT,
                palette TEXT,
                gender TEXT
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity >= 1),
                total REAL NOT NULL,
                sold_at TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products (id)
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sku_master (
                sku TEXT PRIMARY KEY,
                total_stock REAL NOT NULL DEFAULT 0,
                avg_unit_cost REAL NOT NULL DEFAULT 0,
                selling_price REAL NOT NULL DEFAULT 0,
                updated_at TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_cost_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                product_id INTEGER,
                quantity REAL NOT NULL CHECK(quantity > 0),
                unit_cost REAL NOT NULL,
                total_entry_cost REAL NOT NULL,
                stock_before REAL NOT NULL,
                stock_after REAL NOT NULL,
                avg_cost_before REAL NOT NULL,
                avg_cost_after REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products (id)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                old_price REAL,
                new_price REAL NOT NULL,
                created_at TEXT NOT NULL,
                note TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sku_sequence_counter (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_value INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO sku_sequence_counter (id, last_value) VALUES (1, 0);"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sku_pricing_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                avg_cost_snapshot REAL NOT NULL,
                markup_pct REAL NOT NULL CHECK(markup_pct >= 0),
                taxes_pct REAL NOT NULL CHECK(taxes_pct >= 0),
                interest_pct REAL NOT NULL CHECK(interest_pct >= 0),
                price_before_taxes REAL NOT NULL,
                price_with_taxes REAL NOT NULL,
                target_price REAL NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0 CHECK(is_active IN (0, 1))
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sku_pricing_records_sku ON sku_pricing_records(sku);"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sku_cost_components (
                sku TEXT NOT NULL,
                component_key TEXT NOT NULL,
                label TEXT NOT NULL,
                unit_price REAL NOT NULL DEFAULT 0 CHECK(unit_price >= 0),
                quantity REAL NOT NULL DEFAULT 0 CHECK(quantity >= 0),
                line_total REAL NOT NULL DEFAULT 0 CHECK(line_total >= 0),
                updated_at TEXT,
                PRIMARY KEY (sku, component_key)
            );
            """
        )

        sku_master_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sku_master);").fetchall()}
        if "structured_cost_total" not in sku_master_cols:
            conn.execute(
                "ALTER TABLE sku_master ADD COLUMN structured_cost_total REAL NOT NULL DEFAULT 0;"
            )

        sce_cols = {row["name"] for row in conn.execute("PRAGMA table_info(stock_cost_entries);").fetchall()}
        if sce_cols and "total_entry_cost" not in sce_cols:
            conn.execute(
                "ALTER TABLE stock_cost_entries ADD COLUMN total_entry_cost REAL NOT NULL DEFAULT 0;"
            )
            conn.execute(
                """
                UPDATE stock_cost_entries
                SET total_entry_cost = ROUND(CAST(quantity AS REAL) * unit_cost, 2);
                """
            )

        migrate_inventory_decimal_v1(conn)

        sku_master_cols2 = {row["name"] for row in conn.execute("PRAGMA table_info(sku_master);").fetchall()}
        if "deleted_at" not in sku_master_cols2:
            conn.execute("ALTER TABLE sku_master ADD COLUMN deleted_at TEXT;")
        product_cols2 = {row["name"] for row in conn.execute("PRAGMA table_info(products);").fetchall()}
        if "deleted_at" not in product_cols2:
            conn.execute("ALTER TABLE products ADD COLUMN deleted_at TEXT;")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sku_deletion_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                deleted_at TEXT NOT NULL,
                deleted_by TEXT,
                note TEXT
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_sequence_counter (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_value INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO customer_sequence_counter (id, last_value) VALUES (1, 0);"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                cpf TEXT,
                rg TEXT,
                phone TEXT,
                email TEXT,
                instagram TEXT,
                zip_code TEXT,
                street TEXT,
                number TEXT,
                neighborhood TEXT,
                city TEXT,
                state TEXT,
                country TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);"
        )

        sales_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sales);").fetchall()}
        if "cogs_total" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN cogs_total REAL NOT NULL DEFAULT 0;")
        if "sku" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN sku TEXT;")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sale_sequence_counter (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_value INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO sale_sequence_counter (id, last_value) VALUES (1, 0);"
        )

        sales_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sales);").fetchall()}
        if "sale_code" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN sale_code TEXT;")
        if "customer_id" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN customer_id INTEGER;")
        if "unit_price" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN unit_price REAL;")
        if "discount_amount" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN discount_amount REAL NOT NULL DEFAULT 0;")
        if "base_amount" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN base_amount REAL;")

        # Backfill sale_code (#####V) for legacy rows; keep chronological order by id.
        max_n = 0
        for row in conn.execute(
            """
            SELECT sale_code FROM sales
            WHERE sale_code IS NOT NULL AND TRIM(sale_code) != '';
            """
        ):
            s = str(row["sale_code"] or "").strip().upper()
            m = re.match(r"^(\d{5})V$", s)
            if m:
                max_n = max(max_n, int(m.group(1)))
        next_n = max_n + 1
        for row in conn.execute(
            """
            SELECT id FROM sales
            WHERE sale_code IS NULL OR TRIM(sale_code) = ''
            ORDER BY id ASC;
            """
        ):
            conn.execute(
                "UPDATE sales SET sale_code = ? WHERE id = ?;",
                (format_sale_code(next_n), int(row["id"])),
            )
            next_n += 1
        sync_sale_sequence_counter_from_sales(conn)

        # Legacy rows: approximate unit/base/discount when missing.
        conn.execute(
            """
            UPDATE sales
            SET unit_price = CASE
                    WHEN COALESCE(quantity, 0) >= 1 THEN total * 1.0 / quantity
                    ELSE total
                END,
                discount_amount = 0,
                base_amount = total
            WHERE unit_price IS NULL;
            """
        )

        # Migrate older DBs (created before these fields existed).
        product_cols = {row["name"] for row in conn.execute("PRAGMA table_info(products);").fetchall()}
        if "sku" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN sku TEXT;")
        if "registered_date" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN registered_date TEXT;")
        if "product_enter_code" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN product_enter_code TEXT;")
        if "pricing_locked" not in product_cols:
            conn.execute(
                "ALTER TABLE products ADD COLUMN pricing_locked INTEGER NOT NULL DEFAULT 0 CHECK(pricing_locked IN (0, 1));"
            )
        if "color" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN color TEXT;")
        if "style" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN style TEXT;")
        if "palette" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN palette TEXT;")
        if "gender" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN gender TEXT;")

        # Backfill values for older rows so the new batch logic works.
        # (Older rows won't have SKU / registered_date / product_enter_code.)
        missing_rows = conn.execute(
            """
            SELECT id, name, sku, registered_date, product_enter_code
            FROM products
            WHERE product_enter_code IS NULL OR product_enter_code = ''
               OR registered_date IS NULL OR registered_date = '';
            """
        ).fetchall()

        if missing_rows:
            today_text = datetime.now().date().isoformat()
            for row in missing_rows:
                row_id = int(row["id"])
                sku = row["sku"] if row["sku"] else "N/A"
                registered_date_text = row["registered_date"] if row["registered_date"] else today_text
                # registered_date is stored as YYYY-MM-DD (from date_input), but we guard anyway.
                try:
                    registered_date = datetime.fromisoformat(registered_date_text).date()
                except ValueError:
                    registered_date = datetime.now().date()

                code = make_product_enter_code(product_name=row["name"], registered_date=registered_date)
                conn.execute(
                    """
                    UPDATE products
                    SET sku = ?, registered_date = ?, product_enter_code = ?
                    WHERE id = ?;
                    """,
                    (sku, registered_date.isoformat(), code, row_id),
                )

        # Backfill pricing_locked based on existing cost/price.
        conn.execute(
            """
            UPDATE products
            SET pricing_locked = 1
            WHERE pricing_locked = 0
              AND stock > 0
              AND (COALESCE(cost, 0) != 0 OR COALESCE(price, 0) != 0);
            """
        )

        migrate_product_skus_to_generated(conn)
        sync_sku_sequence_counter_from_skus(conn)
        sync_customer_sequence_counter_from_customers(conn)
        backfill_sales_cogs(conn)
        backfill_sku_master_from_products(conn)
        migrate_sku_cost_component_rows(conn)


def format_money(value: float) -> str:
    try:
        return f"{CURRENCY_SYMBOL}{value:,.2f}"
    except TypeError:
        return f"{CURRENCY_SYMBOL}{float(value):,.2f}"


def fetch_products():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, sku, registered_date, product_enter_code, cost, price, pricing_locked, stock,
                   color, style, palette, gender
            FROM products
            WHERE deleted_at IS NULL
            ORDER BY id DESC
            """
        ).fetchall()
    return rows


def _sku_search_sanitize_text(q: str) -> str:
    """Lowercase substring for LIKE; strip wildcard chars to avoid pattern injection."""
    return (q or "").strip().lower().replace("%", "").replace("_", "")


def fetch_product_search_attribute_options() -> dict:
    """Distinct color / gender / palette / style values for SKU search dropdowns."""
    out: dict = {"color": [], "gender": [], "palette": [], "style": []}
    with get_conn() as conn:
        for key, col in [
            ("color", "color"),
            ("gender", "gender"),
            ("palette", "palette"),
            ("style", "style"),
        ]:
            rows = conn.execute(
                f"""
                SELECT DISTINCT TRIM({col}) AS v
                FROM products
                WHERE {col} IS NOT NULL AND TRIM({col}) != ''
                  AND deleted_at IS NULL
                ORDER BY v COLLATE NOCASE;
                """
            ).fetchall()
            out[key] = [str(r["v"]) for r in rows if r["v"] is not None and str(r["v"]).strip()]
    return out


def search_products_filtered(
    text_q: str,
    color_filter: str,
    gender_filter: str,
    palette_filter: str,
    style_filter: str,
    sort_by: str,
    limit: int,
    offset: int,
) -> Tuple[list, int]:
    """
    Partial match on SKU and product name; optional exact-match attribute filters.
    Returns (rows as sqlite3.Row list, total matching count).
    """
    t = _sku_search_sanitize_text(text_q)
    wheres = ["p.deleted_at IS NULL"]
    params: list = []
    if t:
        pat = f"%{t}%"
        wheres.append(
            "(LOWER(COALESCE(p.sku, '')) LIKE ? OR LOWER(COALESCE(p.name, '')) LIKE ?)"
        )
        params.extend([pat, pat])

    for val, pcol in [
        (color_filter, "p.color"),
        (gender_filter, "p.gender"),
        (palette_filter, "p.palette"),
        (style_filter, "p.style"),
    ]:
        if val and str(val).strip() and str(val) != "Any":
            wheres.append(f"TRIM(COALESCE({pcol}, '')) = ?")
            params.append(str(val).strip())

    where_sql = " AND ".join(wheres)
    order_map = {
        "sku": "p.sku COLLATE NOCASE ASC",
        "name": "p.name COLLATE NOCASE ASC",
        "stock_desc": "p.stock DESC",
        "stock_asc": "p.stock ASC",
    }
    order_sql = order_map.get(sort_by, "p.sku COLLATE NOCASE ASC")

    base_from = """
        FROM products p
        LEFT JOIN sku_master sm ON sm.sku = p.sku
    """
    count_sql = f"SELECT COUNT(*) AS cnt {base_from} WHERE {where_sql}"
    data_sql = f"""
        SELECT p.id, p.sku, p.name, p.color, p.gender, p.palette, p.style,
               p.stock,
               COALESCE(sm.avg_unit_cost, p.cost, 0) AS avg_cost,
               COALESCE(sm.selling_price, p.price, 0) AS sell_price
        {base_from}
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
    """
    lim = max(1, min(int(limit), 500))
    off = max(0, int(offset))
    with get_conn() as conn:
        total = int(conn.execute(count_sql, params).fetchone()["cnt"])
        rows = conn.execute(data_sql, params + [lim, off]).fetchall()
    return rows, total


def fetch_product_by_id(product_id: int):
    """Single product row joined with sku_master for display."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT p.id, p.sku, p.name, p.color, p.gender, p.palette, p.style,
                   p.stock, p.registered_date, p.product_enter_code,
                   COALESCE(sm.avg_unit_cost, p.cost, 0) AS avg_cost,
                   COALESCE(sm.selling_price, p.price, 0) AS sell_price
            FROM products p
            LEFT JOIN sku_master sm ON sm.sku = p.sku
            WHERE p.id = ?;
            """,
            (int(product_id),),
        ).fetchone()


def add_product(
    name: str,
    stock: float,
    registered_date,
    color: str,
    style: str,
    palette: str,
    gender: str,
    unit_cost: float,
) -> None:
    """
    Register a product batch. SKU is [SEQ]-[PP]-[CC]-[GG]-[PA]-[ST] with a persistent sequence.

    Product registration typically uses stock=0; add stock via the Costing page (stock receipts).
    If stock > 0 here, unit_cost must be > 0 (weighted-average receipt).

    Raises ValueError if the generated SKU already exists on a different batch (not mergeable).
    """
    product_enter_code = make_product_enter_code(product_name=name, registered_date=registered_date)
    name = name.strip()
    color = (color or "").strip()
    style = (style or "").strip()
    palette = (palette or "").strip()
    gender = (gender or "").strip()

    if float(stock) > 0 and float(unit_cost) <= 0:
        raise ValueError("Unit cost is required and must be greater than zero when adding stock.")
    if float(stock) < 0:
        raise ValueError("Stock cannot be negative.")

    with get_conn() as conn:
        conn.isolation_level = None
        try:
            conn.execute("BEGIN IMMEDIATE;")
            registered_date_text = registered_date.isoformat()
            existing = conn.execute(
                """
                SELECT id
                FROM products
                WHERE name = ? AND registered_date = ?
                  AND COALESCE(color, '') = ?
                  AND COALESCE(style, '') = ?
                  AND COALESCE(palette, '') = ?
                  AND COALESCE(gender, '') = ?;
                """,
                (
                    name,
                    registered_date_text,
                    color,
                    style,
                    palette,
                    gender,
                ),
            ).fetchone()

            if existing is not None:
                pid = int(existing["id"])
                row_sku = conn.execute(
                    "SELECT sku FROM products WHERE id = ?;",
                    (pid,),
                ).fetchone()
                sku = str(row_sku["sku"] or "").strip()
                conn.execute(
                    """
                    UPDATE products
                    SET product_enter_code = COALESCE(product_enter_code, ?),
                        sku = ?
                    WHERE id = ?;
                    """,
                    (product_enter_code, sku, pid),
                )
                if float(stock) > 0:
                    ensure_sku_master(conn, sku)
                    apply_stock_receipt(conn, sku, pid, float(stock), float(unit_cost))
            else:
                n = _next_sku_sequence(conn)
                body = build_product_sku_body(name, color, gender, palette, style)
                sku = f"{format_sku_sequence_int(n)}-{body}"
                clash = conn.execute(
                    "SELECT id FROM products WHERE sku = ?;",
                    (sku,),
                ).fetchone()
                if clash is not None:
                    raise ValueError(
                        f"Duplicate SKU `{sku}` already exists. "
                        "Use a different product name or adjust attributes so the SKU is unique."
                    )
                ins_cur = conn.execute(
                    """
                    INSERT INTO products (
                        name, sku, registered_date, product_enter_code, cost, price, stock,
                        color, style, palette, gender
                    )
                    VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?);
                    """,
                    (
                        name,
                        sku,
                        registered_date_text,
                        product_enter_code,
                        color,
                        style,
                        palette,
                        gender,
                    ),
                )
                pid = int(ins_cur.lastrowid)
                if float(stock) > 0:
                    ensure_sku_master(conn, sku)
                    apply_stock_receipt(conn, sku, pid, float(stock), float(unit_cost))
                else:
                    ensure_sku_master(conn, sku)
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise


def set_product_pricing(product_id: int, cost: float, price: float) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE products
            SET cost = ?, price = ?
            WHERE id = ?;
            """,
            (cost, price, product_id),
        )


def set_product_pricing_for_batch(
    product_name: str,
    sku: str,
    registered_date_text: str,
    cost: float,
    price: float,
) -> int:
    """
    Freeze cost/price for all rows that belong to the same "batch":
    (product name + registered date + SKU) and still have stock in inventory.

    - cost: subtotal cost from the pricing worksheet (sum of lines).
    - price: **final unit price** from pricing (incl. markup, taxes & interest) — used for Sales and stock value.

    Returns how many product rows were updated.
    """
    with get_conn() as conn:
        # If there's already a priced in-stock batch for this code,
        # we must not overwrite it (unless the batch was excluded from stock/reset).
        locked = conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM products
            WHERE name = ?
              AND sku = ?
              AND registered_date = ?
              AND stock > 0
              AND pricing_locked = 1;
            """,
            (product_name, sku, registered_date_text),
        ).fetchone()["cnt"]

        if int(locked) > 0:
            return -1

        cur = conn.execute(
            """
            UPDATE products
            SET cost = ?,
                price = ?,
                pricing_locked = 1
            WHERE name = ?
              AND sku = ?
              AND registered_date = ?
              AND stock > 0;
            """,
            (cost, price, product_name, sku, registered_date_text),
        )
        return int(cur.rowcount or 0)


def reset_batch_pricing_and_exclude(product_enter_code: str) -> int:
    """
    Exclude the batch from stock and clear its pricing so it can be repriced later.
    Syncs SKU-level total_stock after stock is cleared.
    """
    with get_conn() as conn:
        skus = [
            str(r["sku"]).strip()
            for r in conn.execute(
                """
                SELECT DISTINCT sku FROM products
                WHERE product_enter_code = ? AND sku IS NOT NULL AND TRIM(sku) != '';
                """,
                (product_enter_code,),
            ).fetchall()
        ]
        cur = conn.execute(
            """
            UPDATE products
            SET stock = 0,
                cost = 0,
                price = 0,
                pricing_locked = 0
            WHERE product_enter_code = ?;
            """,
            (product_enter_code,),
        )
        n = int(cur.rowcount or 0)
        for sku in skus:
            sync_sku_master_totals(conn, sku)
        return n


def clear_batch_pricing_only(product_enter_code: str) -> int:
    """Clear cost/price only (keep stock as-is) for the given entering code."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE products
            SET cost = 0,
                price = 0,
                pricing_locked = 0
            WHERE product_enter_code = ?;
            """,
            (product_enter_code,),
        )
        return int(cur.rowcount or 0)


def record_sale(
    product_id: int,
    quantity: int,
    customer_id: int,
    discount_amount: float,
) -> Tuple[str, float]:
    """
    Atomically:
    - validate customer exists
    - read SKU selling price from sku_master and WAC (COGS)
    - verify stock >= quantity
    - update stock and sku_master totals (WAC unchanged on sale)
    - allocate sequential sale_code (#####V) and insert full sale row

    Returns (sale_code, final_total_after_discount).
    """
    qty = int(quantity)
    if qty < 1:
        raise ValueError("Quantity must be greater than zero.")
    disc = float(discount_amount)
    if disc < 0:
        raise ValueError("Discount cannot be negative.")

    with get_conn() as conn:
        conn.isolation_level = None
        try:
            conn.execute("BEGIN IMMEDIATE;")
            cust = conn.execute(
                "SELECT id FROM customers WHERE id = ?;",
                (int(customer_id),),
            ).fetchone()
            if cust is None:
                raise ValueError("Customer not found.")

            row = conn.execute(
                """
                SELECT p.stock, p.sku, p.deleted_at AS p_del,
                       sm.deleted_at AS sm_del,
                       COALESCE(sm.selling_price, 0) AS sp,
                       COALESCE(sm.avg_unit_cost, 0) AS avg_cogs
                FROM products p
                LEFT JOIN sku_master sm ON sm.sku = p.sku
                WHERE p.id = ?;
                """,
                (product_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Product not found.")
            if row["p_del"] or row["sm_del"]:
                raise ValueError("This product/SKU is inactive (soft-deleted) and cannot be sold.")

            sku = (row["sku"] or "").strip()
            if not sku:
                raise ValueError("Product has no SKU; cannot record sale.")

            selling_price = float(row["sp"])
            if selling_price <= 0:
                raise ValueError("Set a selling price for this SKU on the Pricing page before selling.")

            stock = float(row["stock"] or 0)
            gross_total = selling_price * float(qty)

            if float(qty) > stock + 1e-9:
                raise ValueError(f"Insufficient stock. Available: {stock}")

            if disc > gross_total + 1e-9:
                raise ValueError("Discount cannot exceed the base amount (unit price × quantity).")

            final_total = gross_total - disc
            avg_cogs = float(row["avg_cogs"])
            cogs_total = float(qty) * avg_cogs

            conn.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ?;",
                (qty, product_id),
            )
            sync_sku_master_totals(conn, sku)

            seq_n = _next_sale_sequence(conn)
            sale_code = format_sale_code(seq_n)

            conn.execute(
                """
                INSERT INTO sales (
                    sale_code, product_id, customer_id, quantity, unit_price, discount_amount,
                    base_amount, total, sold_at, sku, cogs_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    sale_code,
                    product_id,
                    int(customer_id),
                    qty,
                    selling_price,
                    disc,
                    gross_total,
                    final_total,
                    datetime.now().isoformat(timespec="seconds"),
                    sku,
                    cogs_total,
                ),
            )
            conn.execute("COMMIT;")
            return sale_code, final_total
        except Exception:
            conn.execute("ROLLBACK;")
            raise


def compute_dashboard():
    with get_conn() as conn:
        revenue = conn.execute("SELECT COALESCE(SUM(total), 0) AS revenue FROM sales;").fetchone()[
            "revenue"
        ]
        sales_count = conn.execute("SELECT COUNT(*) AS cnt FROM sales;").fetchone()["cnt"]
        total_stock_units = float(
            conn.execute("SELECT COALESCE(SUM(stock), 0) AS cnt FROM products;").fetchone()["cnt"]
        )
        low_stock = conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM products
            WHERE stock <= 5
            """
        ).fetchone()["cnt"]

    return {
        "revenue": float(revenue),
        "sales_count": int(sales_count),
        "total_stock_units": total_stock_units,
        "low_stock": int(low_stock),
    }


def compute_sales_financials():
    """
    Financial summary based strictly on recorded sales:
    - revenue: SUM(sales.total)
    - cost: SUM(sales.cogs_total) — COGS at sale time (SKU weighted-average cost × qty)
    - profit/loss: revenue - cost
    """
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(s.total), 0) AS revenue,
                COALESCE(SUM(s.cogs_total), 0) AS cost
            FROM sales s;
            """
        ).fetchone()

    revenue = float(row["revenue"])
    cost = float(row["cost"])
    profit_loss = revenue - cost
    return revenue, cost, profit_loss


def fetch_revenue_timeseries():
    """Revenue aggregated by day (for the dashboard chart)."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                DATE(sold_at) AS day,
                SUM(total) AS revenue
            FROM sales
            GROUP BY day
            ORDER BY day;
            """
        ).fetchall()

    if not rows:
        return pd.DataFrame(columns=["day", "revenue"])

    df = pd.DataFrame([{"day": r["day"], "revenue": r["revenue"]} for r in rows])
    df["revenue"] = df["revenue"].astype(float)
    return df


def main():
    st.set_page_config(page_title="ALIEH Business Manager", layout="wide")
    init_db()

    # Responsive app shell: flex row (sidebar + main). Collapsed sidebar → main uses full width.
    st.markdown(
        """
        <style>
        /* App shell: flex layout (not fixed positioning) */
        [data-testid="stAppViewContainer"] {
            width: 100% !important;
            max-width: 100vw !important;
            box-sizing: border-box !important;
        }

        [data-testid="stAppViewContainer"] > div {
            width: 100% !important;
            max-width: 100% !important;
        }

        /* Row that holds sidebar + main */
        [data-testid="stAppViewContainer"] > div:has(> section[data-testid="stSidebar"]) {
            display: flex !important;
            flex-direction: row !important;
            align-items: stretch !important;
            width: 100% !important;
            min-width: 0 !important;
            flex: 1 1 auto !important;
        }

        /* Sidebar expanded — 240px track */
        section[data-testid="stSidebar"] {
            flex: 0 0 240px !important;
            width: 240px !important;
            min-width: 240px !important;
            max-width: 240px !important;
            box-sizing: border-box !important;
            position: relative !important;
        }

        section[data-testid="stSidebar"] > div {
            width: 100% !important;
        }

        /* Sidebar collapsed — no layout width (Streamlit sets aria-expanded + translateX) */
        section[data-testid="stSidebar"][aria-expanded="false"] {
            flex: 0 0 0 !important;
            width: 0 !important;
            min-width: 0 !important;
            max-width: 0 !important;
            overflow: visible !important;
            border: none !important;
            padding: 0 !important;
        }

        /* Main content: grows to fill remaining space */
        section.main,
        [data-testid="stMain"] {
            flex: 1 1 0% !important;
            min-width: 0 !important;
            width: 100% !important;
            max-width: 100% !important;
            margin-left: 0 !important;
            box-sizing: border-box !important;
        }

        /* Collapsed sidebar: remove phantom left inset; stretch edge-to-edge */
        section[data-testid="stSidebar"][aria-expanded="false"] ~ section.main,
        section[data-testid="stSidebar"][aria-expanded="false"] ~ [data-testid="stMain"] {
            margin-left: 0 !important;
            padding-left: 0.75rem !important;
            max-width: 100% !important;
        }

        section.main .block-container,
        [data-testid="stMain"] .block-container {
            max-width: 100% !important;
            margin-left: 0 !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            box-sizing: border-box !important;
        }

        section[data-testid="stSidebar"][aria-expanded="false"] ~ section.main .block-container,
        section[data-testid="stSidebar"][aria-expanded="false"] ~ [data-testid="stMain"] .block-container {
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }

        /* Fallback: Streamlit collapses with translateX(-Npx) on the sidebar */
        section[data-testid="stSidebar"][style*="translateX(-"] {
            flex: 0 0 0 !important;
            width: 0 !important;
            min-width: 0 !important;
            max-width: 0 !important;
            overflow: visible !important;
            padding: 0 !important;
        }
        section[data-testid="stSidebar"][style*="translateX(-"] ~ section.main,
        section[data-testid="stSidebar"][style*="translateX(-"] ~ [data-testid="stMain"] {
            margin-left: 0 !important;
            padding-left: 0.75rem !important;
            max-width: 100% !important;
        }
        section[data-testid="stSidebar"][style*="translateX(-"] ~ section.main .block-container,
        section[data-testid="stSidebar"][style*="translateX(-"] ~ [data-testid="stMain"] .block-container {
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Business Management System")
    st.caption("Clean, simple products + sales + dashboard (SQLite-backed).")

    page = st.sidebar.radio(
        "Navigation",
        [
            "Products",
            "Stock",
            "Costing",
            "Pricing",
            "Sales",
            "Customers",
            "Dashboard",
        ],
        index=0,
    )

    if page == "Products":
        st.markdown("### Products")
        st.caption(
            "Use **SKU search & lookup** to find batches, or register new ones below."
        )

        attr_opts = fetch_product_search_attribute_options()
        with st.expander("SKU search & lookup", expanded=False):
            st.caption(
                "Partial match on **SKU** or **product name** (contains). Combine filters; results update on each change."
            )
            tq = st.text_input(
                "Search SKU or product name",
                key="sku_search_text_q",
                placeholder="e.g. 001, SUN, partial name…",
            )
            r1a, r1b = st.columns(2)
            with r1a:
                sort_by = st.selectbox(
                    "Sort by",
                    ["sku", "name", "stock_desc", "stock_asc"],
                    index=0,
                    format_func=lambda k: {
                        "sku": "SKU (A–Z)",
                        "name": "Name (A–Z)",
                        "stock_desc": "Stock (high → low)",
                        "stock_asc": "Stock (low → high)",
                    }[k],
                    key="sku_search_sort",
                )
            with r1b:
                page_size = st.selectbox("Rows per page", [25, 50, 100, 200], index=0, key="sku_search_ps")

            fc1, fc2, fc3, fc4 = st.columns(4)
            with fc1:
                cf = st.selectbox("Color", ["Any"] + attr_opts["color"], key="sku_search_color")
            with fc2:
                gf = st.selectbox("Gender", ["Any"] + attr_opts["gender"], key="sku_search_gender")
            with fc3:
                pf = st.selectbox("Palette", ["Any"] + attr_opts["palette"], key="sku_search_palette")
            with fc4:
                sf = st.selectbox("Style", ["Any"] + attr_opts["style"], key="sku_search_style")

            _, total_match = search_products_filtered(
                tq, cf, gf, pf, sf, sort_by, 1, 0
            )
            total_pages = max(1, (total_match + page_size - 1) // page_size)
            if st.session_state.get("sku_search_page", 1) > total_pages:
                st.session_state["sku_search_page"] = total_pages
            pg1, pg2, pg3 = st.columns([1, 1, 2])
            with pg1:
                page_num = st.number_input(
                    "Page",
                    min_value=1,
                    max_value=total_pages,
                    value=1,
                    step=1,
                    key="sku_search_page",
                )
            with pg2:
                st.metric("Matches", total_match)
            with pg3:
                st.caption(
                    f"Page **{page_num}** / **{total_pages}** · **{total_match}** row(s) match filters."
                )

            rows, _ = search_products_filtered(
                tq, cf, gf, pf, sf, sort_by, page_size, (page_num - 1) * page_size
            )

            if not rows:
                st.info("No products match these filters.")
            else:
                df = pd.DataFrame(
                    [
                        {
                            "ID": r["id"],
                            "SKU": r["sku"] or "—",
                            "Name": r["name"] or "—",
                            "Color": r["color"] or "—",
                            "Gender": r["gender"] or "—",
                            "Palette": r["palette"] or "—",
                            "Style": r["style"] or "—",
                            "Stock": float(r["stock"] or 0),
                            "Avg cost": float(r["avg_cost"] or 0),
                            "Price": float(r["sell_price"] or 0),
                        }
                        for r in rows
                    ]
                )
                st.dataframe(
                    df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Avg cost": st.column_config.NumberColumn(format="$%.2f"),
                        "Price": st.column_config.NumberColumn(format="$%.2f"),
                        "Stock": st.column_config.NumberColumn(format="%.4f"),
                    },
                )

                pick_labels = [
                    f"{r['id']}  |  {r['sku'] or '—'}  |  {r['name'] or '—'}" for r in rows
                ]
                pick = st.selectbox(
                    "Select a product (focus)",
                    ["—"] + pick_labels,
                    key="sku_search_product_focus",
                )
                if pick != "—":
                    focus_id = int(pick.split("|", 1)[0].strip())
                    st.session_state["products_focus_product_id"] = focus_id
                    pr = fetch_product_by_id(focus_id)
                    if pr is not None:
                        st.success(
                            f"Focused **product ID `{pr['id']}`** — SKU `{pr['sku'] or '—'}`."
                        )
                        with st.container(border=True):
                            st.markdown(
                                f"- **SKU:** `{pr['sku'] or '—'}`\n"
                                f"- **Name:** {pr['name']}\n"
                                f"- **Color · Gender · Palette · Style:** "
                                f"{pr['color'] or '—'} · {pr['gender'] or '—'} · "
                                f"{pr['palette'] or '—'} · {pr['style'] or '—'}\n"
                                f"- **Stock:** {format_qty_display_4(float(pr['stock'] or 0))}\n"
                                f"- **Avg cost (SKU):** {format_money(float(pr['avg_cost'] or 0))}\n"
                                f"- **Price (SKU):** {format_money(float(pr['sell_price'] or 0))}\n"
                                f"- **Enter code:** {pr['product_enter_code'] or '—'}"
                            )
                            st.caption(
                                "Use this SKU on **Stock**, **Costing**, **Pricing**, and **Sales**."
                            )

        st.markdown("### Product registration")
        st.caption(
            "Only register new product batches here (identity + attributes). Excluding from stock is done in `Stock`. "
            "If you register the same **name + register date + color + style + palette + gender**, the batch is merged. "
            "**SKU** is generated automatically as `[SEQ]-[PP]-[CC]-[GG]-[PA]-[ST]`. "
            "Add **stock** and **unit cost** on the **Costing** page (weighted-average inventory per SKU)."
        )

        # No st.form here: form widgets buffer values until submit, which breaks live SKU preview and
        # session_state sync. Inputs keep their values on validation errors via widget keys.
        name = st.text_input(
            "Product name",
            placeholder="e.g., Sunglasses Model A",
            key="prod_reg_name",
        )
        registered_date = st.date_input(
            "Register date",
            value=datetime.now().date(),
            key="prod_reg_date",
        )
        c1, c2 = st.columns(2)
        with c1:
            color_opts = dropdown_with_other(PRODUCT_COLOR_OPTIONS)
            color_choice = attribute_selectbox(
                "Color", color_opts, key="prod_reg_color", current_value=""
            )

            palette_opts = dropdown_with_other(PRODUCT_PALETTE_OPTIONS)
            palette_choice = attribute_selectbox(
                "Palette", palette_opts, key="prod_reg_palette", current_value=""
            )
        with c2:
            gender_opts = dropdown_with_other(PRODUCT_GENDER_OPTIONS)
            gender_choice = attribute_selectbox(
                "Gender", gender_opts, key="prod_reg_gender", current_value=""
            )

            style_opts = dropdown_with_other(PRODUCT_STYLE_OPTIONS)
            style_choice = attribute_selectbox(
                "Style", style_opts, key="prod_reg_style", current_value=""
            )

        preview_sku = _maybe_preview_product_sku()
        if preview_sku:
            st.info(f"**Generated SKU (read-only):** `{preview_sku}`")
        else:
            st.caption("Select all attributes to preview the SKU. It cannot be edited manually.")

        if st.button("Register product", type="primary", key="prod_reg_submit"):
            if not name.strip():
                st.error("Product name is required.")
            else:
                color_val, err_c = resolve_attribute_value(color_choice, "", "color")
                palette_val, err_p = resolve_attribute_value(palette_choice, "", "palette")
                gender_val, err_g = resolve_attribute_value(gender_choice, "", "gender")
                style_val, err_s = resolve_attribute_value(style_choice, "", "style")
                field_errors = [e for e in (err_c, err_p, err_g, err_s) if e]
                if field_errors:
                    for e in field_errors:
                        st.error(e)
                else:
                    try:
                        add_product(
                            name=name,
                            stock=0,
                            registered_date=registered_date,
                            color=color_val,
                            style=style_val,
                            palette=palette_val,
                            gender=gender_val,
                            unit_cost=0.0,
                        )
                    except ValueError as e:
                        st.error(str(e))
                    else:
                        product_enter_code = make_product_enter_code(
                            product_name=name, registered_date=registered_date
                        )
                        st.info(f"Product entering code: {product_enter_code}")
                        st.success("Product batch registered.")
                        for k in (
                            "prod_reg_name",
                            "prod_reg_date",
                            "prod_reg_color",
                            "prod_reg_palette",
                            "prod_reg_gender",
                            "prod_reg_style",
                        ):
                            if k in st.session_state:
                                del st.session_state[k]
                        st.rerun()

    elif page == "Sales":
        st.markdown("### Sales")
        st.caption(
            "Workflow: **1) SKU** → **2) Customer** → **3) Quantity** → **4) Discount** → **Confirm**. "
            "Each sale gets a traceable **sale ID** (#####V). Stock is deducted from the selected **batch**."
        )

        sales_skus = fetch_skus_available_for_sale()
        customers_all = fetch_customers_ordered()

        product_id: Optional[int] = None
        sku_sel = ""
        unit_price = 0.0
        available_stock = 0.0
        batch_row = None

        # --- STEP 1 — SELECT SKU ---
        st.markdown("#### Step 1 — Select SKU")
        if not sales_skus:
            st.info(
                "No SKUs are ready to sell. Add **stock** (Costing) and set an **active price** (Pricing) first."
            )
        else:
            sku_labels = [
                f"{r['sku']}  —  {r['sample_name'] or '—'}  (SKU stock: {float(r['total_stock'] or 0):g})"
                for r in sales_skus
            ]
            sku_map = {sku_labels[i]: sales_skus[i] for i in range(len(sku_labels))}
            picked_sku_label = st.selectbox(
                "Choose SKU",
                options=sku_labels,
                key="sales_step1_sku_label",
            )
            row_sku = sku_map[picked_sku_label]
            sku_sel = str(row_sku["sku"] or "").strip()
            unit_price = float(row_sku["selling_price"] or 0)

            batches = fetch_product_batches_for_sku(sku_sel)
            if not batches:
                st.error("This SKU has no in-stock batches (data may have changed). Refresh the page.")
            elif len(batches) == 1:
                batch_row = batches[0]
                product_id = int(batch_row["id"])
                st.caption("Single inventory batch for this SKU — used automatically.")
            else:
                batch_labels = [
                    f"{b['product_enter_code'] or '—'} | batch stock {float(b['stock']):g} | {b['name']}"
                    for b in batches
                ]
                bl = st.selectbox(
                    "Select inventory batch (multiple batches for this SKU)",
                    options=batch_labels,
                    key="sales_step1_batch_pick",
                )
                batch_row = batches[batch_labels.index(bl)]
                product_id = int(batch_row["id"])

            if product_id is not None:
                with get_conn() as conn:
                    pr = conn.execute(
                        "SELECT stock, name, sku FROM products WHERE id = ?;",
                        (product_id,),
                    ).fetchone()
                if pr is None:
                    st.error("Selected batch no longer exists.")
                    product_id = None
                else:
                    available_stock = float(pr["stock"] or 0)
                    with st.container(border=True):
                        st.markdown(f"**SKU:** `{sku_sel}`")
                        st.markdown(
                            f"**Product / batch:** {pr['name']}  ·  code **{batch_row['product_enter_code'] or '—'}**"
                        )
                        attrs = " · ".join(
                            x
                            for x in (
                                batch_row["color"],
                                batch_row["style"],
                                batch_row["palette"],
                                batch_row["gender"],
                            )
                            if x
                        )
                        if attrs:
                            st.caption(attrs)
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Stock (this batch)", f"{available_stock:g}")
                        c2.metric("SKU total stock (all batches)", f"{float(row_sku['total_stock'] or 0):g}")
                        c3.metric("Active unit price (Pricing)", format_money(unit_price))

        st.divider()

        # --- STEP 2 — SELECT CUSTOMER ---
        st.markdown("#### Step 2 — Select customer")
        cust_id: Optional[int] = None
        cust_display = "—"
        if not customers_all:
            st.warning("No customers found. Add one under **Customers** before selling.")
        else:
            search_q = st.text_input(
                "Search by name or customer code",
                key="sales_cust_search",
                placeholder="Filter the list…",
            )
            filtered_c = filter_customers_by_search(customers_all, search_q)
            if not filtered_c:
                st.warning("No customer matches the current search.")
            else:
                cust_labels = [
                    f"{c['customer_code']} — {c['name']}" for c in filtered_c
                ]
                cust_pick = st.selectbox(
                    "Customer",
                    options=cust_labels,
                    key="sales_cust_select",
                )
                idx_c = cust_labels.index(cust_pick)
                cust_id = int(filtered_c[idx_c]["id"])
                cust_display = cust_pick

        st.divider()

        # --- STEP 3 — QUANTITY ---
        st.markdown("#### Step 3 — Quantity")
        max_sale_qty = int(math.floor(available_stock + 1e-9))
        if product_id is None or available_stock <= 0:
            st.caption("Complete **Step 1** to enter quantity.")
            quantity = 0
        elif max_sale_qty < 1:
            st.warning(
                f"Available stock in this batch is **{available_stock:g}**, which is not enough "
                "to sell a whole unit at quantity **1**. Add stock or pick another batch."
            )
            quantity = 0
        else:
            st.caption(f"Available in this batch: **{available_stock:g}** (cannot sell more than stock).")
            quantity = int(
                st.number_input(
                    "Quantity to sell",
                    min_value=1,
                    max_value=max_sale_qty,
                    step=1,
                    value=min(1, max_sale_qty),
                    format="%d",
                    key=f"sales_qty_{product_id}",
                )
            )

        st.divider()

        # --- STEP 4 — DISCOUNT ---
        st.markdown("#### Step 4 — Apply discount")
        disc_mode = st.radio(
            "Discount type",
            ["Percent (%)", "Fixed amount"],
            horizontal=True,
            key="sales_disc_mode",
        )
        base_price = float(quantity) * unit_price if product_id else 0.0
        if disc_mode.startswith("Percent"):
            pct = float(
                st.number_input(
                    "Discount percent",
                    min_value=0.0,
                    max_value=100.0,
                    step=0.1,
                    value=0.0,
                    format="%.2f",
                    key="sales_disc_pct",
                )
            )
            discount_amount = min(base_price, base_price * (pct / 100.0))
        else:
            dv = float(
                st.number_input(
                    "Discount amount",
                    min_value=0.0,
                    step=0.01,
                    value=0.0,
                    format="%.2f",
                    key="sales_disc_amt",
                )
            )
            discount_amount = min(base_price, dv)

        final_price = base_price - discount_amount
        m1, m2, m3 = st.columns(3)
        m1.metric("Base price (price × qty)", format_money(base_price))
        m2.metric("Discount", format_money(discount_amount))
        m3.metric("Final price", format_money(final_price))

        st.divider()

        # --- SUMMARY & CONFIRM ---
        st.markdown("#### Review & confirm")
        ready = (
            product_id is not None
            and cust_id is not None
            and unit_price > 0
            and quantity >= 1
            and float(quantity) <= available_stock + 1e-9
        )
        if not ready:
            st.info("Complete all steps above. Quantity must be **> 0** and **≤ available stock**.")
        else:
            with st.container(border=True):
                st.markdown("**Sale summary**")
                sum_tbl = {
                    "SKU": f"`{sku_sel}`",
                    "Customer": cust_display,
                    "Quantity": str(quantity),
                    "Unit price": format_money(unit_price),
                    "Base price": format_money(base_price),
                    "Discount": format_money(discount_amount),
                    "Final price": format_money(final_price),
                }
                st.table(
                    [{"Field": k, "Value": v} for k, v in sum_tbl.items()]
                )

            confirm = st.checkbox(
                "I confirm this sale (stock will be reduced and a sale record will be created).",
                key="sales_confirm_chk",
            )
            if st.button(
                "Complete sale",
                type="primary",
                key="sales_confirm_btn",
                disabled=not confirm,
            ):
                try:
                    code, total = record_sale(
                        product_id=int(product_id),
                        quantity=int(quantity),
                        customer_id=int(cust_id),
                        discount_amount=float(discount_amount),
                    )
                    st.success(
                        f"Sale **{code}** recorded. Final total: **{format_money(total)}**"
                    )
                    st.session_state.pop("sales_confirm_chk", None)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
                except Exception:
                    st.error("Failed to record sale. Please try again.")

        st.divider()
        st.markdown("#### Recent sales")
        with get_conn() as conn:
            recent = conn.execute(
                """
                SELECT
                    s.sale_code,
                    s.id,
                    p.name AS product_name,
                    s.sku,
                    CASE
                        WHEN s.customer_id IS NULL THEN '—'
                        ELSE (COALESCE(c.customer_code, '') || ' — ' || COALESCE(c.name, ''))
                    END AS customer_label,
                    s.quantity,
                    s.unit_price,
                    s.discount_amount,
                    s.total,
                    s.sold_at
                FROM sales s
                JOIN products p ON p.id = s.product_id
                LEFT JOIN customers c ON c.id = s.customer_id
                ORDER BY s.id DESC
                LIMIT 20;
                """
            ).fetchall()

        if not recent:
            st.info("No sales yet.")
        else:
            data = [
                {
                    "Sale ID": r["sale_code"] or f"#{r['id']}",
                    "SKU": r["sku"] or "—",
                    "Product": r["product_name"],
                    "Customer": r["customer_label"],
                    "Qty": r["quantity"],
                    "Unit": format_money(float(r["unit_price"] or 0)),
                    "Discount": format_money(float(r["discount_amount"] or 0)),
                    "Final": format_money(float(r["total"] or 0)),
                    "Sold at": r["sold_at"],
                }
                for r in recent
            ]
            st.dataframe(data, width="stretch", hide_index=True)

    elif page == "Dashboard":  # Dashboard
        st.markdown("### Dashboard")
        stats = compute_dashboard()
        revenue, cost, profit_loss = compute_sales_financials()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Revenue", format_money(stats["revenue"]))
        col2.metric("Sales", stats["sales_count"])
        col3.metric("Total products in stock", stats["total_stock_units"])
        col4.metric("Low Stock (<=5)", stats["low_stock"])

        st.divider()
        st.markdown("### Profit / Loss Menu (from sales executed)")
        menu_col1, menu_col2, menu_col3 = st.columns(3)
        menu_col1.metric("Revenue", format_money(revenue))
        menu_col2.metric("Cost", format_money(cost))
        menu_col3.metric("Profit / Loss", format_money(profit_loss))

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown("#### Revenue trend")
            df = fetch_revenue_timeseries()
            if df.empty:
                st.info("No sales yet. Record your first sale to see revenue.")
            else:
                st.line_chart(df.set_index("day")["revenue"])

        with col_right:
            st.markdown("#### Low stock products")
            with get_conn() as conn:
                low = conn.execute(
                    """
                    SELECT p.id, p.name, COALESCE(sm.selling_price, p.price, 0) AS price, p.stock
                    FROM products p
                    LEFT JOIN sku_master sm ON sm.sku = p.sku
                    WHERE p.stock <= 5
                    ORDER BY p.stock ASC, p.id DESC
                    LIMIT 25;
                    """
                ).fetchall()

            if not low:
                st.success("No low-stock products. You are good.")
            else:
                data = [
                    {
                        "ID": r["id"],
                        "Name": r["name"],
                        "Sale price": format_money(r["price"]),
                        "Stock": r["stock"],
                    }
                    for r in low
                ]
                st.dataframe(data, width="stretch", hide_index=True)

    elif page == "Costing":
        st.markdown("### Costing")

        st.caption(
            "**SKU cost breakdown**: planned component costs (unit price × quantity), stored per SKU. "
            "**Weighted-average inventory cost (WAC)** updates from **stock receipts** only; sales do not change WAC. "
            "**Selling price** is on **Pricing**."
        )

        sku_rows = fetch_sku_master_rows()
        sku_list = [r["sku"] for r in sku_rows] if sku_rows else []

        st.markdown("#### SKU cost breakdown (planned components)")
        if not sku_list:
            st.info(
                "No SKUs in inventory master yet. Register a product in `Products`, then add stock (or ensure "
                "`sku_master` is populated) to use the cost breakdown."
            )
        else:
            sel_sku = st.selectbox(
                "SKU for cost breakdown",
                options=sku_list,
                key="costing_struct_sku_select",
            )
            marker = "costing_struct_session_sku"
            if st.session_state.get(marker) != sel_sku:
                st.session_state[marker] = sel_sku
                loaded = fetch_sku_cost_components_for_sku(sel_sku)
                by_row = {r["component_key"]: r for r in loaded}
                for key, _lbl in SKU_COST_COMPONENT_DEFINITIONS:
                    r = by_row.get(key)
                    q = float(r["quantity"] or 0) if r else 0.0
                    p = float(r["unit_price"] or 0) if r else 0.0
                    st.session_state[f"scq_{sel_sku}_{key}"] = format_qty_display_4(q)
                    st.session_state[f"scp_{sel_sku}_{key}"] = p

            st.caption(
                "Quantity: up to **4** decimal places (empty = 0). Unit price: **2** decimal places. "
                "Totals update as you edit."
            )

            with st.container(border=True):
                for key, label in SKU_COST_COMPONENT_DEFINITIONS:
                    st.markdown(f"**{label}**")
                    qcol, pcol, tcol = st.columns([1, 1, 1])
                    with qcol:
                        st.text_input(
                            "Quantity",
                            key=f"scq_{sel_sku}_{key}",
                            help="Up to 4 decimal places (e.g. 0.25, 1.0000).",
                        )
                    with pcol:
                        st.number_input(
                            "Unit price",
                            min_value=0.0,
                            step=0.01,
                            format="%.2f",
                            key=f"scp_{sel_sku}_{key}",
                        )
                    with tcol:
                        qt = st.session_state.get(f"scq_{sel_sku}_{key}", "")
                        up = float(st.session_state.get(f"scp_{sel_sku}_{key}", 0.0))
                        qv, qe = parse_cost_quantity_text(str(qt))
                        pv, pe = parse_cost_unit_price_value(up)
                        if qe or pe:
                            st.metric("Line total", "—")
                            if qe:
                                st.caption(qe)
                            if pe:
                                st.caption(pe)
                        else:
                            st.metric("Line total", format_money(qv * pv))

            live_total = 0.0
            err_msgs = []
            for key, label in SKU_COST_COMPONENT_DEFINITIONS:
                qt = st.session_state.get(f"scq_{sel_sku}_{key}", "")
                up = float(st.session_state.get(f"scp_{sel_sku}_{key}", 0.0))
                qv, qe = parse_cost_quantity_text(str(qt))
                pv, pe = parse_cost_unit_price_value(up)
                if qe:
                    err_msgs.append(f"{label} — quantity: {qe}")
                if pe:
                    err_msgs.append(f"{label} — unit price: {pe}")
                if not qe and not pe:
                    live_total += qv * pv

            st.metric("Total cost (SKU, live)", format_money(live_total))
            saved_row = next((r for r in sku_rows if r["sku"] == sel_sku), None)
            if saved_row is not None:
                st.caption(
                    f"Last saved total: **{format_money(float(saved_row['structured_cost_total'] or 0))}**"
                )

            if st.button("Save SKU cost breakdown", type="primary", key="costing_struct_save"):
                payload = []
                save_errs = []
                for key, label in SKU_COST_COMPONENT_DEFINITIONS:
                    qt = st.session_state.get(f"scq_{sel_sku}_{key}", "")
                    up = float(st.session_state.get(f"scp_{sel_sku}_{key}", 0.0))
                    qv, qe = parse_cost_quantity_text(str(qt))
                    pv, pe = parse_cost_unit_price_value(up)
                    if qe:
                        save_errs.append(f"{label} — quantity: {qe}")
                    if pe:
                        save_errs.append(f"{label} — unit price: {pe}")
                    payload.append((key, pv, qv))
                if save_errs:
                    for e in save_errs:
                        st.error(e)
                else:
                    try:
                        save_sku_cost_structure(sel_sku, payload)
                        st.success("SKU cost breakdown saved.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

            if err_msgs:
                st.warning("Fix validation errors above before saving.")

        if sku_rows:
            st.markdown("#### Current SKU inventory valuation")
            sm_data = [
                {
                    "SKU": r["sku"],
                    "Total stock": format_qty_display_4(float(r["total_stock"] or 0)),
                    "Avg unit cost (WAC)": format_money(float(r["avg_unit_cost"] or 0)),
                    "Structured cost total": format_money(float(r["structured_cost_total"] or 0)),
                    "Updated": r["updated_at"] or "—",
                }
                for r in sku_rows
            ]
            st.dataframe(sm_data, width="stretch", hide_index=True)

        st.markdown("#### Stock entry (SKU workflow)")
        st.caption(
            "**Step 1** — Select SKU (loads saved cost components). **Step 2** — Choose the receiving batch. "
            "**Step 3** — Enter quantity to add (> 0, up to 4 decimals). **Step 4** — Unit cost is your **saved** "
            "structured cost total (from the breakdown above). **Step 5** — Confirm the summary, then finalize — "
            "inventory WAC updates using the existing weighted-average logic."
        )

        if not sku_list:
            st.info("No SKUs available for stock entry yet.")
        else:
            stock_entry_sku = st.selectbox(
                "Step 1 — Select SKU",
                options=sku_list,
                key="costing_stock_entry_sku",
            )
            marker_stock = "costing_stock_entry_sku_marker"
            if st.session_state.get(marker_stock) != stock_entry_sku:
                st.session_state[marker_stock] = stock_entry_sku
                st.session_state["costing_stock_qty_text"] = ""

            loaded_components = fetch_sku_cost_components_for_sku(stock_entry_sku)
            with st.expander("Cost components loaded for this SKU (read-only)", expanded=False):
                comp_rows = [
                    {
                        "Component": r["label"],
                        "Unit price": format_money(float(r["unit_price"] or 0)),
                        "Qty": format_qty_display_4(float(r["quantity"] or 0)),
                        "Line": format_money(float(r["line_total"] or 0)),
                    }
                    for r in loaded_components
                ]
                st.dataframe(comp_rows, width="stretch", hide_index=True)

            batches = fetch_product_batches_for_sku(stock_entry_sku)
            if not batches:
                st.warning(
                    "No product batches exist for this SKU. Register a product in **Products** first "
                    "(same generated SKU)."
                )
            else:
                batch_labels = {}
                for p in batches:
                    attrs = " · ".join(
                        x
                        for x in (
                            p["color"] or "",
                            p["style"] or "",
                            p["palette"] or "",
                            p["gender"] or "",
                        )
                        if x
                    )
                    extra = f" ({attrs})" if attrs else ""
                    label = (
                        f"{p['name']}{extra} | Code: {p['product_enter_code'] or '—'} | "
                        f"Stock: {format_qty_display_4(float(p['stock'] or 0))}"
                    )
                    batch_labels[label] = p

                pick_b = st.selectbox(
                    "Step 2 — Receiving batch",
                    options=list(batch_labels.keys()),
                    key="costing_stock_entry_batch",
                )
                pr = batch_labels[pick_b]
                pid = int(pr["id"])
                psku = (pr["sku"] or "").strip()

                qty_raw = st.text_input(
                    "Step 3 — Quantity to add to stock",
                    key="costing_stock_qty_text",
                    help="Must be greater than zero. Up to 4 decimal places (e.g. 12.5000).",
                )
                qv, qe = parse_cost_quantity_text(str(qty_raw))
                try:
                    unit_cost = get_persisted_structured_unit_cost(stock_entry_sku)
                except ValueError:
                    unit_cost = 0.0

                st.markdown("**Step 4 — Unit cost (from saved cost structure)**")
                if unit_cost > 0:
                    st.metric("Calculated unit cost (per unit)", format_money(unit_cost))
                else:
                    st.warning(
                        "Structured unit cost is **zero** or missing. Save the **SKU cost breakdown** above "
                        "(non-zero component totals) before adding stock."
                    )

                total_entry = 0.0
                if qe is None and qv > 0 and unit_cost > 0:
                    total_entry = round(qv * unit_cost, 2)
                    st.metric("Total entry cost (unit cost × quantity)", format_money(total_entry))

                if qe:
                    st.error(qe)
                elif (qty_raw or "").strip() != "" and qv <= 0:
                    st.error("Quantity must be greater than zero.")

                st.markdown("**Confirmation summary**")
                st.write(f"- **SKU:** `{stock_entry_sku}`")
                st.write(
                    f"- **Quantity:** `{format_qty_display_4(qv) if qe is None else '—'}`"
                )
                st.write(f"- **Unit cost:** `{format_money(unit_cost) if unit_cost > 0 else '—'}`")
                st.write(
                    f"- **Total cost:** `{format_money(total_entry) if total_entry > 0 else '—'}`"
                )

                confirm_ok = st.checkbox(
                    "I confirm this stock entry is correct.",
                    key="costing_stock_confirm_chk",
                )

                can_finalize = (
                    confirm_ok
                    and qe is None
                    and qv > 0
                    and unit_cost > 0
                    and psku == stock_entry_sku.strip()
                )

                if st.button(
                    "Finalize stock entry",
                    type="primary",
                    key="costing_stock_finalize",
                    disabled=not can_finalize,
                ):
                    try:
                        add_stock_receipt(stock_entry_sku.strip(), pid, float(qv), float(unit_cost))
                        st.success(
                            "Stock entry recorded. Weighted-average inventory cost updated for this SKU."
                        )
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

        st.markdown("#### Stock cost history (audit)")
        entries = fetch_recent_stock_cost_entries(75)
        if not entries:
            st.caption("No stock receipts recorded yet.")
        else:
            eh = []
            for r in entries:
                rd = dict(r)
                te = rd.get("total_entry_cost")
                if te is None:
                    te = round(float(rd["quantity"] or 0) * float(rd["unit_cost"] or 0), 2)
                eh.append(
                    {
                        "ID": r["id"],
                        "SKU": r["sku"],
                        "Product ID": r["product_id"],
                        "Qty": format_qty_display_4(float(r["quantity"] or 0)),
                        "Unit cost": format_money(float(r["unit_cost"])),
                        "Total entry cost": format_money(float(te)),
                        "Stock before": format_qty_display_4(float(r["stock_before"] or 0)),
                        "Stock after": format_qty_display_4(float(r["stock_after"] or 0)),
                        "Avg before": format_money(float(r["avg_cost_before"])),
                        "Avg after": format_money(float(r["avg_cost_after"])),
                        "At": r["created_at"],
                    }
                )
            st.dataframe(eh, width="stretch", hide_index=True)

    elif page == "Pricing":
        st.markdown("### Pricing (per SKU)")

        st.caption(
            "**Step 1** — Select a SKU; **base cost** is the current **weighted-average inventory cost (WAC)**. "
            "**Step 2** — Enter markup, taxes, and interest as percentages (≥ 0). **Step 3** — Review calculated "
            "prices. **Step 4** — Save to append a **new** pricing record (never overwrites past rows). "
            "The **active** record is the latest save; **Sales** uses the **target price** from that record."
        )

        sku_rows = fetch_sku_master_rows()
        if not sku_rows:
            st.info("No SKUs in the system yet. Register products in `Products` first.")
            return

        sku_list = [r["sku"] for r in sku_rows]
        sel_sku = st.selectbox("Step 1 — Select SKU", options=sku_list, key="pricing_sku_select")

        sm = next((r for r in sku_rows if r["sku"] == sel_sku), None)
        if sm is None:
            st.error("SKU not found.")
            return

        wf_marker = "pricing_wf_sku_marker"
        if st.session_state.get(wf_marker) != sel_sku:
            st.session_state[wf_marker] = sel_sku
            active_row = fetch_active_sku_pricing_record(sel_sku)
            if active_row:
                st.session_state["pricing_wf_markup"] = float(active_row["markup_pct"])
                st.session_state["pricing_wf_taxes"] = float(active_row["taxes_pct"])
                st.session_state["pricing_wf_interest"] = float(active_row["interest_pct"])
            else:
                st.session_state["pricing_wf_markup"] = 0.0
                st.session_state["pricing_wf_taxes"] = 0.0
                st.session_state["pricing_wf_interest"] = 0.0

        c1, c2, c3 = st.columns(3)
        with c1:
            _ts = float(sm["total_stock"] or 0)
            st.metric(
                "Total stock (all batches)",
                format_qty_display_4(_ts) if abs(_ts) >= 1e-12 else "0",
            )
        with c2:
            avg_cost = float(sm["avg_unit_cost"] or 0)
            st.metric("Base cost — avg inventory (WAC)", format_money(avg_cost))
        with c3:
            st.metric("Current selling price (SKU)", format_money(float(sm["selling_price"] or 0)))

        if avg_cost <= 0:
            st.warning(
                "Average inventory cost is **not available** (WAC is zero). Add stock via **Costing** before pricing."
            )

        st.markdown("#### Step 2 — Pricing parameters (%)")
        st.caption("All values are percentages, stored with two decimal places (e.g. 10.50%).")
        pc1, pc2, pc3 = st.columns(3)
        with pc1:
            markup_pct = st.number_input(
                "Markup (%)",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="pricing_wf_markup",
            )
        with pc2:
            taxes_pct = st.number_input(
                "Taxes (%)",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="pricing_wf_taxes",
            )
        with pc3:
            interest_pct = st.number_input(
                "Interest (%)",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="pricing_wf_interest",
            )

        st.markdown("#### Step 3 — Calculated prices")
        if avg_cost > 0:
            pb, pwt, tgt = compute_sku_pricing_targets(
                avg_cost, float(markup_pct), float(taxes_pct), float(interest_pct)
            )
            st.caption(
                "1) Price before taxes = Avg cost + (Avg cost × Markup%). "
                "2) Price with taxes = (1) + ((1) × Taxes%). "
                "3) Target price = (2) + ((2) × Interest%)."
            )
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Price before taxes & interest", format_money(pb))
            with m2:
                st.metric("Price with taxes", format_money(pwt))
            with m3:
                st.metric("Target price (applied to Sales)", format_money(tgt))
        else:
            pb, pwt, tgt = (0.0, 0.0, 0.0)
            st.info("Enter stock receipts so average inventory cost (WAC) is greater than zero to see calculations.")

        st.markdown("#### Step 4 — Save price (new history record)")
        can_save = avg_cost > 0 and tgt > 0
        if st.button(
            "Save pricing (append record & set active)",
            type="primary",
            key=f"pricing_wf_save_{sel_sku}",
            disabled=not can_save,
        ):
            try:
                save_sku_pricing_workflow(
                    sel_sku,
                    float(markup_pct),
                    float(taxes_pct),
                    float(interest_pct),
                )
                st.success(
                    "Pricing saved. A new record was added; previous rows are kept. Target price is now active for Sales."
                )
                st.rerun()
            except ValueError as e:
                st.error(str(e))

        st.markdown("#### Pricing history (workflow records)")
        wf_rows = fetch_sku_pricing_records_for_sku(sel_sku, 100)
        if not wf_rows:
            st.caption("No workflow pricing records yet. Save above to create the first record.")
        else:
            wf_df = [
                {
                    "ID": r["id"],
                    "Active": "Yes" if int(r["is_active"] or 0) else "—",
                    "Avg cost (snapshot)": format_money(float(r["avg_cost_snapshot"])),
                    "Markup %": f"{float(r['markup_pct']):.2f}%",
                    "Taxes %": f"{float(r['taxes_pct']):.2f}%",
                    "Interest %": f"{float(r['interest_pct']):.2f}%",
                    "Price before taxes": format_money(float(r["price_before_taxes"])),
                    "Price with taxes": format_money(float(r["price_with_taxes"])),
                    "Target price": format_money(float(r["target_price"])),
                    "Saved at": r["created_at"],
                }
                for r in wf_rows
            ]
            st.dataframe(wf_df, width="stretch", hide_index=True)

        st.markdown("#### Selling price audit (legacy log)")
        st.caption("Includes workflow saves and any historical manual price updates.")
        ph = fetch_price_history_for_sku(sel_sku, 50)
        if not ph:
            st.caption("No entries in the legacy log yet.")
        else:
            ph_df = [
                {
                    "ID": r["id"],
                    "Old": format_money(float(r["old_price"])) if r["old_price"] is not None else "—",
                    "New": format_money(float(r["new_price"])),
                    "At": r["created_at"],
                    "Note": r["note"] or "",
                }
                for r in ph
            ]
            st.dataframe(ph_df, width="stretch", hide_index=True)

    elif page == "Customers":
        st.markdown("### Customers")
        st.caption(
            "Register customers with optional **ViaCEP** address lookup. "
            "**Customer code** is a 5-digit auto ID (not editable). "
            "Saving is blocked if **CPF** or **phone** (digits) already exists for another customer."
        )
        try:
            preview = peek_next_customer_code_preview()
        except Exception:
            preview = "—"
        st.info(
            f"Next customer code on save: **{preview}** (preview only — assigned when you save)."
        )

        tab_reg, tab_edit = st.tabs(["Register", "Edit customer"])

        def _init_cust_edit_session(r: sqlite3.Row, cid: int) -> None:
            st.session_state[f"cust_edit_name_{cid}"] = r["name"] or ""
            st.session_state[f"cust_edit_cpf_{cid}"] = r["cpf"] or ""
            st.session_state[f"cust_edit_rg_{cid}"] = r["rg"] or ""
            st.session_state[f"cust_edit_phone_{cid}"] = r["phone"] or ""
            st.session_state[f"cust_edit_email_{cid}"] = r["email"] or ""
            st.session_state[f"cust_edit_instagram_{cid}"] = r["instagram"] or ""
            st.session_state[f"cust_edit_cep_{cid}"] = r["zip_code"] or ""
            st.session_state[f"cust_edit_street_{cid}"] = r["street"] or ""
            st.session_state[f"cust_edit_number_{cid}"] = r["number"] or ""
            st.session_state[f"cust_edit_neighborhood_{cid}"] = r["neighborhood"] or ""
            st.session_state[f"cust_edit_city_{cid}"] = r["city"] or ""
            st.session_state[f"cust_edit_state_{cid}"] = r["state"] or ""
            st.session_state[f"cust_edit_country_{cid}"] = r["country"] or ""

        with tab_reg:
            st.markdown("#### Register new customer")
            cep_row = st.columns([3, 1])
            with cep_row[0]:
                st.text_input(
                    "CEP (ZIP)",
                    key="cust_reg_cep",
                    placeholder="00000-000",
                    help="Enter 8 digits and click **Buscar CEP** to fill street, neighborhood, city, and state.",
                )
            with cep_row[1]:
                st.write("")
                if st.button("Buscar CEP", key="cust_reg_cep_btn", type="secondary"):
                    with st.spinner("Buscando endereço..."):
                        data, err = fetch_viacep_address(
                            st.session_state.get("cust_reg_cep", "")
                        )
                    if err:
                        st.error(err)
                    else:
                        st.session_state["cust_reg_street"] = data["street"]
                        st.session_state["cust_reg_neighborhood"] = data["neighborhood"]
                        st.session_state["cust_reg_city"] = data["city"]
                        st.session_state["cust_reg_state"] = data["state"]
                        st.success("Address loaded — you can edit the fields below.")
                        st.rerun()

            with st.form("cust_reg_form"):
                c1, c2 = st.columns(2)
                with c1:
                    st.text_input(
                        "Name *",
                        key="cust_reg_name",
                        placeholder="Full name",
                    )
                    st.text_input(
                        "CPF",
                        key="cust_reg_cpf",
                        placeholder="000.000.000-00",
                    )
                    st.text_input("RG", key="cust_reg_rg")
                    st.text_input(
                        "Phone",
                        key="cust_reg_phone",
                        placeholder="+55 …",
                    )
                with c2:
                    st.text_input("Email", key="cust_reg_email")
                    st.text_input(
                        "Instagram profile",
                        key="cust_reg_instagram",
                        placeholder="@user or URL",
                    )

                st.markdown("##### Address")
                st1, st2 = st.columns([3, 1])
                with st1:
                    st.text_input("Street", key="cust_reg_street")
                with st2:
                    st.text_input("Number", key="cust_reg_number")
                st3, st4 = st.columns(2)
                with st3:
                    st.text_input("Neighborhood", key="cust_reg_neighborhood")
                with st4:
                    st.text_input("City", key="cust_reg_city")
                st5, st6 = st.columns(2)
                with st5:
                    st.text_input("State (UF)", key="cust_reg_state", max_chars=2)
                with st6:
                    st.text_input(
                        "Country",
                        key="cust_reg_country",
                        placeholder="Brasil",
                    )

                reg_submitted = st.form_submit_button("Save customer", type="primary")

            if reg_submitted:
                name_val = (st.session_state.get("cust_reg_name") or "").strip()
                if not name_val:
                    st.error("Name is required.")
                else:
                    cep_digits = sanitize_cep_digits(
                        st.session_state.get("cust_reg_cep", "")
                    )
                    if cep_digits and len(cep_digits) != 8:
                        st.error(
                            "If CEP is filled, it must have exactly 8 digits (valid for lookup)."
                        )
                    else:
                        cpf_raw = st.session_state.get("cust_reg_cpf", "")
                        cpf_norm = normalize_cpf_digits(cpf_raw)
                        if cpf_norm and not validate_cpf_br(cpf_norm):
                            st.error("CPF is invalid (check digits).")
                        elif not validate_email_optional(
                            st.session_state.get("cust_reg_email", "")
                        ):
                            st.error("Email format is invalid.")
                        else:
                            phone_norm = normalize_phone_digits(
                                st.session_state.get("cust_reg_phone", "")
                            )
                            try:
                                new_code = insert_customer_row(
                                    name=name_val,
                                    cpf=cpf_norm if cpf_norm else None,
                                    rg=(st.session_state.get("cust_reg_rg") or "").strip()
                                    or None,
                                    phone=phone_norm if phone_norm else None,
                                    email=(st.session_state.get("cust_reg_email") or "").strip()
                                    or None,
                                    instagram=(
                                        st.session_state.get("cust_reg_instagram") or ""
                                    ).strip()
                                    or None,
                                    zip_code=cep_digits if cep_digits else None,
                                    street=(
                                        st.session_state.get("cust_reg_street") or ""
                                    ).strip()
                                    or None,
                                    number=(
                                        st.session_state.get("cust_reg_number") or ""
                                    ).strip()
                                    or None,
                                    neighborhood=(
                                        st.session_state.get("cust_reg_neighborhood") or ""
                                    ).strip()
                                    or None,
                                    city=(st.session_state.get("cust_reg_city") or "").strip()
                                    or None,
                                    state=(st.session_state.get("cust_reg_state") or "").strip()
                                    or None,
                                    country=(
                                        st.session_state.get("cust_reg_country") or ""
                                    ).strip()
                                    or None,
                                )
                            except ValueError as e:
                                st.error(str(e))
                            else:
                                st.success(f"Customer **{new_code}** saved.")
                                for k in (
                                    "cust_reg_cep",
                                    "cust_reg_street",
                                    "cust_reg_number",
                                    "cust_reg_neighborhood",
                                    "cust_reg_city",
                                    "cust_reg_state",
                                    "cust_reg_country",
                                    "cust_reg_name",
                                    "cust_reg_cpf",
                                    "cust_reg_rg",
                                    "cust_reg_phone",
                                    "cust_reg_email",
                                    "cust_reg_instagram",
                                ):
                                    st.session_state.pop(k, None)
                                st.rerun()

            st.divider()
            st.markdown("#### All customers")
            all_cust = fetch_customers_ordered()
            if not all_cust:
                st.caption("No customers yet.")
            else:
                df_c = pd.DataFrame(
                    [
                        {
                            "Code": r["customer_code"],
                            "Name": r["name"],
                            "CPF": r["cpf"] or "—",
                            "Phone": r["phone"] or "—",
                            "City": r["city"] or "—",
                            "Updated": r["updated_at"] or "—",
                        }
                        for r in all_cust
                    ]
                )
                st.dataframe(df_c, width="stretch", hide_index=True)

        with tab_edit:
            st.markdown("#### Edit customer")
            rows_edit = fetch_customers_ordered()
            if not rows_edit:
                st.info("No customers yet — register one in the **Register** tab first.")
            else:
                labels = [f"{r['customer_code']} — {r['name']}" for r in rows_edit]
                sel = st.selectbox("Select customer", labels, key="cust_edit_sel")
                idx = labels.index(sel)
                row = rows_edit[idx]
                cid = int(row["id"])
                cc = row["customer_code"]
                st.caption(f"Customer code **{cc}** (read-only).")

                if st.session_state.get("cust_edit_pick_id") != cid:
                    st.session_state["cust_edit_pick_id"] = cid
                    _init_cust_edit_session(row, cid)

                cep_row_e = st.columns([3, 1])
                with cep_row_e[0]:
                    st.text_input(
                        "CEP (ZIP)",
                        key=f"cust_edit_cep_{cid}",
                    )
                with cep_row_e[1]:
                    st.write("")
                    if st.button(
                        "Buscar CEP",
                        key=f"cust_edit_cep_btn_{cid}",
                        type="secondary",
                    ):
                        with st.spinner("Buscando endereço..."):
                            data, err = fetch_viacep_address(
                                st.session_state.get(f"cust_edit_cep_{cid}", "")
                            )
                        if err:
                            st.error(err)
                        else:
                            st.session_state[f"cust_edit_street_{cid}"] = data["street"]
                            st.session_state[f"cust_edit_neighborhood_{cid}"] = data[
                                "neighborhood"
                            ]
                            st.session_state[f"cust_edit_city_{cid}"] = data["city"]
                            st.session_state[f"cust_edit_state_{cid}"] = data["state"]
                            st.success("Address loaded — you can edit below.")
                            st.rerun()

                with st.form(f"cust_edit_form_{cid}"):
                    e1, e2 = st.columns(2)
                    with e1:
                        st.text_input("Name *", key=f"cust_edit_name_{cid}")
                        st.text_input("CPF", key=f"cust_edit_cpf_{cid}")
                        st.text_input("RG", key=f"cust_edit_rg_{cid}")
                        st.text_input("Phone", key=f"cust_edit_phone_{cid}")
                    with e2:
                        st.text_input("Email", key=f"cust_edit_email_{cid}")
                        st.text_input(
                            "Instagram profile",
                            key=f"cust_edit_instagram_{cid}",
                        )

                    st.markdown("##### Address")
                    e_st1, e_st2 = st.columns([3, 1])
                    with e_st1:
                        st.text_input("Street", key=f"cust_edit_street_{cid}")
                    with e_st2:
                        st.text_input("Number", key=f"cust_edit_number_{cid}")
                    e_st3, e_st4 = st.columns(2)
                    with e_st3:
                        st.text_input(
                            "Neighborhood",
                            key=f"cust_edit_neighborhood_{cid}",
                        )
                    with e_st4:
                        st.text_input("City", key=f"cust_edit_city_{cid}")
                    e_st5, e_st6 = st.columns(2)
                    with e_st5:
                        st.text_input(
                            "State (UF)",
                            key=f"cust_edit_state_{cid}",
                            max_chars=2,
                        )
                    with e_st6:
                        st.text_input("Country", key=f"cust_edit_country_{cid}")

                    edit_submitted = st.form_submit_button("Save changes", type="primary")

                if edit_submitted:
                    name_val = (
                        st.session_state.get(f"cust_edit_name_{cid}") or ""
                    ).strip()
                    if not name_val:
                        st.error("Name is required.")
                    else:
                        cep_digits = sanitize_cep_digits(
                            st.session_state.get(f"cust_edit_cep_{cid}", "")
                        )
                        if cep_digits and len(cep_digits) != 8:
                            st.error(
                                "If CEP is filled, it must have exactly 8 digits (valid for lookup)."
                            )
                        else:
                            cpf_norm = normalize_cpf_digits(
                                st.session_state.get(f"cust_edit_cpf_{cid}", "")
                            )
                            if cpf_norm and not validate_cpf_br(cpf_norm):
                                st.error("CPF is invalid (check digits).")
                            elif not validate_email_optional(
                                st.session_state.get(f"cust_edit_email_{cid}", "")
                            ):
                                st.error("Email format is invalid.")
                            else:
                                phone_norm = normalize_phone_digits(
                                    st.session_state.get(f"cust_edit_phone_{cid}", "")
                                )
                                try:
                                    update_customer_row(
                                        customer_id=cid,
                                        name=name_val,
                                        cpf=cpf_norm if cpf_norm else None,
                                        rg=(
                                            st.session_state.get(f"cust_edit_rg_{cid}")
                                            or ""
                                        ).strip()
                                        or None,
                                        phone=phone_norm if phone_norm else None,
                                        email=(
                                            st.session_state.get(f"cust_edit_email_{cid}")
                                            or ""
                                        ).strip()
                                        or None,
                                        instagram=(
                                            st.session_state.get(
                                                f"cust_edit_instagram_{cid}"
                                            )
                                            or ""
                                        ).strip()
                                        or None,
                                        zip_code=cep_digits if cep_digits else None,
                                        street=(
                                            st.session_state.get(
                                                f"cust_edit_street_{cid}"
                                            )
                                            or ""
                                        ).strip()
                                        or None,
                                        number=(
                                            st.session_state.get(
                                                f"cust_edit_number_{cid}"
                                            )
                                            or ""
                                        ).strip()
                                        or None,
                                        neighborhood=(
                                            st.session_state.get(
                                                f"cust_edit_neighborhood_{cid}"
                                            )
                                            or ""
                                        ).strip()
                                        or None,
                                        city=(
                                            st.session_state.get(f"cust_edit_city_{cid}")
                                            or ""
                                        ).strip()
                                        or None,
                                        state=(
                                            st.session_state.get(
                                                f"cust_edit_state_{cid}"
                                            )
                                            or ""
                                        ).strip()
                                        or None,
                                        country=(
                                            st.session_state.get(
                                                f"cust_edit_country_{cid}"
                                            )
                                            or ""
                                        ).strip()
                                        or None,
                                    )
                                except ValueError as e:
                                    st.error(str(e))
                                else:
                                    st.success("Customer updated.")
                                    st.session_state.pop("cust_edit_pick_id", None)
                                    st.rerun()

    elif page == "Stock":
        st.markdown(
            """
            <style>
            /* Stock typography: two ×30% steps vs 12–13px base (0.7² = 0.49). Main app title unchanged. */
            section.main h1 {
                font-size: 2.75rem !important;
                line-height: 1.2 !important;
            }

            section.main .block-container {
                font-size: calc(13px * 0.49) !important;
                line-height: 1.3 !important;
                max-width: 100% !important;
                padding-top: 0.35rem !important;
                padding-left: 0.4rem !important;
                padding-right: 0.4rem !important;
                box-sizing: border-box !important;
            }

            section.main h3 {
                font-size: calc(1.02rem * 0.49) !important;
                font-weight: 600 !important;
                line-height: 1.3 !important;
                margin: 0.15rem 0 0.28rem 0 !important;
            }

            /* Tighter vertical stack (less space between table rows) */
            section.main .block-container > div[data-testid="stVerticalBlock"] {
                gap: 0.08rem !important;
            }
            section.main div[data-testid="stVerticalBlock"] > div[data-testid="element-container"] {
                margin-top: 0 !important;
                margin-bottom: 0.04rem !important;
            }

            /* Grid rows: minimal horizontal gap, full width */
            section.main div[data-testid="stHorizontalBlock"] {
                gap: 0.05rem !important;
                align-items: stretch !important;
                width: 100% !important;
                min-width: 0 !important;
            }

            section.main div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
                padding-left: 0.06rem !important;
                padding-right: 0.06rem !important;
                min-width: 0 !important;
            }

            /* Table headers — 12px × 0.49 */
            section.main div[data-testid="stHorizontalBlock"] div[data-testid="column"] p {
                font-size: calc(12px * 0.49) !important;
                line-height: 1.3 !important;
                margin: 0 0 0.06rem 0 !important;
                padding: 0 !important;
            }
            section.main div[data-testid="stHorizontalBlock"] div[data-testid="column"] strong {
                font-size: calc(12px * 0.49) !important;
                font-weight: 500 !important;
                line-height: 1.3 !important;
            }

            /* Table cells */
            section.main div[data-testid="stHorizontalBlock"] div[data-testid="column"] div[data-testid="element-container"] {
                font-size: calc(12px * 0.49) !important;
                line-height: 1.3 !important;
                padding-top: 0.05rem !important;
                padding-bottom: 0.05rem !important;
            }
            section.main div[data-testid="stHorizontalBlock"] div[data-testid="column"] div[data-testid="stMarkdownContainer"] p {
                font-size: calc(12px * 0.49) !important;
                line-height: 1.3 !important;
                margin: 0 !important;
                font-weight: 400 !important;
            }

            /* Multiselects — font ×0.49 vs base; controls scaled; cover placeholder (“Choose options”) */
            section.main [data-testid="stMultiSelect"] {
                margin-top: 0 !important;
                margin-bottom: 0 !important;
            }
            section.main [data-testid="stMultiSelect"] [data-baseweb="select"],
            section.main [data-testid="stMultiSelect"] [data-baseweb="select"] [data-baseweb="select"],
            section.main [data-testid="stMultiSelect"] [role="combobox"],
            section.main [data-testid="stMultiSelect"] [role="combobox"] span,
            section.main [data-testid="stMultiSelect"] [role="combobox"] div {
                font-size: calc(12px * 0.49) !important;
            }
            section.main [data-testid="stMultiSelect"] [data-baseweb="select"] {
                min-height: calc(29px * 0.49) !important;
                height: calc(29px * 0.49) !important;
            }
            section.main [data-testid="stMultiSelect"] [data-baseweb="select"] span {
                font-size: calc(12px * 0.49) !important;
                line-height: 1.3 !important;
            }
            section.main [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
                min-height: calc(29px * 0.49) !important;
                height: calc(29px * 0.49) !important;
                max-height: calc(30px * 0.49) !important;
            }
            section.main [data-testid="stMultiSelect"] [data-baseweb="select"] [data-baseweb="select"] > div {
                min-height: calc(27px * 0.49) !important;
                height: calc(27px * 0.49) !important;
                padding-top: calc(5px * 0.49) !important;
                padding-bottom: calc(5px * 0.49) !important;
                padding-left: calc(6px * 0.49) !important;
                padding-right: calc(6px * 0.49) !important;
                box-sizing: border-box !important;
            }

            section.main ul[data-baseweb="menu"] li,
            section.main [role="listbox"] li {
                font-size: calc(12px * 0.49) !important;
                line-height: 1.3 !important;
                min-height: calc(26px * 0.49) !important;
                padding-top: calc(4px * 0.49) !important;
                padding-bottom: calc(4px * 0.49) !important;
            }

            /* Exclude — label ×0.49; no wrap; box aligned to row */
            section.main div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child button {
                background-color: #dc2626 !important;
                color: #ffffff !important;
                border: 1px solid #b91c1c !important;
                margin: 0 !important;
                padding: calc(4px * 0.49) calc(8px * 0.49) !important;
                min-height: calc(29px * 0.49) !important;
                height: calc(29px * 0.49) !important;
                max-height: calc(29px * 0.49) !important;
                align-self: center !important;
                box-sizing: border-box !important;
                white-space: nowrap !important;
            }
            section.main div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child button:hover {
                background-color: #b91c1c !important;
                color: #ffffff !important;
            }
            section.main div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child button p {
                color: #ffffff !important;
                font-size: calc(12px * 0.49) !important;
                line-height: 1.3 !important;
                margin: 0 !important;
            }

            section.main hr {
                margin: 0.35rem 0 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("### Stock")

        products = fetch_products()
        in_stock_products = [p for p in products if float(p["stock"] or 0) > 0]

        if not in_stock_products:
            st.info("No stock available. Add products with pieces first.")
            return

        # Confirmation dialog state for excluding an entering batch.
        if "pending_exclude_code" not in st.session_state:
            st.session_state.pending_exclude_code = None
        if "pending_exclude_label" not in st.session_state:
            st.session_state.pending_exclude_label = None

        @st.dialog("Confirm exclude from stock")
        def confirm_exclude_dialog():
            code = st.session_state.pending_exclude_code
            label = st.session_state.pending_exclude_label
            if not code:
                st.write("Nothing to exclude.")
                return

            st.warning(
                "This will exclude the entire entering batch from stock (set stock=0, cost=0, price=0).\n\n"
                f"{label}"
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "Confirm exclude",
                    type="primary",
                    key="confirm_exclude_stock_btn",
                ):
                    reset_batch_pricing_and_exclude(code)
                    st.session_state.pending_exclude_code = None
                    st.session_state.pending_exclude_label = None
                    st.rerun()
            with c2:
                if st.button("Cancel", key="cancel_exclude_stock_btn"):
                    st.session_state.pending_exclude_code = None
                    st.session_state.pending_exclude_label = None
                    st.rerun()

        if st.session_state.get("pending_exclude_code"):
            confirm_exclude_dialog()

        # Build items (one row per batch/register entry).
        items = []
        for r in in_stock_products:
            product_id = int(r["id"])
            code = r["product_enter_code"] or ""
            sku = r["sku"] or ""
            reg_date = r["registered_date"] or ""
            name = str(r["name"])
            color = r["color"] or ""
            style = r["style"] or ""
            palette = r["palette"] or ""
            gender = r["gender"] or ""
            cost = round(float(r["cost"] or 0), 2)
            price = round(float(r["price"] or 0), 2)
            stock_qty = int(r["stock"] or 0)
            markup_amount = round(price - cost, 2)

            items.append(
                {
                    "product_id": product_id,
                    "code": code,
                    "name": name,
                    "sku": sku,
                    "registered_date": reg_date,
                    "color": color,
                    "style": style,
                    "palette": palette,
                    "gender": gender,
                    "cost": cost,
                    "price": price,
                    "markup": markup_amount,
                    "stock_qty": stock_qty,
                }
            )

        # Column layout: tight weights; Streamlit columns share full width proportionally.
        stock_col_w = [
            0.88,
            1.52,
            0.92,
            0.92,
            0.92,
            1.0,
            0.88,
            0.9,
            0.9,
            0.9,
            0.86,
        ]

        # Build header filters (Excel-like column dropdowns).
        header = st.columns(stock_col_w)
        header[0].markdown("**Action**")

        header[1].markdown("**Product name**")
        name_options = sorted({it["name"] for it in items if it["name"] is not None})
        selected_names = header[1].multiselect(
            label="",
            options=name_options,
            default=[],
            key="stock_filter_name",
        )

        header[2].markdown("**SKU**")
        sku_options = sorted({it["sku"] for it in items if it["sku"] is not None})
        selected_skus = header[2].multiselect(
            label="",
            options=sku_options,
            default=[],
            key="stock_filter_sku",
        )

        header[3].markdown("**Color**")
        color_options = sorted({it["color"] for it in items if it["color"] is not None})
        selected_colors = header[3].multiselect(
            label="",
            options=color_options,
            default=[],
            key="stock_filter_color",
        )

        header[4].markdown("**Style**")
        style_options = sorted({it["style"] for it in items if it["style"] is not None})
        selected_styles = header[4].multiselect(
            label="",
            options=style_options,
            default=[],
            key="stock_filter_style",
        )

        header[5].markdown("**Palette**")
        palette_options = sorted({it["palette"] for it in items if it["palette"] is not None})
        selected_palettes = header[5].multiselect(
            label="",
            options=palette_options,
            default=[],
            key="stock_filter_palette",
        )

        header[6].markdown("**Gender**")
        gender_options = sorted({it["gender"] for it in items if it["gender"] is not None})
        selected_genders = header[6].multiselect(
            label="",
            options=gender_options,
            default=[],
            key="stock_filter_gender",
        )

        header[7].markdown("**Cost**")
        cost_options = sorted({it["cost"] for it in items})
        selected_costs = header[7].multiselect(
            label="",
            options=cost_options,
            default=[],
            key="stock_filter_cost",
        )

        header[8].markdown("**Sale price**")
        price_options = sorted({it["price"] for it in items})
        selected_prices = header[8].multiselect(
            label="",
            options=price_options,
            default=[],
            key="stock_filter_price",
        )

        header[9].markdown("**Margin**")
        markup_options = sorted({it["markup"] for it in items})
        selected_markups = header[9].multiselect(
            label="",
            options=markup_options,
            default=[],
            key="stock_filter_markup",
        )

        header[10].markdown("**In stock**")
        stock_options = sorted({it["stock_qty"] for it in items})
        selected_stocks = header[10].multiselect(
            label="",
            options=stock_options,
            default=[],
            key="stock_filter_stock",
        )

        # Apply filters.
        filtered = []
        for it in items:
            if selected_names and it["name"] not in selected_names:
                continue
            if selected_skus and it["sku"] not in selected_skus:
                continue
            if selected_colors and it["color"] not in selected_colors:
                continue
            if selected_styles and it["style"] not in selected_styles:
                continue
            if selected_palettes and it["palette"] not in selected_palettes:
                continue
            if selected_genders and it["gender"] not in selected_genders:
                continue
            if selected_costs and it["cost"] not in selected_costs:
                continue
            if selected_prices and it["price"] not in selected_prices:
                continue
            if selected_markups and it["markup"] not in selected_markups:
                continue
            if selected_stocks and it["stock_qty"] not in selected_stocks:
                continue
            filtered.append(it)

        # Default order.
        filtered.sort(
            key=lambda x: ((x.get("name") or "").lower(), x.get("registered_date") or "")
        )

        # Totals (for filtered rows).
        totals_cost = 0.0
        totals_price = 0.0
        totals_markup = 0.0
        totals_stock = 0

        if not filtered:
            st.info("No rows match the current filters.")
            return

        for it in filtered:
            product_id = int(it["product_id"])
            code = it["code"]
            sku = it["sku"]
            name = it["name"]
            cost = float(it["cost"])
            price = float(it["price"])
            markup_amount = float(it["markup"])
            stock_qty = int(it["stock_qty"])

            row = st.columns(stock_col_w)
            with row[0]:
                if code and st.button(
                    "Exclude",
                    type="secondary",
                    key=f"stock_exclude_{product_id}",
                ):
                    st.session_state.pending_exclude_code = code
                    attr_bits = " · ".join(
                        x
                        for x in (
                            it["color"],
                            it["style"],
                            it["palette"],
                            it["gender"],
                        )
                        if x
                    )
                    extra = f" | {attr_bits}" if attr_bits else ""
                    st.session_state.pending_exclude_label = (
                        f"{name}{extra} | SKU: {sku} | Code: {code}"
                    )
                    st.rerun()

            row[1].markdown(f"**{name}**")
            row[2].write(sku or "—")
            row[3].write(it["color"] or "—")
            row[4].write(it["style"] or "—")
            row[5].write(it["palette"] or "—")
            row[6].write(it["gender"] or "—")
            row[7].write(format_money(cost))
            row[8].write(format_money(price))
            row[9].write(format_money(markup_amount))
            row[10].write(stock_qty)

            totals_cost += cost * stock_qty
            totals_price += price * stock_qty
            totals_markup += markup_amount * stock_qty
            totals_stock += stock_qty

        st.divider()
        total_row = st.columns(stock_col_w)
        with total_row[0]:
            st.write("")
        total_row[1].markdown("**TOTAL**")
        for _i in range(2, 7):
            total_row[_i].write("")
        total_row[7].write(format_money(totals_cost))
        total_row[8].write(format_money(totals_price))
        total_row[9].write(format_money(totals_markup))
        total_row[10].write(totals_stock)


if __name__ == "__main__":
    main()

