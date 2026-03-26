import json
import logging
import math
import re
import sqlite3
import urllib.error
import urllib.parse
from urllib import request
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd
import streamlit as st

from database.connection import DB_PATH, get_conn
from database.constants import SKU_COST_COMPONENT_DEFINITIONS
from database.cost_components_repo import (
    ensure_sku_cost_component_rows,
    recompute_sku_structured_cost_total,
)
from database.customer_sync import format_customer_code
from database.init_db import init_db
from database.product_codes import make_product_enter_code
from database.sale_codes import _next_sale_sequence, format_sale_code
from database.sku_codec import (
    _next_sku_sequence,
    build_product_sku_body,
    format_sku_sequence_int,
)
from database.sku_master_repo import ensure_sku_master, sync_sku_master_totals

_logger = logging.getLogger(__name__)

# Navegação (rótulos em português — também usados nos `if page == …`)
PAGE_PRODUTOS = "Produtos"
PAGE_ESTOQUE = "Estoque"
PAGE_CUSTOS = "Custos"
PAGE_PRECIFICACAO = "Precificação"
PAGE_VENDAS = "Vendas"
PAGE_CLIENTES = "Clientes"
PAGE_PAINEL = "Painel"

FILTER_ANY = "Qualquer"

CURRENCY_SYMBOL = "R$"

# Product registration — dropdown options (pt-BR; valores gravados no banco / SKU)
PRODUCT_GENDER_OPTIONS = ["Masculino", "Feminino", "Unissex"]

PRODUCT_PALETTE_OPTIONS = [
    "Primavera",
    "Verão",
    "Outono",
    "Inverno",
]

# Armação / estilo do produto (cadastro)
PRODUCT_STYLE_OPTIONS = [
    "Aviador",
    "Wayfarer",
    "Redondo",
    "Retangular",
    "Gatinho",
    "Hexagonal",
    "Clubmaster",
    "Oval",
    "Esportivo",
]

# Cor da armação (cadastro)
PRODUCT_FRAME_COLOR_OPTIONS = [
    "Preto",
    "Preto / Fosco",
    "Preto / Brilhante",
    "Branco",
    "Branco / Pérola",
    "Marfim",
    "Creme",
    "Cinza",
    "Cinza / Claro",
    "Cinza / Carvão",
    "Prata",
    "Prata / Metálico",
    "Dourado",
    "Dourado / Rose",
    "Ouro rose",
    "Cobre",
    "Bronze",
    "Champagne",
    "Azul-marinho",
    "Azul-marinho / Meia-noite",
    "Azul royal",
    "Azul céu",
    "Azul / Cobalto",
    "Azul aço",
    "Verde-azulado",
    "Turquesa",
    "Água-marinha",
    "Verde",
    "Verde floresta",
    "Verde oliva",
    "Esmeralda",
    "Menta",
    "Sálvia",
    "Vermelho",
    "Bordô",
    "Vinho",
    "Carmim",
    "Coral",
    "Rosa",
    "Rosa blush",
    "Rosa antigo",
    "Magenta",
    "Roxo",
    "Lavanda",
    "Ameixa",
    "Violeta",
    "Marrom",
    "Bege / Cáqui claro",
    "Camel",
    "Cáqui",
    "Taupe",
    "Café",
    "Chocolate",
    "Amarelo",
    "Mostarda",
    "Laranja",
    "Pêssego",
    "Damasco",
    "Tartaruga",
    "Tartaruga / Havana",
    "Havana",
    "Mel",
    "Cristal",
    "Transparente",
    "Transparente / Fumê",
    "Gradiente / Cinza",
    "Gradiente / Marrom",
    "Espelhado / Prata",
    "Espelhado / Azul",
    "Espelhado / Dourado",
    "Fosco",
    "Opaco",
]

# Cor da lente (óculos de sol)
PRODUCT_LENS_COLOR_OPTIONS = [
    "Preto",
    "Cinza",
    "Marrom",
    "Verde",
    "Azul",
    "Degradê preto",
    "Degradê marrom",
    "Espelhado prata",
    "Espelhado azul",
    "Espelhado dourado",
    "Espelhado verde",
    "Amarelo",
    "Transparente",
    "Espelhado Rosa",
]

# UX: placeholder do select; última opção é valor literal salvo no SKU quando usuário escolhe "Outro"
SELECT_LABEL = "Selecione"
OTHER_LABEL = "Outro"


def dropdown_with_other(base_options):
    """[…opções…, 'Outro'] — 'Outro' é opção normal (valor literal salvo); placeholder no select."""
    return list(base_options) + [OTHER_LABEL]


def attribute_select_index(options, current_value) -> Optional[int]:
    """Índice do selectbox a partir do valor do BD, ou None = mostrar placeholder. Valores fora da lista → Outro."""
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
    Selectbox com placeholder acinzentado «Selecione» quando nada foi escolhido (Streamlit 1.29+).
    Retorna None até o usuário escolher uma opção válida.
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

    Se "Outro" for selecionado, grava o rótulo literal (sem campo de texto extra).
    """
    if choice is None:
        return None, f"Selecione {field_label}."
    if choice == OTHER_LABEL:
        t = (other_text or "").strip()
        if t:
            return t, None
        return OTHER_LABEL, None
    return choice, None


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
        raise RuntimeError("Contador de sequência de cliente não inicializado.")
    return int(row["last_value"])


def sanitize_cep_digits(cep: str) -> str:
    return re.sub(r"\D", "", cep or "")


def fetch_viacep_address(cep: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    ViaCEP lookup. Returns (payload, error_message).
    payload keys: street, neighborhood, city, state.
    """
    digits = sanitize_cep_digits(cep)
    if len(digits) != 8:
        return None, "O CEP deve ter exatamente 8 dígitos."
    url = f"https://viacep.com.br/ws/{digits}/json/"
    try:
        req = request.Request(
            url,
            headers={"User-Agent": "ALIEH-management/1.0"},
        )
        with request.urlopen(req, timeout=12) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        if data.get("erro"):
            return None, "CEP não encontrado (ViaCEP)."
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
        return None, f"Falha na consulta do CEP (HTTP {e.code})."
    except urllib.error.URLError as e:
        return None, f"Falha na consulta do CEP: {e.reason}"
    except Exception as e:
        return None, f"Falha na consulta do CEP: {e}"


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


def _sqlite_safe_rollback(conn: sqlite3.Connection) -> None:
    """Use API rollback; avoid OperationalError from raw ROLLBACK when no txn is active."""
    try:
        conn.rollback()
    except sqlite3.OperationalError:
        pass


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
                _sqlite_safe_rollback(conn)
                label = "CPF" if kind == "cpf" else "Telefone"
                raise ValueError(
                    f"{label} duplicado: "
                    f"já usado pelo cliente {row['customer_code']} — {row['name']}."
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
            _sqlite_safe_rollback(conn)
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
                _sqlite_safe_rollback(conn)
                label = "CPF" if kind == "cpf" else "Telefone"
                raise ValueError(
                    f"{label} duplicado: "
                    f"já usado pelo cliente {row['customer_code']} — {row['name']}."
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
            _sqlite_safe_rollback(conn)
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


def init_cust_edit_session(r: sqlite3.Row, cid: int) -> None:
    """Load customer row into Streamlit session keys for the edit form."""
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


def peek_next_customer_code_preview() -> str:
    """Read-only preview of the next code (does not consume sequence)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT last_value FROM customer_sequence_counter WHERE id = 1;"
        ).fetchone()
        n = int(row["last_value"] or 0) + 1 if row else 1
        return format_customer_code(n)


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


def fetch_product_batches_in_stock_for_sku(sku: str) -> list:
    """Lotes do SKU com estoque > 0 (fluxo de vendas)."""
    sku = (sku or "").strip()
    if not sku:
        return []
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT p.id, p.name, p.stock, p.product_enter_code,
                   p.frame_color, p.lens_color, p.style, p.palette, p.gender
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
        raise ValueError("A quantidade deve ser maior que zero.")
    if unit_cost <= 0:
        raise ValueError("O custo unitário deve ser maior que zero.")
    sku = sku.strip()

    prow = conn.execute(
        "SELECT id, sku, deleted_at FROM products WHERE id = ?;",
        (int(product_id),),
    ).fetchone()
    if prow is None:
        raise ValueError("Lote de produto não encontrado.")
    if (prow["sku"] or "").strip() != sku:
        raise ValueError("O SKU do produto não corresponde ao lote selecionado.")
    if prow["deleted_at"]:
        raise ValueError(
            "Não é possível adicionar estoque a um lote inativo (excluído logicamente)."
        )

    sm_del = conn.execute(
        "SELECT deleted_at FROM sku_master WHERE sku = ?;",
        (sku,),
    ).fetchone()
    if sm_del and sm_del["deleted_at"]:
        raise ValueError(
            "Não é possível adicionar estoque a um SKU inativo (excluído logicamente)."
        )

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
        raise ValueError("SKU é obrigatório.")
    if new_price <= 0:
        raise ValueError("O preço de venda deve ser maior que zero.")
    sku = sku.strip()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT selling_price FROM sku_master WHERE sku = ?;",
            (sku,),
        ).fetchone()
        if row is None:
            raise ValueError(
                "SKU não encontrado no estoque. "
                "Cadastre um produto ou registre uma entrada de estoque primeiro."
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
        raise ValueError("Markup, impostos e juros devem ser zero ou maiores.")

    with get_conn() as conn:
        conn.isolation_level = None
        try:
            conn.execute("BEGIN;")
            row = conn.execute(
                "SELECT selling_price, avg_unit_cost FROM sku_master WHERE sku = ?;",
                (sku,),
            ).fetchone()
            if row is None:
                raise ValueError("SKU não cadastrado no mestre de estoque.")
            avg_cost = float(row["avg_unit_cost"] or 0.0)
            if avg_cost <= 0:
                raise ValueError(
                    "O custo médio de estoque (CMP) não está disponível para este SKU. "
                    "Registre entradas de estoque na página Custos para definir o CMP antes de precificar."
                )
            old_sell = float(row["selling_price"] or 0.0)
            pb, pwt, target = compute_sku_pricing_targets(
                avg_cost, markup_pct, taxes_pct, interest_pct
            )
            if target <= 0:
                raise ValueError("O preço-alvo calculado deve ser maior que zero.")
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
            raise ValueError("SKU não cadastrado no mestre de estoque.")
        if row["deleted_at"]:
            raise ValueError("SKU inativo (excluído logicamente).")
        return float(row["t"] or 0.0)


def fetch_product_batches_for_sku(sku: str) -> list:
    """Product rows (batches) for a given SKU — stock receipts apply to one batch."""
    sku = sku.strip()
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, name, sku, registered_date, product_enter_code, cost, price, pricing_locked, stock,
                   frame_color, lens_color, style, palette, gender
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
    for k in (
        "prod_reg_frame_color",
        "prod_reg_lens_color",
        "prod_reg_palette",
        "prod_reg_gender",
        "prod_reg_style",
    ):
        if st.session_state.get(k) is None:
            return None
    fc, efc = resolve_attribute_value(
        st.session_state["prod_reg_frame_color"], "", "a cor da armação"
    )
    lc, elc = resolve_attribute_value(
        st.session_state["prod_reg_lens_color"], "", "a cor da lente"
    )
    p, ep = resolve_attribute_value(st.session_state["prod_reg_palette"], "", "a paleta")
    g, eg = resolve_attribute_value(st.session_state["prod_reg_gender"], "", "o gênero")
    s, es = resolve_attribute_value(st.session_state["prod_reg_style"], "", "o estilo")
    if efc or elc or ep or eg or es:
        return None
    body = build_product_sku_body(
        product_name=name,
        frame_color=fc,
        lens_color=lc,
        gender=g,
        palette=p,
        style=s,
    )
    return f"XXX-{body}"


def update_product_attributes(
    product_id: int,
    frame_color: str,
    lens_color: str,
    style: str,
    palette: str,
    gender: str,
) -> None:
    """
    Update attributes and recalculate SKU from product name + attributes.
    Raises ValueError if another product already uses the new SKU.
    """
    frame_color = (frame_color or "").strip()
    lens_color = (lens_color or "").strip()
    style = (style or "").strip()
    palette = (palette or "").strip()
    gender = (gender or "").strip()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name, sku FROM products WHERE id = ?;",
            (int(product_id),),
        ).fetchone()
        if row is None:
            raise ValueError("Produto não encontrado.")
        name = str(row["name"] or "").strip()
        old_sku = str(row["sku"] or "").strip()
        oparts = old_sku.split("-")
        if oparts and oparts[0].isdigit():
            new_sku = f"{oparts[0]}-{build_product_sku_body(name, frame_color, lens_color, gender, palette, style)}"
        else:
            new_sku = generate_product_sku(
                name, frame_color, lens_color, gender, palette, style
            )
        dup = conn.execute(
            """
            SELECT id FROM products
            WHERE sku = ? AND id != ?;
            """,
            (new_sku, int(product_id)),
        ).fetchone()
        if dup is not None:
            raise ValueError(
                f"Seria criado um SKU duplicado `{new_sku}`. "
                "Ajuste o nome do produto ou os atributos para obter um SKU único."
            )
        conn.execute(
            """
            UPDATE products
            SET frame_color = ?, lens_color = ?, style = ?, palette = ?, gender = ?, sku = ?
            WHERE id = ?;
            """,
            (frame_color, lens_color, style, palette, gender, new_sku, int(product_id)),
        )


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
            return 0.0, "Use apenas dígitos e um ponto decimal."
    if s.count(".") > 1:
        return 0.0, "Permitido apenas um ponto decimal."
    if s == ".":
        return 0.0, None
    parts = s.split(".")
    if len(parts) == 2 and len(parts[1]) > 4:
        return 0.0, "No máximo 4 casas decimais na quantidade."
    try:
        v = float(s)
    except ValueError:
        return 0.0, "Número inválido."
    if v < 0:
        return 0.0, "A quantidade não pode ser negativa."
    return round(v, 4), None


def parse_cost_unit_price_value(value: float) -> tuple[float, Optional[str]]:
    """Unit price: non-negative, rounded to 2 decimals."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0, "Preço unitário inválido."
    if v < 0:
        return 0.0, "Preço unitário não pode ser negativo."
    return round(v, 2), None


def generate_product_sku(
    product_name: str,
    frame_color: str,
    lens_color: str,
    gender: str,
    palette: str,
    style: str,
) -> str:
    """
    SKU completo: [SEQ]-[PP]-[FC]-[LC]-[GG]-[PA]-[ST]. SEQ = contador persistente (001+).
    """
    with get_conn() as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE;")
        try:
            n = _next_sku_sequence(conn)
            body = build_product_sku_body(
                product_name, frame_color, lens_color, gender, palette, style
            )
            conn.execute("COMMIT;")
            return f"{format_sku_sequence_int(n)}-{body}"
        except Exception:
            conn.execute("ROLLBACK;")
            raise


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
                raise ValueError("SKU não cadastrado no mestre de estoque.")
            ensure_sku_cost_component_rows(conn, sku)
            now = datetime.now().isoformat(timespec="seconds")
            for key, unit_price, quantity in component_inputs:
                unit_price = round(float(unit_price), 2)
                quantity = round(float(quantity), 4)
                if unit_price < 0 or quantity < 0:
                    raise ValueError("Preço unitário e quantidade não podem ser negativos.")
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


def fetch_products():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, sku, registered_date, product_enter_code, cost, price, pricing_locked, stock,
                   frame_color, lens_color, style, palette, gender
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
    """Valores distintos para filtros da busca por SKU."""
    out: dict = {
        "frame_color": [],
        "lens_color": [],
        "gender": [],
        "palette": [],
        "style": [],
    }
    with get_conn() as conn:
        for key, col in [
            ("frame_color", "frame_color"),
            ("lens_color", "lens_color"),
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
    frame_color_filter: str,
    lens_color_filter: str,
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
        (frame_color_filter, "p.frame_color"),
        (lens_color_filter, "p.lens_color"),
        (gender_filter, "p.gender"),
        (palette_filter, "p.palette"),
        (style_filter, "p.style"),
    ]:
        if val and str(val).strip() and str(val) != FILTER_ANY:
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
        SELECT p.id, p.sku, p.name, p.frame_color, p.lens_color, p.gender, p.palette, p.style,
               p.stock, p.created_at,
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


def fetch_product_by_id(product_id: int):
    """Single product row joined with sku_master for display."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT p.id, p.sku, p.name, p.frame_color, p.lens_color, p.gender, p.palette, p.style,
                   p.stock, p.registered_date, p.product_enter_code, p.created_at,
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
    frame_color: str,
    lens_color: str,
    style: str,
    palette: str,
    gender: str,
    unit_cost: float,
) -> str:
    """
    Registra um lote. SKU: [SEQ]-[PP]-[FC]-[LC]-[GG]-[PA]-[ST].

    Product registration typically uses stock=0; add stock via the Costing page (stock receipts).
    If stock > 0 here, unit_cost must be > 0 (weighted-average receipt).

    Returns the product enter code (slug + date). Raises ValueError or sqlite errors if not mergeable / DB fails.
    """
    product_enter_code = make_product_enter_code(product_name=name, registered_date=registered_date)
    name = name.strip()
    frame_color = (frame_color or "").strip()
    lens_color = (lens_color or "").strip()
    style = (style or "").strip()
    palette = (palette or "").strip()
    gender = (gender or "").strip()

    if float(stock) > 0 and float(unit_cost) <= 0:
        raise ValueError(
            "Com estoque maior que zero, o custo unitário é obrigatório e deve ser maior que zero."
        )
    if float(stock) < 0:
        raise ValueError("O estoque não pode ser negativo.")

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
                  AND COALESCE(frame_color, '') = ?
                  AND COALESCE(lens_color, '') = ?
                  AND COALESCE(style, '') = ?
                  AND COALESCE(palette, '') = ?
                  AND COALESCE(gender, '') = ?;
                """,
                (
                    name,
                    registered_date_text,
                    frame_color,
                    lens_color,
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
                body = build_product_sku_body(
                    name, frame_color, lens_color, gender, palette, style
                )
                sku = f"{format_sku_sequence_int(n)}-{body}"
                clash = conn.execute(
                    "SELECT id FROM products WHERE sku = ?;",
                    (sku,),
                ).fetchone()
                if clash is not None:
                    raise ValueError(
                        f"O SKU `{sku}` já existe (duplicado). "
                        "Use outro nome de produto ou ajuste os atributos para o SKU ser único."
                    )
                created_now = datetime.now().isoformat(timespec="seconds")
                ins_cur = conn.execute(
                    """
                    INSERT INTO products (
                        name, sku, registered_date, product_enter_code, cost, price, stock,
                        frame_color, lens_color, style, palette, gender, created_at
                    )
                    VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        name,
                        sku,
                        registered_date_text,
                        product_enter_code,
                        frame_color,
                        lens_color,
                        style,
                        palette,
                        gender,
                        created_now,
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
            _sqlite_safe_rollback(conn)
            raise
    return product_enter_code


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
        raise ValueError("A quantidade deve ser maior que zero.")
    disc = float(discount_amount)
    if disc < 0:
        raise ValueError("O desconto não pode ser negativo.")

    with get_conn() as conn:
        conn.isolation_level = None
        try:
            conn.execute("BEGIN IMMEDIATE;")
            cust = conn.execute(
                "SELECT id FROM customers WHERE id = ?;",
                (int(customer_id),),
            ).fetchone()
            if cust is None:
                raise ValueError("Cliente não encontrado.")

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
                raise ValueError("Produto não encontrado.")
            if row["p_del"] or row["sm_del"]:
                raise ValueError(
                    "Este produto/SKU está inativo (excluído logicamente) e não pode ser vendido."
                )

            sku = (row["sku"] or "").strip()
            if not sku:
                raise ValueError("O produto não tem SKU; não é possível registrar a venda.")

            selling_price = float(row["sp"])
            if selling_price <= 0:
                raise ValueError(
                    "Defina um preço de venda para este SKU em Precificação antes de vender."
                )

            stock = float(row["stock"] or 0)
            gross_total = selling_price * float(qty)

            if float(qty) > stock + 1e-9:
                raise ValueError(f"Estoque insuficiente. Disponível: {stock}")

            if disc > gross_total + 1e-9:
                raise ValueError(
                    "O desconto não pode exceder o valor base (preço unitário × quantidade)."
                )

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
    st.set_page_config(page_title="ALIEH — Gestão", layout="wide")
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

    st.title("ALIEH — Gestão comercial")
    st.caption(
        "Produtos, estoque, custos, precificação, vendas e painel (banco SQLite local)."
    )

    page = st.sidebar.radio(
        "Navegação",
        [
            PAGE_PRODUTOS,
            PAGE_ESTOQUE,
            PAGE_CUSTOS,
            PAGE_PRECIFICACAO,
            PAGE_VENDAS,
            PAGE_CLIENTES,
            PAGE_PAINEL,
        ],
        index=0,
    )

    if page == PAGE_PRODUTOS:
        st.markdown("### Produtos")
        st.caption(
            "Use **Busca por SKU** para localizar lotes ou cadastre novos abaixo."
        )

        attr_opts = fetch_product_search_attribute_options()
        with st.expander("Busca por SKU e lote", expanded=False):
            st.caption(
                "Busca parcial em **SKU** ou **nome do produto**. Combine os filtros; a tabela atualiza a cada alteração."
            )
            tq = st.text_input(
                "Buscar SKU ou nome",
                key="sku_search_text_q",
                placeholder="ex.: 001, SUN, parte do nome…",
            )
            r1a, r1b = st.columns(2)
            with r1a:
                sort_by = st.selectbox(
                    "Ordenar por",
                    ["sku", "name", "stock_desc", "stock_asc"],
                    index=0,
                    format_func=lambda k: {
                        "sku": "SKU (A–Z)",
                        "name": "Nome (A–Z)",
                        "stock_desc": "Estoque (maior → menor)",
                        "stock_asc": "Estoque (menor → maior)",
                    }[k],
                    key="sku_search_sort",
                )
            with r1b:
                page_size = st.selectbox(
                    "Linhas por página", [25, 50, 100, 200], index=2, key="sku_search_ps"
                )

            fc1, fc2, fc3, fc4, fc5 = st.columns(5)
            with fc1:
                cf = st.selectbox(
                    "Cor da armação",
                    [FILTER_ANY] + attr_opts["frame_color"],
                    key="sku_search_frame_color",
                )
            with fc2:
                lf = st.selectbox(
                    "Cor da lente",
                    [FILTER_ANY] + attr_opts["lens_color"],
                    key="sku_search_lens_color",
                )
            with fc3:
                gf = st.selectbox(
                    "Gênero",
                    [FILTER_ANY] + attr_opts["gender"],
                    key="sku_search_gender",
                )
            with fc4:
                pf = st.selectbox(
                    "Paleta",
                    [FILTER_ANY] + attr_opts["palette"],
                    key="sku_search_palette",
                )
            with fc5:
                sf = st.selectbox(
                    "Estilo",
                    [FILTER_ANY] + attr_opts["style"],
                    key="sku_search_style",
                )

            _, total_match = search_products_filtered(
                tq, cf, lf, gf, pf, sf, sort_by, 1, 0
            )
            total_pages = max(1, (total_match + page_size - 1) // page_size)
            if st.session_state.get("sku_search_page", 1) > total_pages:
                st.session_state["sku_search_page"] = total_pages
            pg1, pg2, pg3 = st.columns([1, 1, 2])
            with pg1:
                page_num = st.number_input(
                    "Página",
                    min_value=1,
                    max_value=total_pages,
                    value=1,
                    step=1,
                    key="sku_search_page",
                )
            with pg2:
                st.metric("Resultados", total_match)
            with pg3:
                st.caption(
                    f"Página **{page_num}** / **{total_pages}** · **{total_match}** linha(s) com os filtros."
                )

            rows, _ = search_products_filtered(
                tq, cf, lf, gf, pf, sf, sort_by, page_size, (page_num - 1) * page_size
            )

            if not rows:
                st.info("Nenhum produto com esses filtros.")
            else:
                df = pd.DataFrame(
                    [
                        {
                            "ID": r["id"],
                            "SKU": r["sku"] or "—",
                            "Nome": r["name"] or "—",
                            "Cor armação": r["frame_color"] or "—",
                            "Cor lente": r["lens_color"] or "—",
                            "Gênero": r["gender"] or "—",
                            "Paleta": r["palette"] or "—",
                            "Estilo": r["style"] or "—",
                            "Criado em": format_product_created_display(
                                r["created_at"]
                            ),
                            "Estoque": float(r["stock"] or 0),
                            "Custo médio": float(r["avg_cost"] or 0),
                            "Preço": float(r["sell_price"] or 0),
                        }
                        for r in rows
                    ]
                )
                st.dataframe(
                    df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Custo médio": st.column_config.NumberColumn(format="%.2f"),
                        "Preço": st.column_config.NumberColumn(format="%.2f"),
                        "Estoque": st.column_config.NumberColumn(format="%.4f"),
                    },
                )

                pick_labels = [
                    f"{r['id']}  |  {r['sku'] or '—'}  |  {r['name'] or '—'}" for r in rows
                ]
                pick = st.selectbox(
                    "Selecionar produto (detalhes)",
                    ["—"] + pick_labels,
                    key="sku_search_product_focus",
                )
                if pick != "—":
                    focus_id = int(pick.split("|", 1)[0].strip())
                    st.session_state["products_focus_product_id"] = focus_id
                    pr = fetch_product_by_id(focus_id)
                    if pr is not None:
                        st.success(
                            f"Produto **ID `{pr['id']}`** — SKU `{pr['sku'] or '—'}`."
                        )
                        with st.container(border=True):
                            st.markdown(
                                f"- **SKU:** `{pr['sku'] or '—'}`\n"
                                f"- **Nome:** {pr['name']}\n"
                                f"- **Cor armação · Cor lente · Gênero · Paleta · Estilo:** "
                                f"{pr['frame_color'] or '—'} · {pr['lens_color'] or '—'} · "
                                f"{pr['gender'] or '—'} · "
                                f"{pr['palette'] or '—'} · {pr['style'] or '—'}\n"
                                f"- **Estoque:** {format_qty_display_4(float(pr['stock'] or 0))}\n"
                                f"- **Custo médio (SKU):** {format_money(float(pr['avg_cost'] or 0))}\n"
                                f"- **Preço (SKU):** {format_money(float(pr['sell_price'] or 0))}\n"
                                f"- **Código de entrada:** {pr['product_enter_code'] or '—'}\n"
                                f"- **Cadastro (registro):** "
                                f"{format_product_created_display(pr['created_at'])}"
                            )
                            st.caption(
                                "Use este SKU em **Estoque**, **Custos**, **Precificação** e **Vendas**."
                            )

        st.markdown("### Cadastro de produto")
        st.caption(
            "Cadastre apenas **novos lotes** (identidade + atributos). Exclusão de estoque é feita em **Estoque**. "
            "Se cadastrar o mesmo **nome + data + cor da armação + cor da lente + estilo + paleta + gênero**, "
            "o lote é **mesclado**. "
            "O **SKU** é gerado como `[SEQ]-[PP]-[FC]-[LC]-[GG]-[PA]-[ST]`. "
            "**Estoque** e **custo unitário** entram na página **Custos** (média ponderada por SKU)."
        )
        _prod_ok = st.session_state.pop("prod_reg_success_msg", None)
        if _prod_ok:
            st.success(_prod_ok)

        # No st.form here: form widgets buffer values until submit, which breaks live SKU preview and
        # session_state sync. Inputs keep their values on validation errors via widget keys.
        name = st.text_input(
            "Nome do produto",
            placeholder="ex.: Óculos modelo A",
            key="prod_reg_name",
        )
        registered_date = st.date_input(
            "Data de registro",
            value=datetime.now().date(),
            key="prod_reg_date",
        )
        c1, c2 = st.columns(2)
        with c1:
            frame_opts = dropdown_with_other(PRODUCT_FRAME_COLOR_OPTIONS)
            frame_color_choice = attribute_selectbox(
                "Cor da armação",
                frame_opts,
                key="prod_reg_frame_color",
                current_value="",
            )

            palette_opts = dropdown_with_other(PRODUCT_PALETTE_OPTIONS)
            palette_choice = attribute_selectbox(
                "Paleta", palette_opts, key="prod_reg_palette", current_value=""
            )
        with c2:
            lens_opts = dropdown_with_other(PRODUCT_LENS_COLOR_OPTIONS)
            lens_color_choice = attribute_selectbox(
                "Cor da lente",
                lens_opts,
                key="prod_reg_lens_color",
                current_value="",
            )

            gender_opts = dropdown_with_other(PRODUCT_GENDER_OPTIONS)
            gender_choice = attribute_selectbox(
                "Gênero", gender_opts, key="prod_reg_gender", current_value=""
            )

        style_opts = dropdown_with_other(PRODUCT_STYLE_OPTIONS)
        style_choice = attribute_selectbox(
            "Estilo", style_opts, key="prod_reg_style", current_value=""
        )

        preview_sku = _maybe_preview_product_sku()
        if preview_sku:
            st.info(f"**SKU gerado (somente leitura):** `{preview_sku}`")
        else:
            st.caption(
                "Selecione todos os atributos para visualizar o SKU. Ele não pode ser editado manualmente."
            )

        if st.button("Cadastrar produto", type="primary", key="prod_reg_submit"):
            if not name.strip():
                st.error("O nome do produto é obrigatório.")
            else:
                frame_val, err_fc = resolve_attribute_value(
                    frame_color_choice, "", "a cor da armação"
                )
                lens_val, err_lc = resolve_attribute_value(
                    lens_color_choice, "", "a cor da lente"
                )
                palette_val, err_p = resolve_attribute_value(palette_choice, "", "a paleta")
                gender_val, err_g = resolve_attribute_value(gender_choice, "", "o gênero")
                style_val, err_s = resolve_attribute_value(style_choice, "", "o estilo")
                field_errors = [e for e in (err_fc, err_lc, err_p, err_g, err_s) if e]
                if field_errors:
                    for e in field_errors:
                        st.error(e)
                else:
                    try:
                        enter_code = add_product(
                            name=name,
                            stock=0,
                            registered_date=registered_date,
                            frame_color=frame_val,
                            lens_color=lens_val,
                            style=style_val,
                            palette=palette_val,
                            gender=gender_val,
                            unit_cost=0.0,
                        )
                    except Exception as e:
                        st.error(f"Não foi possível cadastrar o produto: {e}")
                    else:
                        st.session_state["prod_reg_success_msg"] = (
                            f"Lote salvo. **Código de entrada:** `{enter_code}`. "
                            "Inclua estoque em **Custos**, se necessário."
                        )
                        for k in (
                            "prod_reg_name",
                            "prod_reg_date",
                            "prod_reg_frame_color",
                            "prod_reg_lens_color",
                            "prod_reg_palette",
                            "prod_reg_gender",
                            "prod_reg_style",
                        ):
                            st.session_state.pop(k, None)
                        st.rerun()

    elif page == PAGE_VENDAS:
        st.markdown("### Vendas")
        st.caption(
            "Fluxo: **1) SKU** → **2) Cliente** → **3) Quantidade** → **4) Desconto** → **Confirmar**. "
            "Cada venda gera um **ID de venda** (#####V). O estoque sai do **lote** selecionado."
        )

        sales_skus = fetch_skus_available_for_sale()
        customers_all = fetch_customers_ordered()

        product_id: Optional[int] = None
        sku_sel = ""
        unit_price = 0.0
        available_stock = 0.0
        batch_row = None

        # --- Etapa 1 — escolher SKU ---
        st.markdown("#### Etapa 1 — Escolher SKU")
        if not sales_skus:
            st.info(
                "Nenhum SKU pronto para venda. Inclua **estoque** (Custos) e defina um **preço ativo** (Precificação)."
            )
        else:
            sku_labels = [
                f"{r['sku']}  —  {r['sample_name'] or '—'}  (estoque SKU: {float(r['total_stock'] or 0):g})"
                for r in sales_skus
            ]
            sku_map = {sku_labels[i]: sales_skus[i] for i in range(len(sku_labels))}
            picked_sku_label = st.selectbox(
                "Escolher SKU",
                options=sku_labels,
                key="sales_step1_sku_label",
            )
            row_sku = sku_map[picked_sku_label]
            sku_sel = str(row_sku["sku"] or "").strip()
            unit_price = float(row_sku["selling_price"] or 0)

            batches = fetch_product_batches_in_stock_for_sku(sku_sel)
            if not batches:
                st.error(
                    "Este SKU não tem lotes com estoque (os dados podem ter mudado). Atualize a página."
                )
            elif len(batches) == 1:
                batch_row = batches[0]
                product_id = int(batch_row["id"])
                st.caption("Único lote em estoque para este SKU — usado automaticamente.")
            else:
                batch_labels = [
                    f"{b['product_enter_code'] or '—'} | estoque lote {float(b['stock']):g} | {b['name']}"
                    for b in batches
                ]
                bl = st.selectbox(
                    "Lote (vários lotes para este SKU)",
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
                    st.error("O lote selecionado não existe mais.")
                    product_id = None
                else:
                    available_stock = float(pr["stock"] or 0)
                    with st.container(border=True):
                        st.markdown(f"**SKU:** `{sku_sel}`")
                        st.markdown(
                            f"**Produto / lote:** {pr['name']}  ·  código **{batch_row['product_enter_code'] or '—'}**"
                        )
                        attrs = " · ".join(
                            x
                            for x in (
                                batch_row["frame_color"],
                                batch_row["lens_color"],
                                batch_row["style"],
                                batch_row["palette"],
                                batch_row["gender"],
                            )
                            if x
                        )
                        if attrs:
                            st.caption(attrs)
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Estoque (este lote)", f"{available_stock:g}")
                        c2.metric(
                            "Estoque total SKU (todos os lotes)",
                            f"{float(row_sku['total_stock'] or 0):g}",
                        )
                        c3.metric("Preço unitário ativo (Precificação)", format_money(unit_price))

        st.divider()

        # --- Etapa 2 — cliente ---
        st.markdown("#### Etapa 2 — Cliente")
        cust_id: Optional[int] = None
        cust_display = "—"
        if not customers_all:
            st.warning("Nenhum cliente. Cadastre em **Clientes** antes de vender.")
        else:
            search_q = st.text_input(
                "Buscar por nome ou código do cliente",
                key="sales_cust_search",
                placeholder="Filtrar a lista…",
            )
            filtered_c = filter_customers_by_search(customers_all, search_q)
            if not filtered_c:
                st.warning("Nenhum cliente corresponde à busca.")
            else:
                cust_labels = [
                    f"{c['customer_code']} — {c['name']}" for c in filtered_c
                ]
                cust_pick = st.selectbox(
                    "Cliente",
                    options=cust_labels,
                    key="sales_cust_select",
                )
                idx_c = cust_labels.index(cust_pick)
                cust_id = int(filtered_c[idx_c]["id"])
                cust_display = cust_pick

        st.divider()

        # --- Etapa 3 — quantidade ---
        st.markdown("#### Etapa 3 — Quantidade")
        max_sale_qty = int(math.floor(available_stock + 1e-9))
        if product_id is None or available_stock <= 0:
            st.caption("Conclua a **Etapa 1** para informar a quantidade.")
            quantity = 0
        elif max_sale_qty < 1:
            st.warning(
                f"O estoque neste lote é **{available_stock:g}**, insuficiente para vender "
                "**1** unidade inteira. Ajuste o estoque ou escolha outro lote."
            )
            quantity = 0
        else:
            st.caption(
                f"Disponível neste lote: **{available_stock:g}** (não venda acima do estoque)."
            )
            quantity = int(
                st.number_input(
                    "Quantidade a vender",
                    min_value=1,
                    max_value=max_sale_qty,
                    step=1,
                    value=min(1, max_sale_qty),
                    format="%d",
                    key=f"sales_qty_{product_id}",
                )
            )

        st.divider()

        # --- Etapa 4 — desconto ---
        st.markdown("#### Etapa 4 — Desconto")
        disc_mode = st.radio(
            "Tipo de desconto",
            ["Percentual (%)", "Valor fixo"],
            horizontal=True,
            key="sales_disc_mode",
        )
        base_price = float(quantity) * unit_price if product_id else 0.0
        if disc_mode == "Percentual (%)":
            pct = float(
                st.number_input(
                    "Desconto percentual",
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
                    "Valor do desconto",
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
        m1.metric("Subtotal (preço × qtd)", format_money(base_price))
        m2.metric("Desconto", format_money(discount_amount))
        m3.metric("Total final", format_money(final_price))

        st.divider()

        # --- SUMMARY & CONFIRM ---
        st.markdown("#### Conferência e confirmação")
        ready = (
            product_id is not None
            and cust_id is not None
            and unit_price > 0
            and quantity >= 1
            and float(quantity) <= available_stock + 1e-9
        )
        if not ready:
            st.info(
                "Preencha todas as etapas acima. A quantidade deve ser **> 0** e **≤ estoque disponível**."
            )
        else:
            with st.container(border=True):
                st.markdown("**Resumo da venda**")
                sum_tbl = {
                    "SKU": f"`{sku_sel}`",
                    "Cliente": cust_display,
                    "Quantidade": str(quantity),
                    "Preço unitário": format_money(unit_price),
                    "Subtotal": format_money(base_price),
                    "Desconto": format_money(discount_amount),
                    "Total": format_money(final_price),
                }
                st.table(
                    [{"Campo": k, "Valor": v} for k, v in sum_tbl.items()]
                )

            confirm = st.checkbox(
                "Confirmo esta venda (o estoque será baixado e o registro de venda será criado).",
                key="sales_confirm_chk",
            )
            if st.button(
                "Concluir venda",
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
                        f"Venda **{code}** registrada. Total: **{format_money(total)}**"
                    )
                    st.session_state.pop("sales_confirm_chk", None)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
                except Exception:
                    st.error("Falha ao registrar a venda. Tente novamente.")

        st.divider()
        st.markdown("#### Vendas recentes")
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
            st.info("Ainda não há vendas.")
        else:
            data = [
                {
                    "ID venda": r["sale_code"] or f"#{r['id']}",
                    "SKU": r["sku"] or "—",
                    "Produto": r["product_name"],
                    "Cliente": r["customer_label"],
                    "Qtd": r["quantity"],
                    "Unit.": format_money(float(r["unit_price"] or 0)),
                    "Desconto": format_money(float(r["discount_amount"] or 0)),
                    "Total": format_money(float(r["total"] or 0)),
                    "Data/Hora": r["sold_at"],
                }
                for r in recent
            ]
            st.dataframe(data, width="stretch", hide_index=True)

    elif page == PAGE_PAINEL:
        st.markdown("### Painel")
        stats = compute_dashboard()
        revenue, cost, profit_loss = compute_sales_financials()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Receita", format_money(stats["revenue"]))
        col2.metric("Vendas", stats["sales_count"])
        col3.metric("Unidades em estoque", stats["total_stock_units"])
        col4.metric("Estoque baixo (≤5)", stats["low_stock"])

        st.divider()
        st.markdown("### Resultado (DRE simplificada — vendas realizadas)")
        menu_col1, menu_col2, menu_col3 = st.columns(3)
        menu_col1.metric("Receita", format_money(revenue))
        menu_col2.metric("Custo", format_money(cost))
        menu_col3.metric("Lucro / prejuízo", format_money(profit_loss))

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown("#### Receita ao longo do tempo")
            df = fetch_revenue_timeseries()
            if df.empty:
                st.info("Sem vendas ainda. Registre a primeira venda para ver a receita.")
            else:
                st.line_chart(df.set_index("day")["revenue"])

        with col_right:
            st.markdown("#### Produtos com estoque baixo")
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
                st.success("Nenhum produto com estoque baixo.")
            else:
                data = [
                    {
                        "ID": r["id"],
                        "Nome": r["name"],
                        "Preço venda": format_money(r["price"]),
                        "Estoque": r["stock"],
                    }
                    for r in low
                ]
                st.dataframe(data, width="stretch", hide_index=True)

    elif page == PAGE_CUSTOS:
        st.markdown("### Custos")

        st.caption(
            "**Composição de custo do SKU**: custos planejados (preço unitário × quantidade), gravados por SKU. "
            "**Custo médio ponderado (CMP)** atualiza só com **entradas de estoque**; vendas não alteram o CMP. "
            "**Preço de venda** fica em **Precificação**."
        )

        sku_rows = fetch_sku_master_rows()
        sku_list = [r["sku"] for r in sku_rows] if sku_rows else []

        st.markdown("#### Composição de custo do SKU (componentes planejados)")
        if not sku_list:
            st.info(
                "Ainda não há SKUs no cadastro mestre. Cadastre um produto em **Produtos** e inclua estoque "
                "(ou confira o `sku_master`) para usar a composição de custo."
            )
        else:
            sel_sku = st.selectbox(
                "SKU para composição de custo",
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
                "Quantidade: até **4** casas decimais (vazio = 0). Preço unitário: **2** casas. "
                "Os totais atualizam ao editar."
            )

            with st.container(border=True):
                for key, label in SKU_COST_COMPONENT_DEFINITIONS:
                    st.markdown(f"**{label}**")
                    qcol, pcol, tcol = st.columns([1, 1, 1])
                    with qcol:
                        st.text_input(
                            "Quantidade",
                            key=f"scq_{sel_sku}_{key}",
                            help="Até 4 decimais (ex.: 0,25 ou 1,0000).",
                        )
                    with pcol:
                        st.number_input(
                            "Preço unitário",
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
                            st.metric("Total linha", "—")
                            if qe:
                                st.caption(qe)
                            if pe:
                                st.caption(pe)
                        else:
                            st.metric("Total linha", format_money(qv * pv))

            live_total = 0.0
            err_msgs = []
            for key, label in SKU_COST_COMPONENT_DEFINITIONS:
                qt = st.session_state.get(f"scq_{sel_sku}_{key}", "")
                up = float(st.session_state.get(f"scp_{sel_sku}_{key}", 0.0))
                qv, qe = parse_cost_quantity_text(str(qt))
                pv, pe = parse_cost_unit_price_value(up)
                if qe:
                    err_msgs.append(f"{label} — quantidade: {qe}")
                if pe:
                    err_msgs.append(f"{label} — preço unit.: {pe}")
                if not qe and not pe:
                    live_total += qv * pv

            st.metric("Custo total (SKU, ao vivo)", format_money(live_total))
            saved_row = next((r for r in sku_rows if r["sku"] == sel_sku), None)
            if saved_row is not None:
                st.caption(
                    f"Último total salvo: **{format_money(float(saved_row['structured_cost_total'] or 0))}**"
                )

            if st.button("Salvar composição de custo", type="primary", key="costing_struct_save"):
                payload = []
                save_errs = []
                for key, label in SKU_COST_COMPONENT_DEFINITIONS:
                    qt = st.session_state.get(f"scq_{sel_sku}_{key}", "")
                    up = float(st.session_state.get(f"scp_{sel_sku}_{key}", 0.0))
                    qv, qe = parse_cost_quantity_text(str(qt))
                    pv, pe = parse_cost_unit_price_value(up)
                    if qe:
                        save_errs.append(f"{label} — quantidade: {qe}")
                    if pe:
                        save_errs.append(f"{label} — preço unit.: {pe}")
                    payload.append((key, pv, qv))
                if save_errs:
                    for e in save_errs:
                        st.error(e)
                else:
                    try:
                        save_sku_cost_structure(sel_sku, payload)
                        st.success("Composição de custo salva.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

            if err_msgs:
                st.warning("Corrija os erros acima antes de salvar.")

        if sku_rows:
            st.markdown("#### Valorização atual do estoque por SKU")
            sm_data = [
                {
                    "SKU": r["sku"],
                    "Estoque total": format_qty_display_4(float(r["total_stock"] or 0)),
                    "Custo médio (CMP)": format_money(float(r["avg_unit_cost"] or 0)),
                    "Custo estruturado": format_money(float(r["structured_cost_total"] or 0)),
                    "Atualizado": r["updated_at"] or "—",
                }
                for r in sku_rows
            ]
            st.dataframe(sm_data, width="stretch", hide_index=True)

        st.markdown("#### Entrada de estoque (fluxo por SKU)")
        st.caption(
            "**Etapa 1** — Escolha o SKU (carrega componentes salvos). **Etapa 2** — Lote que recebe a mercadoria. "
            "**Etapa 3** — Quantidade a adicionar (> 0, até 4 decimais). **Etapa 4** — Custo unitário = **total** "
            "da composição salva acima. **Etapa 5** — Confirme o resumo e finalize — o **CMP** atualiza pela média ponderada."
        )

        if not sku_list:
            st.info("Nenhum SKU disponível para entrada de estoque.")
        else:
            stock_entry_sku = st.selectbox(
                "Etapa 1 — Selecionar SKU",
                options=sku_list,
                key="costing_stock_entry_sku",
            )
            marker_stock = "costing_stock_entry_sku_marker"
            if st.session_state.get(marker_stock) != stock_entry_sku:
                st.session_state[marker_stock] = stock_entry_sku
                st.session_state["costing_stock_qty_text"] = ""

            loaded_components = fetch_sku_cost_components_for_sku(stock_entry_sku)
            with st.expander("Componentes de custo deste SKU (somente leitura)", expanded=False):
                comp_rows = [
                    {
                        "Componente": r["label"],
                        "Preço unit.": format_money(float(r["unit_price"] or 0)),
                        "Qtd": format_qty_display_4(float(r["quantity"] or 0)),
                        "Linha": format_money(float(r["line_total"] or 0)),
                    }
                    for r in loaded_components
                ]
                st.dataframe(comp_rows, width="stretch", hide_index=True)

            batches = fetch_product_batches_for_sku(stock_entry_sku)
            if not batches:
                st.warning(
                    "Não há lotes de produto para este SKU. Cadastre em **Produtos** primeiro "
                    "(mesmo SKU gerado)."
                )
            else:
                batch_labels = {}
                for p in batches:
                    attrs = " · ".join(
                        x
                        for x in (
                            p["frame_color"] or "",
                            p["lens_color"] or "",
                            p["style"] or "",
                            p["palette"] or "",
                            p["gender"] or "",
                        )
                        if x
                    )
                    extra = f" ({attrs})" if attrs else ""
                    label = (
                        f"{p['name']}{extra} | Cód.: {p['product_enter_code'] or '—'} | "
                        f"Estoque: {format_qty_display_4(float(p['stock'] or 0))}"
                    )
                    batch_labels[label] = p

                pick_b = st.selectbox(
                    "Etapa 2 — Lote destinatário",
                    options=list(batch_labels.keys()),
                    key="costing_stock_entry_batch",
                )
                pr = batch_labels[pick_b]
                pid = int(pr["id"])
                psku = (pr["sku"] or "").strip()

                qty_raw = st.text_input(
                    "Etapa 3 — Quantidade a adicionar ao estoque",
                    key="costing_stock_qty_text",
                    help="Deve ser maior que zero. Até 4 decimais (ex.: 12,5000).",
                )
                qv, qe = parse_cost_quantity_text(str(qty_raw))
                try:
                    unit_cost = get_persisted_structured_unit_cost(stock_entry_sku)
                except ValueError:
                    unit_cost = 0.0

                st.markdown("**Etapa 4 — Custo unitário (estrutura salva)**")
                if unit_cost > 0:
                    st.metric("Custo unitário calculado", format_money(unit_cost))
                else:
                    st.warning(
                        "Custo unitário estruturado está **zero** ou ausente. Salve a **composição de custo** acima "
                        "(totais não zerados) antes de dar entrada."
                    )

                total_entry = 0.0
                if qe is None and qv > 0 and unit_cost > 0:
                    total_entry = round(qv * unit_cost, 2)
                    st.metric("Custo total da entrada (unit. × qtd)", format_money(total_entry))

                if qe:
                    st.error(qe)
                elif (qty_raw or "").strip() != "" and qv <= 0:
                    st.error("A quantidade deve ser maior que zero.")

                st.markdown("**Resumo da confirmação**")
                st.write(f"- **SKU:** `{stock_entry_sku}`")
                st.write(
                    f"- **Quantidade:** `{format_qty_display_4(qv) if qe is None else '—'}`"
                )
                st.write(f"- **Custo unitário:** `{format_money(unit_cost) if unit_cost > 0 else '—'}`")
                st.write(
                    f"- **Custo total:** `{format_money(total_entry) if total_entry > 0 else '—'}`"
                )

                confirm_ok = st.checkbox(
                    "Confirmo que esta entrada de estoque está correta.",
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
                    "Finalizar entrada de estoque",
                    type="primary",
                    key="costing_stock_finalize",
                    disabled=not can_finalize,
                ):
                    try:
                        add_stock_receipt(stock_entry_sku.strip(), pid, float(qv), float(unit_cost))
                        st.success(
                            "Entrada registrada. Custo médio (CMP) do SKU atualizado."
                        )
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

        st.markdown("#### Histórico de custos de estoque (auditoria)")
        entries = fetch_recent_stock_cost_entries(75)
        if not entries:
            st.caption("Nenhuma entrada de estoque registrada ainda.")
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
                        "ID produto": r["product_id"],
                        "Qtd": format_qty_display_4(float(r["quantity"] or 0)),
                        "Custo unit.": format_money(float(r["unit_cost"])),
                        "Custo total entrada": format_money(float(te)),
                        "Estoque antes": format_qty_display_4(float(r["stock_before"] or 0)),
                        "Estoque depois": format_qty_display_4(float(r["stock_after"] or 0)),
                        "CMP antes": format_money(float(r["avg_cost_before"])),
                        "CMP depois": format_money(float(r["avg_cost_after"])),
                        "Em": r["created_at"],
                    }
                )
            st.dataframe(eh, width="stretch", hide_index=True)

    elif page == PAGE_PRECIFICACAO:
        st.markdown("### Precificação (por SKU)")

        st.caption(
            "**Etapa 1** — Escolha o SKU; **custo base** = **custo médio ponderado (CMP)** atual. "
            "**Etapa 2** — Informe margem, impostos e encargos em % (≥ 0). **Etapa 3** — Revise os preços "
            "calculados. **Etapa 4** — Salvar cria um **novo** registro (não apaga históricos). "
            "O registro **ativo** é o último salvo; **Vendas** usa o **preço alvo** dele."
        )

        sku_rows = fetch_sku_master_rows()
        if not sku_rows:
            st.info("Ainda não há SKUs. Cadastre produtos em **Produtos** primeiro.")
            return

        sku_list = [r["sku"] for r in sku_rows]
        sel_sku = st.selectbox("Etapa 1 — Selecionar SKU", options=sku_list, key="pricing_sku_select")

        sm = next((r for r in sku_rows if r["sku"] == sel_sku), None)
        if sm is None:
            st.error("SKU não encontrado.")
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
                "Estoque total (todos os lotes)",
                format_qty_display_4(_ts) if abs(_ts) >= 1e-12 else "0",
            )
        with c2:
            avg_cost = float(sm["avg_unit_cost"] or 0)
            st.metric("Custo base — CMP (estoque)", format_money(avg_cost))
        with c3:
            st.metric("Preço de venda atual (SKU)", format_money(float(sm["selling_price"] or 0)))

        if avg_cost <= 0:
            st.warning(
                "Custo médio do estoque **indisponível** (CMP zero). Dê entrada em **Custos** antes de precificar."
            )

        st.markdown("#### Etapa 2 — Parâmetros de preço (%)")
        st.caption("Todos os valores são percentuais, com duas casas decimais (ex.: 10,50%).")
        pc1, pc2, pc3 = st.columns(3)
        with pc1:
            markup_pct = st.number_input(
                "Margem (%)",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="pricing_wf_markup",
            )
        with pc2:
            taxes_pct = st.number_input(
                "Impostos (%)",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="pricing_wf_taxes",
            )
        with pc3:
            interest_pct = st.number_input(
                "Encargos / juros (%)",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="pricing_wf_interest",
            )

        st.markdown("#### Etapa 3 — Preços calculados")
        if avg_cost > 0:
            pb, pwt, tgt = compute_sku_pricing_targets(
                avg_cost, float(markup_pct), float(taxes_pct), float(interest_pct)
            )
            st.caption(
                "1) Preço antes de impostos = CMP + (CMP × Margem%). "
                "2) Preço com impostos = (1) + ((1) × Impostos%). "
                "3) Preço alvo = (2) + ((2) × Encargos%)."
            )
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Preço antes de impostos e encargos", format_money(pb))
            with m2:
                st.metric("Preço com impostos", format_money(pwt))
            with m3:
                st.metric("Preço alvo (usado em Vendas)", format_money(tgt))
        else:
            pb, pwt, tgt = (0.0, 0.0, 0.0)
            st.info(
                "Registre entradas de estoque para o CMP ser maior que zero e ver os cálculos."
            )

        st.markdown("#### Etapa 4 — Salvar preço (novo registro no histórico)")
        can_save = avg_cost > 0 and tgt > 0
        if st.button(
            "Salvar precificação (novo registro e ativar)",
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
                    "Precificação salva. Novo registro criado; histórico preservado. Preço alvo ativo para Vendas."
                )
                st.rerun()
            except ValueError as e:
                st.error(str(e))

        st.markdown("#### Histórico de precificação (registros do fluxo)")
        wf_rows = fetch_sku_pricing_records_for_sku(sel_sku, 100)
        if not wf_rows:
            st.caption("Nenhum registro ainda. Salve acima para criar o primeiro.")
        else:
            wf_df = [
                {
                    "ID": r["id"],
                    "Ativo": "Sim" if int(r["is_active"] or 0) else "—",
                    "CMP (instantâneo)": format_money(float(r["avg_cost_snapshot"])),
                    "Margem %": f"{float(r['markup_pct']):.2f}%",
                    "Impostos %": f"{float(r['taxes_pct']):.2f}%",
                    "Encargos %": f"{float(r['interest_pct']):.2f}%",
                    "Preço pré-impostos": format_money(float(r["price_before_taxes"])),
                    "Preço c/ impostos": format_money(float(r["price_with_taxes"])),
                    "Preço alvo": format_money(float(r["target_price"])),
                    "Salvo em": r["created_at"],
                }
                for r in wf_rows
            ]
            st.dataframe(wf_df, width="stretch", hide_index=True)

        st.markdown("#### Auditoria de preço de venda (legado)")
        st.caption("Inclui salvamentos do fluxo e alterações manuais antigas.")
        ph = fetch_price_history_for_sku(sel_sku, 50)
        if not ph:
            st.caption("Nenhuma entrada no log legado ainda.")
        else:
            ph_df = [
                {
                    "ID": r["id"],
                    "Anterior": format_money(float(r["old_price"])) if r["old_price"] is not None else "—",
                    "Novo": format_money(float(r["new_price"])),
                    "Em": r["created_at"],
                    "Obs.": r["note"] or "",
                }
                for r in ph
            ]
            st.dataframe(ph_df, width="stretch", hide_index=True)

    elif page == PAGE_CLIENTES:
        st.markdown("### Clientes")
        st.caption(
            "Cadastre clientes com busca opcional de endereço via **ViaCEP**. "
            "**Salvar cliente** grava na tabela local **`customers`** do SQLite "
            f"(`{DB_PATH.name}` na pasta do aplicativo). "
            "O **código do cliente** é gerado pelo banco — não preencha no formulário."
        )

        tab_reg, tab_edit = st.tabs(["Cadastrar", "Editar cliente"])

        with tab_reg:
            st.markdown("#### Novo cliente")
            cep_row = st.columns([3, 1])
            with cep_row[0]:
                st.text_input(
                    "CEP",
                    key="cust_reg_cep",
                    placeholder="00000-000",
                    help="Digite 8 dígitos e clique em **Buscar CEP** para preencher rua, bairro, cidade e UF.",
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
                        st.success("Endereço carregado — você pode ajustar os campos abaixo.")
                        st.rerun()

            with st.form("cust_reg_form"):
                c1, c2 = st.columns(2)
                with c1:
                    st.text_input(
                        "Nome *",
                        key="cust_reg_name",
                        placeholder="Nome completo",
                    )
                    st.text_input(
                        "CPF",
                        key="cust_reg_cpf",
                        placeholder="000.000.000-00",
                    )
                    st.text_input("RG", key="cust_reg_rg")
                    st.text_input(
                        "Telefone",
                        key="cust_reg_phone",
                        placeholder="+55 …",
                    )
                with c2:
                    st.text_input("E-mail", key="cust_reg_email")
                    st.text_input(
                        "Instagram",
                        key="cust_reg_instagram",
                        placeholder="@usuario ou URL",
                    )

                st.markdown("##### Endereço")
                st1, st2 = st.columns([3, 1])
                with st1:
                    st.text_input("Logradouro", key="cust_reg_street")
                with st2:
                    st.text_input("Número", key="cust_reg_number")
                st3, st4 = st.columns(2)
                with st3:
                    st.text_input("Bairro", key="cust_reg_neighborhood")
                with st4:
                    st.text_input("Cidade", key="cust_reg_city")
                st5, st6 = st.columns(2)
                with st5:
                    st.text_input("UF", key="cust_reg_state", max_chars=2)
                with st6:
                    st.text_input(
                        "País",
                        key="cust_reg_country",
                        placeholder="Brasil",
                    )

                reg_submitted = st.form_submit_button("Salvar cliente", type="primary")

            if reg_submitted:
                name = (st.session_state.get("cust_reg_name") or "").strip()
                if not name:
                    st.error("O nome é obrigatório.")
                else:
                    cep_digits = sanitize_cep_digits(
                        st.session_state.get("cust_reg_cep", "")
                    )
                    if cep_digits and len(cep_digits) != 8:
                        st.error(
                            "Se o CEP for preenchido, deve ter exatamente 8 dígitos."
                        )
                    else:
                        cpf = normalize_cpf_digits(
                            st.session_state.get("cust_reg_cpf", "")
                        )
                        if cpf and not validate_cpf_br(cpf):
                            st.error("CPF inválido (verifique os dígitos).")
                        elif not validate_email_optional(
                            st.session_state.get("cust_reg_email", "")
                        ):
                            st.error("E-mail com formato inválido.")
                        else:
                            rg = (st.session_state.get("cust_reg_rg") or "").strip() or None
                            phone = normalize_phone_digits(
                                st.session_state.get("cust_reg_phone", "")
                            )
                            email = (
                                st.session_state.get("cust_reg_email") or ""
                            ).strip() or None
                            instagram = (
                                st.session_state.get("cust_reg_instagram") or ""
                            ).strip() or None
                            cep = cep_digits if cep_digits else None
                            street = (
                                st.session_state.get("cust_reg_street") or ""
                            ).strip() or None
                            number = (
                                st.session_state.get("cust_reg_number") or ""
                            ).strip() or None
                            neighborhood = (
                                st.session_state.get("cust_reg_neighborhood") or ""
                            ).strip() or None
                            city = (
                                st.session_state.get("cust_reg_city") or ""
                            ).strip() or None
                            state = (
                                st.session_state.get("cust_reg_state") or ""
                            ).strip() or None
                            country = (
                                st.session_state.get("cust_reg_country") or ""
                            ).strip() or None
                            try:
                                new_code = insert_customer_row(
                                    name=name,
                                    cpf=cpf if cpf else None,
                                    rg=rg,
                                    phone=phone if phone else None,
                                    email=email,
                                    instagram=instagram,
                                    zip_code=cep,
                                    street=street,
                                    number=number,
                                    neighborhood=neighborhood,
                                    city=city,
                                    state=state,
                                    country=country,
                                )
                                st.success(
                                    f"Cliente salvo! Código **{new_code}**."
                                )
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
                            except Exception as e:
                                st.error(f"Erro: {e}")

            st.divider()
            st.markdown("#### Todos os clientes")
            all_cust = fetch_customers_ordered()
            if not all_cust:
                st.caption("Nenhum cliente ainda.")
            else:
                df_c = pd.DataFrame(
                    [
                        {
                            "Código": r["customer_code"],
                            "Nome": r["name"],
                            "CPF": r["cpf"] or "—",
                            "Telefone": r["phone"] or "—",
                            "Cidade": r["city"] or "—",
                            "CEP": r["zip_code"] or "—",
                            "Atualizado": r["updated_at"] or "—",
                        }
                        for r in all_cust
                    ]
                )
                st.dataframe(df_c, width="stretch", hide_index=True)

        with tab_edit:
            st.markdown("#### Editar cliente")
            rows_edit = fetch_customers_ordered()
            if not rows_edit:
                st.info("Nenhum cliente — cadastre na aba **Cadastrar**.")
            else:
                labels = [f"{r['customer_code']} — {r['name']}" for r in rows_edit]
                sel = st.selectbox("Cliente", labels, key="cust_edit_sel")
                idx = labels.index(sel)
                row = rows_edit[idx]
                cid = int(row["id"])
                cc = row["customer_code"]
                st.caption(f"Código do cliente **{cc}** (somente leitura).")

                if st.session_state.get("cust_edit_pick_id") != cid:
                    st.session_state["cust_edit_pick_id"] = cid
                    init_cust_edit_session(row, cid)

                cep_row_e = st.columns([3, 1])
                with cep_row_e[0]:
                    st.text_input(
                        "CEP",
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
                            st.success("Endereço carregado — edite abaixo.")
                            st.rerun()

                with st.form(f"cust_edit_form_{cid}"):
                    e1, e2 = st.columns(2)
                    with e1:
                        st.text_input("Nome *", key=f"cust_edit_name_{cid}")
                        st.text_input("CPF", key=f"cust_edit_cpf_{cid}")
                        st.text_input("RG", key=f"cust_edit_rg_{cid}")
                        st.text_input("Telefone", key=f"cust_edit_phone_{cid}")
                    with e2:
                        st.text_input("E-mail", key=f"cust_edit_email_{cid}")
                        st.text_input(
                            "Instagram",
                            key=f"cust_edit_instagram_{cid}",
                        )

                    st.markdown("##### Endereço")
                    e_st1, e_st2 = st.columns([3, 1])
                    with e_st1:
                        st.text_input("Logradouro", key=f"cust_edit_street_{cid}")
                    with e_st2:
                        st.text_input("Número", key=f"cust_edit_number_{cid}")
                    e_st3, e_st4 = st.columns(2)
                    with e_st3:
                        st.text_input(
                            "Bairro",
                            key=f"cust_edit_neighborhood_{cid}",
                        )
                    with e_st4:
                        st.text_input("Cidade", key=f"cust_edit_city_{cid}")
                    e_st5, e_st6 = st.columns(2)
                    with e_st5:
                        st.text_input(
                            "UF",
                            key=f"cust_edit_state_{cid}",
                            max_chars=2,
                        )
                    with e_st6:
                        st.text_input("País", key=f"cust_edit_country_{cid}")

                    edit_submitted = st.form_submit_button("Salvar alterações", type="primary")

                if edit_submitted:
                    name_val = (
                        st.session_state.get(f"cust_edit_name_{cid}") or ""
                    ).strip()
                    if not name_val:
                        st.error("O nome é obrigatório.")
                    else:
                        cep_digits = sanitize_cep_digits(
                            st.session_state.get(f"cust_edit_cep_{cid}", "")
                        )
                        if cep_digits and len(cep_digits) != 8:
                            st.error(
                                "Se o CEP for preenchido, deve ter exatamente 8 dígitos."
                            )
                        else:
                            cpf_norm = normalize_cpf_digits(
                                st.session_state.get(f"cust_edit_cpf_{cid}", "")
                            )
                            if cpf_norm and not validate_cpf_br(cpf_norm):
                                st.error("CPF inválido (verifique os dígitos).")
                            elif not validate_email_optional(
                                st.session_state.get(f"cust_edit_email_{cid}", "")
                            ):
                                st.error("E-mail com formato inválido.")
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
                                    st.success("Cliente atualizado.")
                                    st.session_state.pop("cust_edit_pick_id", None)
                                    st.rerun()

    elif page == PAGE_ESTOQUE:
        st.markdown(
            """
            <style>
            /* Tipografia da página Estoque: dois passos de ×30% em relação à base 12–13px (0.7² = 0.49). */
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
        st.markdown("### Estoque")

        products = fetch_products()
        in_stock_products = [p for p in products if float(p["stock"] or 0) > 0]

        if not in_stock_products:
            st.info("Sem estoque disponível. Cadastre produtos com quantidade primeiro.")
            return

        # Confirmation dialog state for excluding an entering batch.
        if "pending_exclude_code" not in st.session_state:
            st.session_state.pending_exclude_code = None
        if "pending_exclude_label" not in st.session_state:
            st.session_state.pending_exclude_label = None

        @st.dialog("Confirmar exclusão do estoque")
        def confirm_exclude_dialog():
            code = st.session_state.pending_exclude_code
            label = st.session_state.pending_exclude_label
            if not code:
                st.write("Nada a excluir.")
                return

            st.warning(
                "Isso remove o lote inteiro do estoque (estoque=0, custo=0, preço=0).\n\n"
                f"{label}"
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "Confirmar exclusão",
                    type="primary",
                    key="confirm_exclude_stock_btn",
                ):
                    reset_batch_pricing_and_exclude(code)
                    st.session_state.pending_exclude_code = None
                    st.session_state.pending_exclude_label = None
                    st.rerun()
            with c2:
                if st.button("Cancelar", key="cancel_exclude_stock_btn"):
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
            frame_color = r["frame_color"] or ""
            lens_color = r["lens_color"] or ""
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
                    "frame_color": frame_color,
                    "lens_color": lens_color,
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
            0.82,
            1.38,
            0.85,
            0.78,
            0.78,
            0.78,
            0.82,
            0.78,
            0.84,
            0.84,
            0.84,
            0.78,
        ]

        # Build header filters (Excel-like column dropdowns).
        header = st.columns(stock_col_w)
        header[0].markdown("**Ação**")

        header[1].markdown("**Nome do produto**")
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

        header[3].markdown("**Cor armação**")
        frame_color_options = sorted(
            {it["frame_color"] for it in items if it["frame_color"] is not None}
        )
        selected_frame_colors = header[3].multiselect(
            label="",
            options=frame_color_options,
            default=[],
            key="stock_filter_frame_color",
        )

        header[4].markdown("**Cor lente**")
        lens_color_options = sorted(
            {it["lens_color"] for it in items if it["lens_color"] is not None}
        )
        selected_lens_colors = header[4].multiselect(
            label="",
            options=lens_color_options,
            default=[],
            key="stock_filter_lens_color",
        )

        header[5].markdown("**Estilo**")
        style_options = sorted({it["style"] for it in items if it["style"] is not None})
        selected_styles = header[5].multiselect(
            label="",
            options=style_options,
            default=[],
            key="stock_filter_style",
        )

        header[6].markdown("**Paleta**")
        palette_options = sorted({it["palette"] for it in items if it["palette"] is not None})
        selected_palettes = header[6].multiselect(
            label="",
            options=palette_options,
            default=[],
            key="stock_filter_palette",
        )

        header[7].markdown("**Gênero**")
        gender_options = sorted({it["gender"] for it in items if it["gender"] is not None})
        selected_genders = header[7].multiselect(
            label="",
            options=gender_options,
            default=[],
            key="stock_filter_gender",
        )

        header[8].markdown("**Custo**")
        cost_options = sorted({it["cost"] for it in items})
        selected_costs = header[8].multiselect(
            label="",
            options=cost_options,
            default=[],
            key="stock_filter_cost",
        )

        header[9].markdown("**Preço de venda**")
        price_options = sorted({it["price"] for it in items})
        selected_prices = header[9].multiselect(
            label="",
            options=price_options,
            default=[],
            key="stock_filter_price",
        )

        header[10].markdown("**Margem**")
        markup_options = sorted({it["markup"] for it in items})
        selected_markups = header[10].multiselect(
            label="",
            options=markup_options,
            default=[],
            key="stock_filter_markup",
        )

        header[11].markdown("**Em estoque**")
        stock_options = sorted({it["stock_qty"] for it in items})
        selected_stocks = header[11].multiselect(
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
            if selected_frame_colors and it["frame_color"] not in selected_frame_colors:
                continue
            if selected_lens_colors and it["lens_color"] not in selected_lens_colors:
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
            st.info("Nenhuma linha corresponde aos filtros atuais.")
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
                    "Excluir",
                    type="secondary",
                    key=f"stock_exclude_{product_id}",
                ):
                    st.session_state.pending_exclude_code = code
                    attr_bits = " · ".join(
                        x
                        for x in (
                            it["frame_color"],
                            it["lens_color"],
                            it["style"],
                            it["palette"],
                            it["gender"],
                        )
                        if x
                    )
                    extra = f" | {attr_bits}" if attr_bits else ""
                    st.session_state.pending_exclude_label = (
                        f"{name}{extra} | SKU: {sku} | Cód.: {code}"
                    )
                    st.rerun()

            row[1].markdown(f"**{name}**")
            row[2].write(sku or "—")
            row[3].write(it["frame_color"] or "—")
            row[4].write(it["lens_color"] or "—")
            row[5].write(it["style"] or "—")
            row[6].write(it["palette"] or "—")
            row[7].write(it["gender"] or "—")
            row[8].write(format_money(cost))
            row[9].write(format_money(price))
            row[10].write(format_money(markup_amount))
            row[11].write(stock_qty)

            totals_cost += cost * stock_qty
            totals_price += price * stock_qty
            totals_markup += markup_amount * stock_qty
            totals_stock += stock_qty

        st.divider()
        total_row = st.columns(stock_col_w)
        with total_row[0]:
            st.write("")
        total_row[1].markdown("**TOTAL GERAL**")
        for _i in range(2, 8):
            total_row[_i].write("")
        total_row[8].write(format_money(totals_cost))
        total_row[9].write(format_money(totals_price))
        total_row[10].write(format_money(totals_markup))
        total_row[11].write(totals_stock)


if __name__ == "__main__":
    main()

