import json
import logging
import math
import os
from pathlib import Path
import urllib.error
import urllib.parse
from urllib import request
from datetime import date, datetime
from typing import Any, Optional, Tuple

from dotenv import load_dotenv

# Carrega .env na raiz do projeto; não sobrescreve variáveis já definidas no ambiente.
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
logging.getLogger(__name__).info(
    "DATABASE_URL detected: %s",
    "yes" if (os.environ.get("DATABASE_URL") or "").strip() else "no",
)

import pandas as pd

from utils.app_auth import (
    ensure_authenticated_or_stop,
    get_audit_session_user,
    get_audit_session_user_id,
    get_session_tenant_id,
    get_session_user_role,
    is_auth_configured,
    logout,
)
from utils.critical_log import log_critical_event
from utils.rbac import is_admin, require_admin, require_operator_or_admin
from utils.formatters import (
    format_money,
    format_product_created_display,
    format_qty_display_4,
)
from utils.validators import (
    attribute_select_index,
    dropdown_with_other,
    filter_customers_by_search,
    normalize_cpf_digits,
    normalize_phone_digits,
    parse_cost_quantity_text,
    parse_cost_unit_price_value,
    resolve_attribute_value,
    sanitize_cep_digits,
    validate_cpf_br,
    validate_email_optional,
)
import psycopg
import streamlit as st

from database.config import get_db_provider
from database.connection import maybe_run_periodic_database_health
from services.db_startup import run_database_init
from services.domain_constants import (
    DUPLICATE_SKU_BASE_ERROR_MSG,
    FILTER_ANY,
    SALE_PAYMENT_OPTIONS,
    SKU_COST_COMPONENT_DEFINITIONS,
)
from services.product_lot_facade import (
    build_product_sku_body,
    hard_delete_sku_catalog,
    product_image_abs_path,
    product_lot_edit_block_reason,
    sku_correction_block_reason,
    update_product_lot_attributes,
    update_product_lot_photo,
)
from services.read_queries import (
    fetch_active_sku_pricing_record,
    fetch_customers_ordered,
    fetch_price_history_for_sku,
    fetch_product_batches_for_sku,
    fetch_product_batches_in_stock_for_sku,
    fetch_product_by_id,
    fetch_product_search_attribute_options,
    fetch_product_triple_label_by_sku,
    fetch_products,
    fetch_recent_stock_cost_entries,
    fetch_skus_available_for_sale,
    fetch_sku_cost_components_for_sku,
    fetch_sku_master_rows,
    fetch_sku_pricing_records_for_sku,
    get_persisted_structured_unit_cost,
    peek_next_customer_code_preview,
    search_products_filtered,
)
from services.sqlite_admin import get_sqlite_db_path
from services.tenant_scope import effective_tenant_id_for_request
from services.uat_checklist_service import (
    UAT_MANUAL_CASES,
    UAT_STATUS_LABELS,
    UAT_STATUS_ORDER,
    fetch_map_for_tenant,
    upsert_uat_record,
)
from utils.audit_backup import (
    maybe_run_periodic_maintenance_backups,
    register_sqlite_full_backup_atexit,
    run_startup_sqlite_full_backup_once,
)
from services.customer_service import (
    delete_customer_row,
    insert_customer_row,
    update_customer_row,
)
from services.product_service import (
    add_product,
    add_stock_receipt,
    apply_manual_stock_write_down,
    apply_stock_receipt,
    clear_batch_pricing_only,
    compute_sku_pricing_targets,
    fetch_product_stock_name_sku,
    generate_product_sku,
    reset_batch_pricing_and_exclude,
    save_sku_cost_structure,
    save_sku_pricing_workflow,
    set_product_pricing,
    set_product_pricing_for_batch,
    update_product_attributes,
    update_sku_selling_price,
)
from services.sales_service import fetch_recent_sales_for_ui, record_sale
from utils.painel_dashboard import render_painel_executivo

_logger = logging.getLogger(__name__)


def test_db_connection():
    """Debug temporário: valida Postgres via DATABASE_URL nos Secrets (Streamlit Cloud)."""
    try:
        conn = psycopg.connect(
            st.secrets["DATABASE_URL"],
            prepare_threshold=0,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_user;", prepare=False)
                result = cur.fetchone()
            return result
        finally:
            conn.close()
    except Exception as e:
        return str(e)


# Navegação (rótulos em português — também usados nos `if page == …`)
PAGE_PRODUTOS = "Produtos"
PAGE_ESTOQUE = "Estoque"
PAGE_CUSTOS = "Custos"
PAGE_PRECIFICACAO = "Precificação"
PAGE_VENDAS = "Vendas"
PAGE_CLIENTES = "Clientes"
PAGE_PAINEL = "Painel"
PAGE_UAT = "Checklist UAT"

# Precificação (fluxo SKU): modo de cada parâmetro na UI
PRICING_MODE_PCT = "Percentual (%)"
PRICING_MODE_ABS = "Valor fixo (R$)"

# Custos — composição de custo: forma de localizar o SKU na UI
COSTING_STRUCT_PICK_SKU = "Por SKU"
COSTING_STRUCT_PICK_NAME = "Por nome do produto"

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


def init_cust_edit_session(r: Any, cid: int) -> None:
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


def _maybe_sidebar_database_export() -> None:
    """
    Quando `allow_database_export` está definido em Streamlit Secrets (ex.: Cloud),
    mostra um botão para descarregar o ficheiro SQLite ativo — só em deploys com ``DB_PROVIDER=sqlite``;
    com PostgreSQL não há ficheiro .db da aplicação.
    """
    if get_db_provider() != "sqlite":
        return
    try:
        allow = st.secrets.get("allow_database_export", False)
    except Exception:
        allow = False
    if isinstance(allow, str):
        allow = allow.strip().lower() in ("1", "true", "yes", "on")
    if not bool(allow):
        return
    db_path = get_sqlite_db_path()
    with st.sidebar.expander("Backup do banco (admin)", expanded=False):
        st.caption(
            "Descarregue o SQLite uma vez e desative o segredo `allow_database_export` no painel do Streamlit."
        )
        if db_path.is_file():
            _db_leaf = db_path.name
            if not is_admin():
                st.caption("Apenas o perfil **administrador** pode descarregar o ficheiro.")
            st.download_button(
                f"Descarregar {_db_leaf}",
                data=db_path.read_bytes(),
                file_name=_db_leaf,
                mime="application/octet-stream",
                key="alieh_export_sqlite_db",
                disabled=not is_admin(),
                help=(
                    "Restrito a administradores."
                    if not is_admin()
                    else "Transferência única do SQLite ativo (tenant atual)."
                ),
            )
        else:
            st.warning("Ficheiro de base de dados não encontrado neste ambiente.")


def _render_uat_manual_checklist_page() -> None:
    """Checklist interactivo UAT (secção A.4); persistência por inquilino na base de dados."""
    require_operator_or_admin()
    st.markdown("### Checklist UAT manual")
    st.caption(
        "Formalização da validação de negócio (relatório UAT, secção A.4). "
        "Grave cada caso após executar o teste na aplicação; os registos ficam na base de dados "
        "do inquilino actual e entram nas exportações de auditoria quando configuradas."
    )
    tid = effective_tenant_id_for_request()
    db_map = fetch_map_for_tenant(tid)

    for code, _title, _desc in UAT_MANUAL_CASES:
        k_s = f"uat_stat_{code}"
        k_n = f"uat_notes_{code}"
        if k_s not in st.session_state:
            row = db_map.get(code)
            raw_st = (row.get("status") if row else None) or "pending"
            st.session_state[k_s] = (
                raw_st if raw_st in UAT_STATUS_ORDER else "pending"
            )
        if k_n not in st.session_state:
            st.session_state[k_n] = (db_map.get(code) or {}).get("notes") or ""

    n_total = len(UAT_MANUAL_CASES)
    n_done = sum(
        1
        for c, _, __ in UAT_MANUAL_CASES
        if st.session_state.get(f"uat_stat_{c}", "pending") != "pending"
    )
    st.progress(
        n_done / n_total if n_total else 0.0,
        text=f"{n_done} de {n_total} casos com resultado registado (não pendente)",
    )

    summary_rows = []
    for code, title, _desc in UAT_MANUAL_CASES:
        row = db_map.get(code)
        bst = str((row or {}).get("status") or "pending")
        summary_rows.append(
            {
                "ID": code,
                "Caso": title,
                "Estado (último gravado na BD)": UAT_STATUS_LABELS.get(bst, bst),
                "Data/hora registo": (row or {}).get("result_recorded_at") or "—",
                "Actualizado (BD)": (row or {}).get("updated_at") or "—",
                "Utilizador": (row or {}).get("recorded_by_username") or "—",
                "Perfil": (row or {}).get("recorded_by_role") or "—",
            }
        )
    st.dataframe(summary_rows, width="stretch", hide_index=True)

    st.divider()
    for code, title, desc in UAT_MANUAL_CASES:
        row = db_map.get(code)
        with st.expander(f"{code} — {title}", expanded=False):
            st.markdown(desc)
            st.selectbox(
                "Resultado",
                options=list(UAT_STATUS_ORDER),
                format_func=lambda x: UAT_STATUS_LABELS[x],
                key=f"uat_stat_{code}",
            )
            st.text_area("Notas (opcional)", key=f"uat_notes_{code}", height=72)
            c1, c2 = st.columns([1, 2])
            with c1:
                save = st.button("Gravar resultado", type="primary", key=f"uat_save_{code}")
            with c2:
                if row and (row.get("result_recorded_at") or row.get("updated_at")):
                    st.caption(
                        "Último registo gravado: **"
                        f"{(row.get('result_recorded_at') or row.get('updated_at') or '—')}"
                        "** — utilizador **"
                        f"{(row.get('recorded_by_username') or '—')}**"
                    )
            if save:
                status = st.session_state.get(f"uat_stat_{code}", "pending")
                notes = str(st.session_state.get(f"uat_notes_{code}", "") or "")
                upsert_uat_record(
                    tid,
                    code,
                    status,
                    notes,
                    username=get_audit_session_user(),
                    user_id=get_audit_session_user_id(),
                    role=(get_session_user_role() or "—"),
                )
                log_critical_event(
                    "UAT_MANUAL_CHECKLIST_SAVE",
                    test_id=code,
                    status=status,
                )
                st.success(f"**{code}** gravado na base de dados.")
                st.rerun()


def main():
    st.set_page_config(page_title="ALIEH — Gestão", layout="wide")
    st.subheader("DB Connection Debug")
    result = test_db_connection()
    st.write(result)
    run_database_init()
    register_sqlite_full_backup_atexit()
    run_startup_sqlite_full_backup_once()
    maybe_run_periodic_maintenance_backups()
    maybe_run_periodic_database_health()
    ensure_authenticated_or_stop()

    # Shell + tipografia. O primeiro caractere do markdown deve ser «<» — indentação à esquerda
    # no `st.markdown` vira bloco de código e o CSS aparece como texto na página.
    st.markdown(
        """<style>
@import url("https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,300;0,400;0,500;0,600;0,700&display=swap");
/* Tipografia ALIEH: sans-serif única em toda a app (sidebar, painel e páginas). */
:root {
  --alieh-font-ui: "Montserrat", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
html, body,
.stApp,
section.main,
[data-testid="stMain"],
[data-testid="stMain"] .block-container {
  font-family: var(--alieh-font-ui) !important;
}
section.main h1, section.main h2,
[data-testid="stMain"] h1,
[data-testid="stMain"] h2 {
  font-family: var(--alieh-font-ui) !important;
  font-weight: 700 !important;
  letter-spacing: -0.02em !important;
  line-height: 1.2 !important;
}
section.main h3, section.main h4, section.main h5, section.main h6,
[data-testid="stMain"] h3,
[data-testid="stMain"] h4,
[data-testid="stMain"] h5,
[data-testid="stMain"] h6 {
  font-family: var(--alieh-font-ui) !important;
  font-weight: 600 !important;
  letter-spacing: -0.015em !important;
  line-height: 1.3 !important;
}
section[data-testid="stSidebar"] {
  font-family: var(--alieh-font-ui) !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
  font-family: var(--alieh-font-ui) !important;
  letter-spacing: 0.02em !important;
}
.stButton > button,
.stDownloadButton > button,
[data-testid="baseButton-secondary"],
[data-testid="baseButton-primary"] {
  font-family: var(--alieh-font-ui) !important;
  font-weight: 600 !important;
  letter-spacing: 0.05em !important;
  text-transform: none !important;
}
[data-testid="stAppViewContainer"] {
  width: 100% !important;
  max-width: 100vw !important;
  box-sizing: border-box !important;
}
[data-testid="stAppViewContainer"] > div {
  width: 100% !important;
  max-width: 100% !important;
}
[data-testid="stAppViewContainer"] > div:has(> section[data-testid="stSidebar"]) {
  display: flex !important;
  flex-direction: row !important;
  align-items: stretch !important;
  width: 100% !important;
  min-width: 0 !important;
  flex: 1 1 auto !important;
}
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
section[data-testid="stSidebar"][aria-expanded="false"] {
  flex: 0 0 0 !important;
  width: 0 !important;
  min-width: 0 !important;
  max-width: 0 !important;
  overflow: visible !important;
  border: none !important;
  padding: 0 !important;
}
section.main,
[data-testid="stMain"] {
  flex: 1 1 0% !important;
  min-width: 0 !important;
  width: 100% !important;
  max-width: 100% !important;
  margin-left: 0 !important;
  box-sizing: border-box !important;
}
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
</style>""",
        unsafe_allow_html=True,
    )

    st.title("ALIEH — Gestão comercial")
    st.caption(
        "Produtos, custos, precificação, estoque, clientes, vendas e painel (banco SQLite local)."
    )

    if is_auth_configured() and st.sidebar.button("Sair", key="alieh_logout_btn"):
        logout()
        st.rerun()

    if is_auth_configured():
        st.sidebar.caption(f"Inquilino: `{get_session_tenant_id()}`")

    page = st.sidebar.radio(
        "Navegação",
        [
            PAGE_PAINEL,
            PAGE_PRODUTOS,
            PAGE_CUSTOS,
            PAGE_PRECIFICACAO,
            PAGE_ESTOQUE,
            PAGE_CLIENTES,
            PAGE_VENDAS,
            PAGE_UAT,
        ],
        index=0,
    )
    _maybe_sidebar_database_export()

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
                # Reset do detalhe deve ocorrer *antes* do selectbox (Streamlit proíbe alterar a key após o widget).
                if st.session_state.pop("_reset_sku_search_product_focus", False):
                    st.session_state["sku_search_product_focus"] = "—"
                _sku_del_ok = st.session_state.pop("_sku_deleted_ok_msg", None)
                if _sku_del_ok:
                    st.success(_sku_del_ok)
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
                            _pic_col, _det_col = st.columns([1, 1])
                            with _pic_col:
                                _abs_img = product_image_abs_path(pr["product_image_path"])
                                if _abs_img is not None:
                                    st.image(
                                        str(_abs_img),
                                        caption="Foto do produto",
                                        use_container_width=True,
                                    )
                                else:
                                    st.caption("Sem foto cadastrada.")
                            with _det_col:
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

                            lot_edit_block = product_lot_edit_block_reason(focus_id)
                            with st.expander("Editar produto", expanded=False):
                                st.markdown("##### Foto do produto")
                                st.caption(
                                    "A foto pode ser **substituída a qualquer momento**, mesmo com "
                                    "estoque, custo, preço ou vendas."
                                )
                                st.file_uploader(
                                    "Nova imagem (JPG, PNG ou WebP)",
                                    type=["jpg", "jpeg", "png", "webp"],
                                    accept_multiple_files=False,
                                    key=f"prod_edit_photo_{focus_id}",
                                    disabled=not is_admin(),
                                )
                                if st.button(
                                    "Gravar nova foto",
                                    key=f"prod_edit_photo_btn_{focus_id}",
                                    disabled=not is_admin(),
                                    help="Apenas administradores." if not is_admin() else None,
                                ):
                                    require_admin()
                                    _uf = st.session_state.get(f"prod_edit_photo_{focus_id}")
                                    if _uf is None:
                                        st.error("Selecione um ficheiro.")
                                    else:
                                        try:
                                            update_product_lot_photo(
                                                focus_id,
                                                _uf.getvalue(),
                                                getattr(_uf, "name", None) or "foto.jpg",
                                            )
                                        except ValueError as _e:
                                            st.error(str(_e))
                                        else:
                                            st.success("Foto atualizada.")
                                            st.rerun()

                                st.divider()
                                st.markdown("##### Nome, data e atributos")
                                if lot_edit_block:
                                    st.info(lot_edit_block)
                                else:
                                    frame_opts_e = list(
                                        dropdown_with_other(PRODUCT_FRAME_COLOR_OPTIONS)
                                    )
                                    lens_opts_e = list(
                                        dropdown_with_other(PRODUCT_LENS_COLOR_OPTIONS)
                                    )
                                    palette_opts_e = list(
                                        dropdown_with_other(PRODUCT_PALETTE_OPTIONS)
                                    )
                                    gender_opts_e = list(
                                        dropdown_with_other(PRODUCT_GENDER_OPTIONS)
                                    )
                                    style_opts_e = list(
                                        dropdown_with_other(PRODUCT_STYLE_OPTIONS)
                                    )
                                    for _opts, _col in (
                                        (frame_opts_e, pr["frame_color"]),
                                        (lens_opts_e, pr["lens_color"]),
                                        (palette_opts_e, pr["palette"]),
                                        (gender_opts_e, pr["gender"]),
                                        (style_opts_e, pr["style"]),
                                    ):
                                        _vv = (_col or "").strip()
                                        if _vv and _vv not in _opts:
                                            _opts.insert(0, _vv)

                                    if st.session_state.get("prod_edit_init_id") != focus_id:
                                        st.session_state["prod_edit_init_id"] = focus_id
                                        try:
                                            _erd = datetime.fromisoformat(
                                                str(pr["registered_date"]).split("T")[0][:10]
                                            ).date()
                                        except (ValueError, TypeError):
                                            _erd = date.today()
                                        st.session_state[f"prod_edit_name_{focus_id}"] = (
                                            pr["name"] or ""
                                        )
                                        st.session_state[f"prod_edit_date_{focus_id}"] = _erd

                                        def _pick_edit_opt(val, opts):
                                            v = (val or "").strip()
                                            if v and v in opts:
                                                return v
                                            return opts[0] if opts else ""

                                        st.session_state[f"prod_edit_frame_{focus_id}"] = (
                                            _pick_edit_opt(pr["frame_color"], frame_opts_e)
                                        )
                                        st.session_state[f"prod_edit_lens_{focus_id}"] = (
                                            _pick_edit_opt(pr["lens_color"], lens_opts_e)
                                        )
                                        st.session_state[f"prod_edit_pal_{focus_id}"] = (
                                            _pick_edit_opt(pr["palette"], palette_opts_e)
                                        )
                                        st.session_state[f"prod_edit_gen_{focus_id}"] = (
                                            _pick_edit_opt(pr["gender"], gender_opts_e)
                                        )
                                        st.session_state[f"prod_edit_sty_{focus_id}"] = (
                                            _pick_edit_opt(pr["style"], style_opts_e)
                                        )

                                    with st.form(f"prod_edit_lot_form_{focus_id}"):
                                        st.text_input(
                                            "Nome do produto",
                                            key=f"prod_edit_name_{focus_id}",
                                        )
                                        st.date_input(
                                            "Data de registro",
                                            key=f"prod_edit_date_{focus_id}",
                                        )
                                        st.selectbox(
                                            "Cor da armação",
                                            options=frame_opts_e,
                                            key=f"prod_edit_frame_{focus_id}",
                                        )
                                        st.selectbox(
                                            "Cor da lente",
                                            options=lens_opts_e,
                                            key=f"prod_edit_lens_{focus_id}",
                                        )
                                        st.selectbox(
                                            "Paleta",
                                            options=palette_opts_e,
                                            key=f"prod_edit_pal_{focus_id}",
                                        )
                                        st.selectbox(
                                            "Gênero",
                                            options=gender_opts_e,
                                            key=f"prod_edit_gen_{focus_id}",
                                        )
                                        st.selectbox(
                                            "Estilo",
                                            options=style_opts_e,
                                            key=f"prod_edit_sty_{focus_id}",
                                        )
                                        _save_lot = st.form_submit_button(
                                            "Salvar alterações nos dados do lote",
                                            disabled=not is_admin(),
                                        )
                                    if _save_lot:
                                        require_admin()
                                        _nm = (
                                            st.session_state.get(
                                                f"prod_edit_name_{focus_id}", ""
                                            )
                                            or ""
                                        ).strip()
                                        if not _nm:
                                            st.error("O nome é obrigatório.")
                                        else:
                                            try:
                                                update_product_lot_attributes(
                                                    focus_id,
                                                    name=_nm,
                                                    registered_date=st.session_state[
                                                        f"prod_edit_date_{focus_id}"
                                                    ],
                                                    frame_color=st.session_state[
                                                        f"prod_edit_frame_{focus_id}"
                                                    ],
                                                    lens_color=st.session_state[
                                                        f"prod_edit_lens_{focus_id}"
                                                    ],
                                                    style=st.session_state[
                                                        f"prod_edit_sty_{focus_id}"
                                                    ],
                                                    palette=st.session_state[
                                                        f"prod_edit_pal_{focus_id}"
                                                    ],
                                                    gender=st.session_state[
                                                        f"prod_edit_gen_{focus_id}"
                                                    ],
                                                )
                                            except ValueError as _e:
                                                st.error(str(_e))
                                            else:
                                                st.success(
                                                    "Dados do lote atualizados (e SKU ajustado, se necessário)."
                                                )
                                                st.session_state.pop(
                                                    "prod_edit_init_id", None
                                                )
                                                st.rerun()

                            sku_key = (pr["sku"] or "").strip()
                            block = (
                                sku_correction_block_reason(sku_key)
                                if sku_key
                                else "SKU inválido."
                            )
                            if block:
                                st.info(block)
                            else:
                                st.caption(
                                    "Sem estoque, custos, preços ou vendas para este SKU — "
                                    "pode **excluir definitivamente** o cadastro (irreversível)."
                                )

                            delete_disabled = bool(block) or not is_admin()
                            if st.button(
                                "Excluir SKU",
                                key=f"prod_sku_delete_{focus_id}",
                                disabled=delete_disabled,
                                help="Apaga do banco todos os lotes e o mestre deste SKU (se liberado).",
                            ):
                                st.session_state[f"prod_sku_del_confirm_{focus_id}"] = True

                            if st.session_state.get(f"prod_sku_del_confirm_{focus_id}"):
                                st.warning(
                                    "Confirma a **exclusão permanente** de **todos os lotes** e do **mestre** "
                                    "deste SKU no banco de dados? Não há como desfazer pelo aplicativo."
                                )
                                d1, d2 = st.columns(2)
                                with d1:
                                    if st.button(
                                        "Sim, excluir SKU",
                                        key=f"prod_sku_del_yes_{focus_id}",
                                        type="primary",
                                    ):
                                        require_admin()
                                        try:
                                            hard_delete_sku_catalog(sku_key)
                                        except ValueError as exc:
                                            st.error(str(exc))
                                        else:
                                            st.session_state[
                                                "_reset_sku_search_product_focus"
                                            ] = True
                                            st.session_state["_sku_deleted_ok_msg"] = (
                                                "SKU, lotes e mestre foram excluídos do sistema."
                                            )
                                            st.session_state.pop(
                                                f"prod_sku_del_confirm_{focus_id}", None
                                            )
                                            st.rerun()
                                with d2:
                                    if st.button(
                                        "Cancelar",
                                        key=f"prod_sku_del_no_{focus_id}",
                                    ):
                                        st.session_state.pop(
                                            f"prod_sku_del_confirm_{focus_id}", None
                                        )
                                        st.rerun()
                    else:
                        st.warning(
                            "Produto não encontrado ou excluído. Atualize a busca e selecione de novo."
                        )

        st.markdown("### Cadastro de produto")
        st.caption(
            "Cadastre apenas **novos lotes** (identidade + atributos; **foto opcional**). Exclusão de estoque é feita em **Estoque**. "
            "Não é possível cadastrar de novo o mesmo **nome + data + atributos** nem um lote com o **mesmo SKU** "
            "(corpo idêntico, ignorando o número sequencial do início). "
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

        st.file_uploader(
            "Foto do produto (opcional)",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=False,
            key="prod_reg_photo",
            help="JPG, PNG ou WebP. Máximo 8 MB. Aparece no detalhe da busca por SKU e lote.",
        )

        preview_sku = _maybe_preview_product_sku()
        if preview_sku:
            st.info(f"**SKU gerado (somente leitura):** `{preview_sku}`")
        else:
            st.caption(
                "Selecione todos os atributos para visualizar o SKU. Ele não pode ser editado manualmente."
            )

        if st.button(
            "Cadastrar produto",
            type="primary",
            key="prod_reg_submit",
            disabled=not is_admin(),
            help="Apenas administradores." if not is_admin() else None,
        ):
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
                    require_admin()
                    try:
                        _photo = st.session_state.get("prod_reg_photo")
                        _img_bytes: Optional[bytes] = None
                        _img_fn = ""
                        if _photo is not None:
                            _img_bytes = _photo.getvalue()
                            _img_fn = getattr(_photo, "name", None) or "foto.jpg"
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
                            product_image_bytes=_img_bytes,
                            product_image_filename=_img_fn,
                        )
                    except ValueError as e:
                        if str(e) == DUPLICATE_SKU_BASE_ERROR_MSG:
                            st.error(DUPLICATE_SKU_BASE_ERROR_MSG)
                        else:
                            st.error(f"Não foi possível cadastrar o produto: {e}")
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
                            "prod_reg_photo",
                        ):
                            st.session_state.pop(k, None)
                        st.rerun()

    elif page == PAGE_VENDAS:
        st.markdown("### Vendas")
        st.caption(
            "Fluxo: **1) SKU** → **2) Cliente** → **3) Quantidade** → **4) Desconto** → **5) Forma de pagamento** "
            "→ **Confirmar**. Cada venda gera um **ID de venda** (#####V). O estoque sai do **lote** selecionado."
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
                pr = fetch_product_stock_name_sku(int(product_id))
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

        # --- Etapa 5 — forma de pagamento ---
        st.markdown("#### Etapa 5 — Forma de pagamento")
        payment_method = st.selectbox(
            "Forma de pagamento",
            options=list(SALE_PAYMENT_OPTIONS),
            key="sales_payment_method",
        )

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
                    "Forma de pagamento": payment_method,
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
                require_operator_or_admin()
                try:
                    code, total = record_sale(
                        product_id=int(product_id),
                        quantity=int(quantity),
                        customer_id=int(cust_id),
                        discount_amount=float(discount_amount),
                        payment_method=str(payment_method),
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
        recent = fetch_recent_sales_for_ui(limit=20)

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
                    "Pagamento": (r["payment_method"] or "").strip() or "—",
                    "Data/Hora": r["sold_at"],
                }
                for r in recent
            ]
            st.dataframe(data, width="stretch", hide_index=True)

    elif page == PAGE_PAINEL:
        render_painel_executivo()

    elif page == PAGE_UAT:
        _render_uat_manual_checklist_page()

    elif page == PAGE_CUSTOS:
        st.markdown("### Custos")

        st.caption(
            "**Composição de custo do SKU**: custos planejados (preço unitário × quantidade), gravados por SKU. "
            "**Custo médio ponderado (CMP)** atualiza só com **entradas de estoque**; vendas não alteram o CMP. "
            "**Preço de venda** fica em **Precificação**."
        )

        sku_rows = fetch_sku_master_rows()
        sku_list = [r["sku"] for r in sku_rows] if sku_rows else []

        costing_struct_name_label_by_sku = (
            fetch_product_triple_label_by_sku() if sku_list else {}
        )

        st.markdown("#### Composição de custo do SKU (componentes planejados)")
        if not sku_list:
            st.info(
                "Ainda não há SKUs no cadastro mestre. Cadastre um produto em **Produtos** e inclua estoque "
                "(ou confira o `sku_master`) para usar a composição de custo."
            )
        else:
            st.radio(
                "Localizar produto",
                (COSTING_STRUCT_PICK_SKU, COSTING_STRUCT_PICK_NAME),
                horizontal=True,
                key="costing_struct_pick_mode",
            )
            pick_mode = st.session_state.get(
                "costing_struct_pick_mode", COSTING_STRUCT_PICK_SKU
            )
            if pick_mode == COSTING_STRUCT_PICK_SKU:
                sel_sku = st.selectbox(
                    "SKU para composição de custo",
                    options=sku_list,
                    key="costing_struct_sku_select",
                )
            else:
                base_labels: list[tuple[str, str]] = []
                for sku_val in sku_list:
                    s = str(sku_val).strip()
                    bl = costing_struct_name_label_by_sku.get(s, "— — —")
                    base_labels.append((bl, s))
                dup_count: dict[str, int] = {}
                for bl, _s in base_labels:
                    dup_count[bl] = dup_count.get(bl, 0) + 1
                name_pairs: list[tuple[str, str]] = []
                for bl, s in base_labels:
                    disp = f"{bl} — [{s}]" if dup_count.get(bl, 0) > 1 else bl
                    name_pairs.append((disp, s))
                name_pairs.sort(key=lambda t: (t[0].lower(), t[1]))
                name_labels = [p[0] for p in name_pairs]
                chosen_label = st.selectbox(
                    "Nome — cor da armação — cor da lente",
                    options=name_labels,
                    key="costing_struct_name_select",
                )
                sel_sku = name_pairs[name_labels.index(chosen_label)][1]

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

            if st.button(
                "Salvar composição de custo",
                type="primary",
                key="costing_struct_save",
                disabled=not is_admin(),
                help="Apenas administradores." if not is_admin() else None,
            ):
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
                    require_admin()
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
            "**Etapa 1** — Localize o produto **por SKU** ou **por nome** (igual à composição de custo); carrega componentes salvos. "
            "**Etapa 2** — Lote que recebe a mercadoria. "
            "**Etapa 3** — Quantidade a adicionar (> 0, até 4 decimais). **Etapa 4** — Custo unitário = **total** "
            "da composição salva acima. **Etapa 5** — Confirme o resumo e finalize — o **CMP** atualiza pela média ponderada."
        )

        if not sku_list:
            st.info("Nenhum SKU disponível para entrada de estoque.")
        else:
            st.markdown("##### Etapa 1 — Localizar produto")
            st.radio(
                "Localizar produto",
                (COSTING_STRUCT_PICK_SKU, COSTING_STRUCT_PICK_NAME),
                horizontal=True,
                key="costing_stock_entry_pick_mode",
            )
            pick_mode_se = st.session_state.get(
                "costing_stock_entry_pick_mode", COSTING_STRUCT_PICK_SKU
            )
            if pick_mode_se == COSTING_STRUCT_PICK_SKU:
                stock_entry_sku = st.selectbox(
                    "SKU",
                    options=sku_list,
                    key="costing_stock_entry_sku",
                )
            else:
                base_labels_se: list[tuple[str, str]] = []
                for sku_val in sku_list:
                    s = str(sku_val).strip()
                    bl = costing_struct_name_label_by_sku.get(s, "— — —")
                    base_labels_se.append((bl, s))
                dup_count_se: dict[str, int] = {}
                for bl, _s in base_labels_se:
                    dup_count_se[bl] = dup_count_se.get(bl, 0) + 1
                name_pairs_se: list[tuple[str, str]] = []
                for bl, s in base_labels_se:
                    disp = f"{bl} — [{s}]" if dup_count_se.get(bl, 0) > 1 else bl
                    name_pairs_se.append((disp, s))
                name_pairs_se.sort(key=lambda t: (t[0].lower(), t[1]))
                name_labels_se = [p[0] for p in name_pairs_se]
                chosen_label_se = st.selectbox(
                    "Nome — cor da armação — cor da lente",
                    options=name_labels_se,
                    key="costing_stock_entry_name_select",
                )
                stock_entry_sku = name_pairs_se[name_labels_se.index(chosen_label_se)][
                    1
                ]

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
                    disabled=(not can_finalize) or (not is_admin()),
                    help="Apenas administradores." if not is_admin() else None,
                ):
                    require_admin()
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
        require_admin()
        st.markdown("### Precificação (por SKU)")

        st.caption(
            "**Etapa 1** — Localize o produto **por SKU** ou **por nome** (mesmo padrão de **Custos**); **custo base** = **CMP** atual. "
            "**Etapa 2** — Margem, impostos e encargos: **percentual (%)** ou **valor fixo em R$** (≥ 0). "
            "**Etapa 3** — Revise os preços calculados. **Etapa 4** — Salvar cria um **novo** registro. "
            "O registro **ativo** é o último salvo; **Vendas** usa o **preço alvo** dele."
        )

        sku_rows = fetch_sku_master_rows()
        if not sku_rows:
            st.info("Ainda não há SKUs. Cadastre produtos em **Produtos** primeiro.")
            return

        sku_list = [r["sku"] for r in sku_rows]
        name_label_by_sku = fetch_product_triple_label_by_sku()

        st.markdown("#### Etapa 1 — Localizar produto")
        st.radio(
            "Localizar produto",
            (COSTING_STRUCT_PICK_SKU, COSTING_STRUCT_PICK_NAME),
            horizontal=True,
            key="pricing_pick_mode",
        )
        pick_mode = st.session_state.get("pricing_pick_mode", COSTING_STRUCT_PICK_SKU)
        if pick_mode == COSTING_STRUCT_PICK_SKU:
            sel_sku = st.selectbox(
                "SKU",
                options=sku_list,
                key="pricing_sku_select",
            )
        else:
            base_labels: list[tuple[str, str]] = []
            for sku_val in sku_list:
                s = str(sku_val).strip()
                bl = name_label_by_sku.get(s, "— — —")
                base_labels.append((bl, s))
            dup_count: dict[str, int] = {}
            for bl, _s in base_labels:
                dup_count[bl] = dup_count.get(bl, 0) + 1
            name_pairs: list[tuple[str, str]] = []
            for bl, s in base_labels:
                disp = f"{bl} — [{s}]" if dup_count.get(bl, 0) > 1 else bl
                name_pairs.append((disp, s))
            name_pairs.sort(key=lambda t: (t[0].lower(), t[1]))
            name_labels = [p[0] for p in name_pairs]
            chosen_label = st.selectbox(
                "Nome — cor da armação — cor da lente",
                options=name_labels,
                key="pricing_name_select",
            )
            sel_sku = name_pairs[name_labels.index(chosen_label)][1]

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
                st.session_state["pricing_wf_markup_mode"] = (
                    PRICING_MODE_ABS
                    if int(active_row["markup_kind"] or 0) == 1
                    else PRICING_MODE_PCT
                )
                st.session_state["pricing_wf_taxes_mode"] = (
                    PRICING_MODE_ABS
                    if int(active_row["taxes_kind"] or 0) == 1
                    else PRICING_MODE_PCT
                )
                st.session_state["pricing_wf_interest_mode"] = (
                    PRICING_MODE_ABS
                    if int(active_row["interest_kind"] or 0) == 1
                    else PRICING_MODE_PCT
                )
            else:
                st.session_state["pricing_wf_markup"] = 0.0
                st.session_state["pricing_wf_taxes"] = 0.0
                st.session_state["pricing_wf_interest"] = 0.0
                st.session_state["pricing_wf_markup_mode"] = PRICING_MODE_PCT
                st.session_state["pricing_wf_taxes_mode"] = PRICING_MODE_PCT
                st.session_state["pricing_wf_interest_mode"] = PRICING_MODE_PCT

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

        st.markdown("#### Etapa 2 — Parâmetros de preço")
        st.caption(
            "Em **%**, o valor incide sobre a base indicada em cada linha. Em **R$**, soma-se um valor fixo "
            "(margem sobre o CMP; impostos sobre o preço pré-impostos; encargos sobre o preço com impostos)."
        )
        pc1, pc2, pc3 = st.columns(3)
        with pc1:
            st.radio(
                "Margem — modo",
                (PRICING_MODE_PCT, PRICING_MODE_ABS),
                horizontal=True,
                key="pricing_wf_markup_mode",
            )
            m_is_abs = (
                st.session_state.get("pricing_wf_markup_mode", PRICING_MODE_PCT) == PRICING_MODE_ABS
            )
            markup_pct = st.number_input(
                "Margem em R$" if m_is_abs else "Margem em %",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="pricing_wf_markup",
            )
        with pc2:
            st.radio(
                "Impostos — modo",
                (PRICING_MODE_PCT, PRICING_MODE_ABS),
                horizontal=True,
                key="pricing_wf_taxes_mode",
            )
            t_is_abs = (
                st.session_state.get("pricing_wf_taxes_mode", PRICING_MODE_PCT) == PRICING_MODE_ABS
            )
            taxes_pct = st.number_input(
                "Impostos em R$" if t_is_abs else "Impostos em %",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="pricing_wf_taxes",
            )
        with pc3:
            st.radio(
                "Encargos / juros — modo",
                (PRICING_MODE_PCT, PRICING_MODE_ABS),
                horizontal=True,
                key="pricing_wf_interest_mode",
            )
            i_is_abs = (
                st.session_state.get("pricing_wf_interest_mode", PRICING_MODE_PCT)
                == PRICING_MODE_ABS
            )
            interest_pct = st.number_input(
                "Encargos / juros em R$" if i_is_abs else "Encargos / juros em %",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="pricing_wf_interest",
            )

        m_abs = (
            st.session_state.get("pricing_wf_markup_mode", PRICING_MODE_PCT) == PRICING_MODE_ABS
        )
        t_abs = (
            st.session_state.get("pricing_wf_taxes_mode", PRICING_MODE_PCT) == PRICING_MODE_ABS
        )
        i_abs = (
            st.session_state.get("pricing_wf_interest_mode", PRICING_MODE_PCT) == PRICING_MODE_ABS
        )

        st.markdown("#### Etapa 3 — Preços calculados")
        if avg_cost > 0:
            pb, pwt, tgt = compute_sku_pricing_targets(
                avg_cost,
                float(markup_pct),
                float(taxes_pct),
                float(interest_pct),
                markup_absolute=m_abs,
                taxes_absolute=t_abs,
                interest_absolute=i_abs,
            )
            st.caption(
                "1) **Pré-impostos** = CMP + margem (% sobre CMP **ou** +R$). "
                "2) **Com impostos** = (1) + impostos (% sobre (1) **ou** +R$). "
                "3) **Alvo** = (2) + encargos (% sobre (2) **ou** +R$)."
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
            require_admin()
            try:
                save_sku_pricing_workflow(
                    sel_sku,
                    float(markup_pct),
                    float(taxes_pct),
                    float(interest_pct),
                    markup_kind=1 if m_abs else 0,
                    taxes_kind=1 if t_abs else 0,
                    interest_kind=1 if i_abs else 0,
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
                    "Margem": (
                        format_money(float(r["markup_pct"]))
                        if int(r["markup_kind"] or 0) == 1
                        else f"{float(r['markup_pct']):.2f}%"
                    ),
                    "Impostos": (
                        format_money(float(r["taxes_pct"]))
                        if int(r["taxes_kind"] or 0) == 1
                        else f"{float(r['taxes_pct']):.2f}%"
                    ),
                    "Encargos": (
                        format_money(float(r["interest_pct"]))
                        if int(r["interest_kind"] or 0) == 1
                        else f"{float(r['interest_pct']):.2f}%"
                    ),
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
            "**Salvar cliente** grava na tabela **`customers`** na base de dados. "
            "O **código do cliente** é gerado pelo banco — não preencha no formulário."
        )

        tab_reg, tab_edit = st.tabs(["Cadastrar", "Editar cliente"])
        customers_page_rows = fetch_customers_ordered()

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
                            require_operator_or_admin()
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
            all_cust = customers_page_rows
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
            _cust_del_msg = st.session_state.pop("_cust_deleted_ok", None)
            if _cust_del_msg:
                st.success(_cust_del_msg)
            rows_edit = customers_page_rows
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
                                require_operator_or_admin()
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

                st.divider()
                st.markdown("##### Excluir cadastro")
                st.caption(
                    "Remove o cliente **definitivamente** do banco. "
                    "Não é permitido se já existir **venda** vinculada a ele."
                )
                if st.button(
                    "Excluir cliente permanentemente",
                    type="secondary",
                    key=f"cust_del_open_{cid}",
                ):
                    st.session_state[f"cust_del_confirm_{cid}"] = True
                if st.session_state.get(f"cust_del_confirm_{cid}"):
                    st.warning(
                        f"Confirma a exclusão **permanente** do cliente **{cc} — {row['name']}**? "
                        "Esta ação não pode ser desfeita."
                    )
                    dc1, dc2 = st.columns(2)
                    with dc1:
                        if st.button(
                            "Sim, excluir definitivamente",
                            type="primary",
                            key=f"cust_del_yes_{cid}",
                        ):
                            require_admin()
                            try:
                                delete_customer_row(cid)
                            except ValueError as e:
                                st.error(str(e))
                                st.session_state.pop(f"cust_del_confirm_{cid}", None)
                            else:
                                for k in list(st.session_state.keys()):
                                    if k.endswith(f"_{cid}") and k.startswith(
                                        "cust_edit_"
                                    ):
                                        st.session_state.pop(k, None)
                                st.session_state.pop(f"cust_del_confirm_{cid}", None)
                                st.session_state.pop("cust_edit_pick_id", None)
                                st.session_state.pop("cust_edit_sel", None)
                                st.session_state["_cust_deleted_ok"] = (
                                    f"Cliente **{cc}** excluído do sistema."
                                )
                                st.rerun()
                    with dc2:
                        if st.button(
                            "Cancelar",
                            key=f"cust_del_no_{cid}",
                        ):
                            st.session_state.pop(f"cust_del_confirm_{cid}", None)
                            st.rerun()

    elif page == PAGE_ESTOQUE:
        require_admin()
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
                    require_admin()
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
            stock_val = float(r["stock"] or 0)
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
                    "stock_val": stock_val,
                }
            )

        if "stock_baixa_form_nonce" not in st.session_state:
            st.session_state.stock_baixa_form_nonce = 0
        _baixa_confirm_key = (
            f"stock_baixa_confirm_checkbox_{st.session_state.stock_baixa_form_nonce}"
        )
        with st.expander("Baixa manual de estoque", expanded=False):
            st.caption(
                "Reduz apenas a quantidade em stock do **lote** selecionado. "
                "Não altera custo, preço de venda nem regista venda no histórico; o total "
                "por SKU no mestre é actualizado para refletir a soma dos lotes."
            )

            def _stock_baixa_nome_produto_antes_sku(it: dict) -> str:
                """Nome do produto + cores (por lote), no mesmo espírito do rótulo triplo da app."""
                nome = (it.get("name") or "").strip() or "—"
                fc = (it.get("frame_color") or "").strip()
                lc = (it.get("lens_color") or "").strip()
                partes: list[str] = [nome]
                if fc:
                    partes.append(fc)
                if lc:
                    partes.append(lc)
                return " — ".join(partes)

            _baixa_opts = sorted(
                items,
                key=lambda x: (
                    (x.get("name") or "").lower(),
                    x.get("sku") or "",
                    x["product_id"],
                ),
            )
            _baixa_labels = [
                (
                    f"#{it['product_id']} — {_stock_baixa_nome_produto_antes_sku(it)} — "
                    f"SKU {it['sku'] or '—'} — Lote {it['code'] or '—'} — em stock: "
                    f"{format_qty_display_4(float(it['stock_qty']))}"
                )
                for it in _baixa_opts
            ]
            _baixa_label_to_pid = dict(
                zip(_baixa_labels, [it["product_id"] for it in _baixa_opts])
            )
            _sel_baixa = st.selectbox(
                "Produto (lote com stock)",
                options=_baixa_labels,
                key="stock_manual_baixa_select",
            )
            _pid_baixa = _baixa_label_to_pid[_sel_baixa]
            _max_baixa = float(
                next(
                    (r["stock"] or 0)
                    for r in in_stock_products
                    if int(r["id"]) == int(_pid_baixa)
                )
            )
            _default_baixa = min(1.0, _max_baixa) if _max_baixa > 0 else 0.0
            _qty_baixa = st.number_input(
                "Quantidade a dar baixa",
                min_value=0.0,
                max_value=_max_baixa,
                value=float(_default_baixa),
                step=0.0001,
                format="%.4f",
                key="stock_manual_baixa_qty",
            )
            st.warning(
                "Esta operação é irreversível pelo próprio formulário "
                "(excepto nova entrada de stock em **Custos**). "
                "Confirme o lote e a quantidade antes de continuar."
            )
            st.checkbox(
                "Confirmo a baixa de estoque neste lote e quantidade.",
                key=_baixa_confirm_key,
            )
            if st.button(
                "Aplicar baixa de estoque",
                type="primary",
                key="stock_manual_baixa_aplicar",
            ):
                if not bool(st.session_state.get(_baixa_confirm_key)):
                    st.error("Marque a confirmação antes de aplicar a baixa.")
                elif _qty_baixa <= 0:
                    st.error("Indique uma quantidade maior que zero.")
                elif _qty_baixa > _max_baixa + 1e-9:
                    st.error("Quantidade superior ao stock disponível neste lote.")
                else:
                    try:
                        _novo = apply_manual_stock_write_down(
                            _pid_baixa,
                            float(_qty_baixa),
                            user_id=get_audit_session_user_id(),
                            tenant_id=effective_tenant_id_for_request(),
                        )
                    except ValueError as e:
                        st.error(str(e))
                    else:
                        st.success(
                            "Baixa aplicada. Stock restante deste lote: "
                            f"**{format_qty_display_4(float(_novo))}**."
                        )
                        st.session_state.stock_baixa_form_nonce = (
                            int(st.session_state.stock_baixa_form_nonce) + 1
                        )
                        st.rerun()

        st.divider()

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

        if not filtered:
            st.info("Nenhuma linha corresponde aos filtros atuais.")
            return

        _estoque_sort_labels = {
            "sku": "SKU (A–Z)",
            "name": "Nome (A–Z)",
            "stock_desc": "Estoque (maior → menor)",
            "stock_asc": "Estoque (menor → maior)",
        }
        _sort_estoque = st.selectbox(
            "Ordenar por",
            ["sku", "name", "stock_desc", "stock_asc"],
            index=1,
            format_func=lambda k: _estoque_sort_labels[k],
            key="estoque_inv_sort_by",
        )
        if _sort_estoque == "sku":
            filtered.sort(
                key=lambda x: (str(x.get("sku") or "").lower(), x.get("product_id", 0))
            )
        elif _sort_estoque == "name":
            filtered.sort(
                key=lambda x: (
                    (x.get("name") or "").lower(),
                    str(x.get("registered_date") or ""),
                    x.get("product_id", 0),
                )
            )
        elif _sort_estoque == "stock_desc":
            filtered.sort(
                key=lambda x: (-float(x["stock_qty"]), (x.get("name") or "").lower())
            )
        else:
            filtered.sort(
                key=lambda x: (float(x["stock_qty"]), (x.get("name") or "").lower())
            )

        totals_cost = 0.0
        totals_price = 0.0
        totals_markup = 0.0
        totals_stock = 0
        _stock_grid_records: list[dict] = []
        for it in filtered:
            cost = float(it["cost"])
            price = float(it["price"])
            markup_amount = float(it["markup"])
            stock_qty = int(it["stock_qty"])
            totals_cost += cost * stock_qty
            totals_price += price * stock_qty
            totals_markup += markup_amount * stock_qty
            totals_stock += stock_qty
            _stock_grid_records.append(
                {
                    "Nome do produto": it["name"] or "—",
                    "SKU": it["sku"] or "—",
                    "Cor armação": it["frame_color"] or "—",
                    "Cor lente": it["lens_color"] or "—",
                    "Estilo": it["style"] or "—",
                    "Paleta": it["palette"] or "—",
                    "Gênero": it["gender"] or "—",
                    "Custo": cost,
                    "Preço de venda": price,
                    "Margem": markup_amount,
                    "Em estoque": float(it["stock_val"]),
                }
            )

        _stock_df = pd.DataFrame(_stock_grid_records)
        _stock_column_order = [
            "Nome do produto",
            "SKU",
            "Cor armação",
            "Cor lente",
            "Estilo",
            "Paleta",
            "Gênero",
            "Custo",
            "Preço de venda",
            "Margem",
            "Em estoque",
        ]
        _stock_grid_state = st.dataframe(
            _stock_df,
            width="stretch",
            hide_index=True,
            column_order=_stock_column_order,
            column_config={
                "Custo": st.column_config.NumberColumn(format="%.2f"),
                "Preço de venda": st.column_config.NumberColumn(format="%.2f"),
                "Margem": st.column_config.NumberColumn(format="%.2f"),
                "Em estoque": st.column_config.NumberColumn(format="%.4f"),
            },
            on_select="rerun",
            selection_mode="single-row",
            key="estoque_inventory_data_grid",
        )

        st.caption(
            "**Excluir lote:** seleccione **uma linha** na grelha (como em **Produtos · Busca por SKU**) "
            "e clique em **Excluir lote selecionado**."
        )
        if st.button(
            "Excluir lote selecionado",
            type="secondary",
            key="estoque_exclude_from_grid_selection",
        ):
            _sel_rows: list[int] = []
            try:
                _sel_rows = list(_stock_grid_state.selection.rows)
            except (AttributeError, TypeError):
                _sel_rows = []
            if not _sel_rows:
                st.error("Seleccione uma linha na grelha antes de excluir.")
            else:
                _ridx = int(_sel_rows[0])
                if _ridx < 0 or _ridx >= len(filtered):
                    st.error("Linha seleccionada inválida. Tente novamente.")
                else:
                    _it = filtered[_ridx]
                    _code = (_it.get("code") or "").strip()
                    if not _code:
                        st.error("Este registo não tem código de entrada para exclusão.")
                    else:
                        _name = _it.get("name") or ""
                        _sku = _it.get("sku") or ""
                        attr_bits = " · ".join(
                            x
                            for x in (
                                _it.get("frame_color"),
                                _it.get("lens_color"),
                                _it.get("style"),
                                _it.get("palette"),
                                _it.get("gender"),
                            )
                            if x
                        )
                        extra = f" | {attr_bits}" if attr_bits else ""
                        st.session_state.pending_exclude_code = _code
                        st.session_state.pending_exclude_label = (
                            f"{_name}{extra} | SKU: {_sku} | Cód.: {_code}"
                        )
                        st.rerun()

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

