"""
Painel executivo BI — métricas e consultas inalteradas; apresentação via :mod:`ui.components`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analytics import metrics as bi_metrics
from analytics.transformations import add_rolling_mean, format_delta_pct, kpi_delta_pct
from services.read_queries import (
    fetch_customers_ordered,
    fetch_daily_revenue_profit,
    fetch_dashboard_kpis_period,
    fetch_inventory_stock_summary,
    fetch_low_stock_products_dashboard,
    fetch_payment_method_breakdown,
    fetch_products,
    fetch_sales_date_bounds,
    fetch_sku_master_rows,
    fetch_top_customers_by_revenue,
    fetch_top_skus_by_metric,
)
from services.tenant_scope import effective_tenant_id_for_request
from ui.components import (
    BI_COLORS,
    apply_plotly_bi_theme,
    bi_card_end,
    bi_card_start,
    bi_filter_bar_end,
    bi_filter_bar_heading,
    bi_hero,
    bi_kpi_tile_end,
    bi_kpi_tile_start,
    bi_page_divider,
    bi_section_tables_heading,
    bi_table_shell_end,
    bi_table_shell_start,
    inject_bi_dashboard_css,
    render_insight_box,
    render_section,
)
from utils.formatters import format_money


def _tid() -> str:
    return effective_tenant_id_for_request()


def _prev_range(date_start: str, date_end: str) -> tuple[str, str]:
    d0 = datetime.strptime(date_start, "%Y-%m-%d").date()
    d1 = datetime.strptime(date_end, "%Y-%m-%d").date()
    n_days = (d1 - d0).days + 1
    p_end = d0 - timedelta(days=1)
    p_start = p_end - timedelta(days=n_days - 1)
    return p_start.isoformat(), p_end.isoformat()


@st.cache_data(ttl=120)
def _cached_kpis(
    tenant_key: str,
    date_start: str,
    date_end: str,
    sku_key: str,
    customer_id_key: int,
    product_id_key: int,
) -> dict[str, Any]:
    sku = sku_key.strip() or None
    cid = customer_id_key if customer_id_key > 0 else None
    pid = product_id_key if product_id_key > 0 else None
    cur = fetch_dashboard_kpis_period(
        date_start, date_end, sku=sku, customer_id=cid, product_id=pid
    )
    p0, p1 = _prev_range(date_start, date_end)
    prev = fetch_dashboard_kpis_period(
        p0, p1, sku=sku, customer_id=cid, product_id=pid
    )
    return {"current": cur, "previous": prev, "prev_start": p0, "prev_end": p1}


@st.cache_data(ttl=120)
def _cached_daily(
    tenant_key: str,
    date_start: str,
    date_end: str,
    sku_key: str,
    customer_id_key: int,
    product_id_key: int,
) -> pd.DataFrame:
    sku = sku_key.strip() or None
    cid = customer_id_key if customer_id_key > 0 else None
    pid = product_id_key if product_id_key > 0 else None
    return fetch_daily_revenue_profit(
        date_start, date_end, sku=sku, customer_id=cid, product_id=pid
    )


@st.cache_data(ttl=120)
def _cached_top_skus_rev(
    tenant_key: str,
    date_start: str,
    date_end: str,
    sku_key: str,
    customer_id_key: int,
    product_id_key: int,
) -> pd.DataFrame:
    sku = sku_key.strip() or None
    cid = customer_id_key if customer_id_key > 0 else None
    pid = product_id_key if product_id_key > 0 else None
    return fetch_top_skus_by_metric(
        date_start, date_end, sku=sku, customer_id=cid, product_id=pid, limit=12
    )


@st.cache_data(ttl=120)
def _cached_margin_skus(
    tenant_key: str,
    date_start: str,
    date_end: str,
    sku_key: str,
    customer_id_key: int,
    product_id_key: int,
) -> pd.DataFrame:
    sku = sku_key.strip() or None
    cid = customer_id_key if customer_id_key > 0 else None
    pid = product_id_key if product_id_key > 0 else None
    return bi_metrics.get_margin_per_sku(
        date_start, date_end, sku=sku, customer_id=cid, product_id=pid, limit=25
    )


@st.cache_data(ttl=120)
def _cached_turnover(
    tenant_key: str,
    date_start: str,
    date_end: str,
    sku_key: str,
    customer_id_key: int,
    product_id_key: int,
) -> pd.DataFrame:
    sku = sku_key.strip() or None
    cid = customer_id_key if customer_id_key > 0 else None
    pid = product_id_key if product_id_key > 0 else None
    return bi_metrics.get_stock_turnover(
        date_start, date_end, sku=sku, customer_id=cid, product_id=pid, limit=20
    )


@st.cache_data(ttl=300)
def _cached_cohort(tenant_key: str) -> pd.DataFrame:
    return bi_metrics.get_cohort_summary()


@st.cache_data(ttl=300)
def _cached_stock_aging(tenant_key: str, min_days: int) -> pd.DataFrame:
    return bi_metrics.get_stock_aging(min_days=min_days, limit=35)


@st.cache_data(ttl=300)
def _cached_low_stock(tenant_key: str) -> pd.DataFrame:
    return fetch_low_stock_products_dashboard(threshold=5.0, limit=45)


@st.cache_data(ttl=300)
def _cached_inventory_summary(tenant_key: str) -> dict[str, Any]:
    return fetch_inventory_stock_summary()


@st.cache_data(ttl=120)
def _cached_payment(
    tenant_key: str,
    date_start: str,
    date_end: str,
    sku_key: str,
    customer_id_key: int,
    product_id_key: int,
) -> pd.DataFrame:
    sku = sku_key.strip() or None
    cid = customer_id_key if customer_id_key > 0 else None
    pid = product_id_key if product_id_key > 0 else None
    return fetch_payment_method_breakdown(
        date_start, date_end, sku=sku, customer_id=cid, product_id=pid
    )


@st.cache_data(ttl=120)
def _cached_top_customers(
    tenant_key: str,
    date_start: str,
    date_end: str,
    sku_key: str,
    customer_id_key: int,
    product_id_key: int,
) -> pd.DataFrame:
    sku = sku_key.strip() or None
    cid = customer_id_key if customer_id_key > 0 else None
    pid = product_id_key if product_id_key > 0 else None
    return fetch_top_customers_by_revenue(
        date_start, date_end, sku=sku, customer_id=cid, product_id=pid, limit=10
    )


def render_painel_executivo() -> None:
    """Dashboard BI: mesmos dados e caches; layout premium (visual só) via :mod:`ui.components`."""
    c = BI_COLORS
    inject_bi_dashboard_css()
    bi_hero(
        "Intelligence · ALIEH",
        "Indicadores para decisão comercial — receita, margem, giro e risco de stock.",
    )

    d_min, d_max = fetch_sales_date_bounds()
    today = date.today()
    default_end = d_max or today.isoformat()
    default_start = d_min or (today - timedelta(days=29)).isoformat()

    prod_rows = list(fetch_products())
    prod_options: list[tuple[int, str]] = [(0, "Todos os produtos")]
    for r in prod_rows:
        pid = int(r["id"])
        nm = (str(r["name"]).strip() if r["name"] else "") or f"#{pid}"
        sku_l = str(r["sku"]).strip() if r["sku"] else ""
        label = f"{nm}" + (f" · {sku_l}" if sku_l else "")
        prod_options.append((pid, label))

    sku_rows = fetch_sku_master_rows()
    sku_opts = [""] + [str(r["sku"]).strip() for r in sku_rows if r["sku"]]

    cust_rows = fetch_customers_ordered()
    cust_map: dict[int, str] = {0: "Todos"}
    for r in cust_rows:
        cid = int(r["id"])
        nm, code = r["name"], r["customer_code"]
        cust_map[cid] = (
            f"{(str(nm).strip() if nm is not None else '') or '—'} "
            f"({(str(code).strip() if code is not None else '') or cid})"
        )

    bi_filter_bar_heading("Filtros globais")
    fc1, fc2, fc3, fc4, fc5 = st.columns([1, 1, 1.2, 1.2, 1])
    with fc1:
        preset = st.selectbox(
            "Período",
            ("Personalizado", "7 dias", "30 dias", "90 dias"),
            key="bi_preset",
        )
    with fc2:
        st.number_input(
            "Clientes ativos (dias)",
            min_value=7,
            max_value=365,
            value=90,
            key="bi_active_days",
        )
    with fc3:
        pix = st.selectbox(
            "Produto",
            range(len(prod_options)),
            format_func=lambda i: prod_options[i][1],
            key="bi_product",
        )
        product_id_sel = prod_options[pix][0]
    with fc4:
        sku_sel = st.selectbox(
            "SKU",
            sku_opts,
            format_func=lambda s: "Todos" if not s else s,
            key="bi_sku",
        )
    with fc5:
        cust_ids = list(cust_map.keys())
        cix = st.selectbox(
            "Cliente",
            range(len(cust_ids)),
            format_func=lambda i: cust_map[cust_ids[i]],
            key="bi_customer",
        )
        customer_id = cust_ids[cix]

    if preset == "7 dias":
        date_end = today
        date_start = today - timedelta(days=6)
    elif preset == "30 dias":
        date_end = today
        date_start = today - timedelta(days=29)
    elif preset == "90 dias":
        date_end = today
        date_start = today - timedelta(days=89)
    else:
        d0_def = datetime.strptime(default_start, "%Y-%m-%d").date()
        d1_def = datetime.strptime(default_end, "%Y-%m-%d").date()
        dc1, dc2 = st.columns(2)
        with dc1:
            date_start = st.date_input(
                "Início",
                value=d0_def,
                min_value=datetime(2000, 1, 1).date(),
                max_value=today,
                key="bi_d0",
            )
        with dc2:
            date_end = st.date_input(
                "Fim",
                value=d1_def,
                min_value=datetime(2000, 1, 1).date(),
                max_value=today,
                key="bi_d1",
            )

    if preset != "Personalizado":
        st.caption(
            f"Janela: **{date_start.isoformat()}** — **{date_end.isoformat()}**"
        )

    bi_filter_bar_end()

    if date_start > date_end:
        st.warning("A data de início deve ser ≤ à data de fim.")
        return

    ds_str = date_start.isoformat()
    de_str = date_end.isoformat()
    tenant_key = _tid()
    sku_key = (sku_sel or "").strip()
    cust_key = int(customer_id)
    prod_key = int(product_id_sel)

    kpi_pack = _cached_kpis(
        tenant_key, ds_str, de_str, sku_key, cust_key, prod_key
    )
    cur = kpi_pack["current"]
    prev = kpi_pack["previous"]
    daily = _cached_daily(
        tenant_key, ds_str, de_str, sku_key, cust_key, prod_key
    )
    top_rev = _cached_top_skus_rev(
        tenant_key, ds_str, de_str, sku_key, cust_key, prod_key
    )
    top_c = _cached_top_customers(
        tenant_key, ds_str, de_str, sku_key, cust_key, prod_key
    )
    inv_summary = _cached_inventory_summary(tenant_key)
    name_by_id = {
        int(r["id"]): (str(r["name"]).strip() if r["name"] else str(r["id"]))
        for r in cust_rows
    }

    # --- 1) KPI row (4 colunas) — mesmos st.metric / cálculos ---
    render_section("Indicadores do período")
    bi_card_start("Resumo")
    k1, k2, k3, k4 = st.columns(4)
    dr = kpi_delta_pct(cur["revenue"], prev["revenue"])
    d_sales = kpi_delta_pct(
        float(cur["sales_count"]), float(prev["sales_count"])
    )
    dt = kpi_delta_pct(cur["ticket_avg"], prev["ticket_avg"])
    mpp_diff = float(cur["margin_pct"]) - float(prev["margin_pct"])

    with k1:
        bi_kpi_tile_start()
        st.metric(
            "Receita",
            format_money(cur["revenue"]),
            delta=format_delta_pct(dr),
        )
        bi_kpi_tile_end()
    with k2:
        bi_kpi_tile_start()
        st.metric(
            "Volume (linhas de venda)",
            f"{cur['sales_count']:,}".replace(",", "."),
            delta=format_delta_pct(d_sales),
        )
        bi_kpi_tile_end()
    with k3:
        bi_kpi_tile_start()
        st.metric(
            "Ticket médio",
            format_money(cur["ticket_avg"]),
            delta=format_delta_pct(dt),
        )
        bi_kpi_tile_end()
    with k4:
        bi_kpi_tile_start()
        st.metric(
            "Margem bruta",
            f"{cur['margin_pct']:.1f}%",
            delta=f"{mpp_diff:+.1f} p.p." if prev["revenue"] > 0 else None,
        )
        bi_kpi_tile_end()

    st.caption(
        f"Referência: {kpi_pack['prev_start']} — {kpi_pack['prev_end']} (mesma duração)."
    )
    bi_card_end()

    # --- 2) Linha principal: gráfico + caixa de insights (só texto a partir de dados já carregados) ---
    render_section("Visão executiva")
    row_main_l, row_main_r = st.columns([1.65, 1.0])
    with row_main_l:
        bi_card_start("Principais clientes · faturamento")
        if top_c.empty:
            st.caption("Sem dados.")
        else:
            disp = top_c.copy()
            disp["nome"] = disp["customer_id"].map(
                lambda i: name_by_id.get(int(i), str(i))
            )
            fig = go.Figure(
                go.Bar(
                    x=disp["revenue"],
                    y=disp["nome"],
                    orientation="h",
                    marker=dict(
                        color=disp["revenue"],
                        colorscale=[[0, c["card"]], [1, c["accent"]]],
                        line=dict(width=0),
                    ),
                    hovertemplate="%{y}<br>R$ %{x:,.2f}<extra></extra>",
                )
            )
            apply_plotly_bi_theme(fig, None)
            fig.update_xaxes(tickprefix="R$ ")
            fig.update_yaxes(autorange="reversed")
            st.plotly_chart(fig, use_container_width=True, key="bi_main_top_customers")
        bi_card_end()
    with row_main_r:
        insight_lines: list[str] = []
        if not top_rev.empty and cur["revenue"] > 0:
            row0 = top_rev.iloc[0]
            pct = 100.0 * float(row0["revenue"]) / cur["revenue"]
            insight_lines.append(
                f"<strong>{row0['sku']}</strong> representa <strong>{pct:.1f}%</strong> da receita do período."
            )
        if prev["revenue"] > 0 and abs(mpp_diff) >= 0.5:
            insight_lines.append(
                f"A margem média <strong>{'reduziu' if mpp_diff < 0 else 'aumentou'} {abs(mpp_diff):.1f} p.p.</strong> vs referência."
            )
        if inv_summary["n_critical_skus"] > 0:
            insight_lines.append(
                f"<strong>{int(inv_summary['n_critical_skus'])}</strong> produto(s) com stock ≤ 5 unidades."
            )
        if not top_c.empty and cur["revenue"] > 0:
            t0 = top_c.iloc[0]
            nm = name_by_id.get(int(t0["customer_id"]), str(t0["customer_id"]))
            insight_lines.append(
                f"Cliente destaque: <strong>{nm}</strong> ({format_money(float(t0['revenue']))})."
            )
        if not insight_lines:
            insight_lines.append(
                "Sem destaques adicionais para o filtro actual — ajuste o período ou dimensões."
            )
        render_insight_box("Insights", insight_lines)

    # --- 3) Tendência de receita | Top produtos (SKU receita) ---
    render_section("Série e ranking")
    row_trend, row_top = st.columns(2)
    with row_trend:
        bi_card_start("Tendência de receita (diária)")
        if daily.empty:
            st.caption("Sem vendas no período filtrado.")
        else:
            d_ma = add_rolling_mean(daily, "revenue", "day", window=7, out_col="ma7")
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=d_ma["day"],
                    y=d_ma["revenue"],
                    name="Receita diária",
                    mode="lines+markers",
                    line=dict(color=c["accent"], width=2.2),
                    marker=dict(size=6, color=c["accent"]),
                    hovertemplate="%{x}<br>R$ %{y:,.2f}<extra></extra>",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=d_ma["day"],
                    y=d_ma["ma7"],
                    name="MM7",
                    mode="lines",
                    line=dict(color=c["text_muted"], width=2, dash="dash"),
                    hovertemplate="%{x}<br>MM7: R$ %{y:,.2f}<extra></extra>",
                )
            )
            apply_plotly_bi_theme(fig, "Receita e média móvel (7)")
            fig.update_yaxes(tickprefix="R$ ")
            st.plotly_chart(fig, use_container_width=True, key="bi_trend_revenue_ma")
        bi_card_end()

    with row_top:
        bi_card_start("Top produtos · receita por SKU")
        if top_rev.empty:
            st.caption("Sem dados.")
        else:
            chart = top_rev.sort_values("revenue").tail(12)
            fig = go.Figure(
                go.Bar(
                    x=chart["revenue"],
                    y=chart["sku"],
                    orientation="h",
                    marker=dict(
                        color=chart["revenue"],
                        colorscale=[[0, c["card"]], [1, c["accent"]]],
                        line=dict(width=0),
                    ),
                    hovertemplate="%{y}<br>R$ %{x:,.2f}<extra></extra>",
                )
            )
            apply_plotly_bi_theme(fig, None)
            fig.update_xaxes(tickprefix="R$ ")
            fig.update_yaxes(autorange="reversed")
            st.plotly_chart(fig, use_container_width=True, key="bi_bar_top_sku")
        bi_card_end()

    # --- Análises complementares (mesmos dados / caches) ---
    render_section("Análises complementares")
    row_b1, row_b2 = st.columns(2)
    with row_b1:
        bi_card_start("Margem por SKU")
        marg_df = _cached_margin_skus(
            tenant_key, ds_str, de_str, sku_key, cust_key, prod_key
        )
        if marg_df.empty:
            st.caption("Sem SKUs no filtro.")
        else:
            low_m = marg_df[marg_df["margin_pct"] < 15].head(8)
            if not low_m.empty:
                st.warning(
                    f"{len(low_m)} SKUs com margem < 15% no período — rever preço ou custo."
                )
            sub = marg_df.head(12).sort_values("margin_pct")
            fig = go.Figure(
                go.Bar(
                    x=sub["margin_pct"],
                    y=sub["sku"],
                    orientation="h",
                    marker_color=c["accent"],
                    hovertemplate="%{y}<br>%{x:.1f}% margem<extra></extra>",
                )
            )
            apply_plotly_bi_theme(fig, "Margem % (subset)")
            fig.update_xaxes(title_text="Margem %")
            st.plotly_chart(fig, use_container_width=True, key="bi_margin_bar")
        bi_card_end()

    with row_b2:
        bi_card_start("Cohort · primeira compra")
        coh = _cached_cohort(tenant_key)
        if coh.empty:
            st.caption("Sem histórico de vendas.")
        else:
            fig = go.Figure(
                go.Bar(
                    x=coh["cohort_month"],
                    y=coh["n_customers"],
                    marker_color=c["accent_soft"],
                    hovertemplate="%{x}<br>%{y} cliente(s)<extra></extra>",
                )
            )
            apply_plotly_bi_theme(fig, "Novos compradores por mês")
            fig.update_xaxes(title_text="Mês (primeira compra)")
            fig.update_yaxes(title_text="Clientes")
            st.plotly_chart(fig, use_container_width=True, key="bi_cohort")
        bi_card_end()

    row_c1, row_c2 = st.columns(2)
    with row_c1:
        bi_card_start("Giro de stock (proxy no período)")
        turn = _cached_turnover(
            tenant_key, ds_str, de_str, sku_key, cust_key, prod_key
        )
        if turn.empty:
            st.caption("Sem vendas suficientes.")
        else:
            fig = go.Figure(
                go.Bar(
                    x=turn["turnover_ratio"],
                    y=turn["sku"],
                    orientation="h",
                    marker_color=c["gold_dim"],
                    opacity=0.92,
                    hovertemplate="%{y}<br>ratio %{x:.2f}<extra></extra>",
                )
            )
            apply_plotly_bi_theme(fig, "Unidades vendidas / stock mestre")
            st.plotly_chart(fig, use_container_width=True, key="bi_turnover")
        bi_card_end()

    with row_c2:
        bi_card_start("Forma de pagamento")
        pay = _cached_payment(
            tenant_key, ds_str, de_str, sku_key, cust_key, prod_key
        )
        if pay.empty:
            st.caption("Sem dados.")
        else:
            fig = go.Figure(
                go.Pie(
                    labels=pay["payment_method"],
                    values=pay["revenue"],
                    hole=0.5,
                    marker=dict(
                        colors=[
                            c["accent"],
                            c["accent_soft"],
                            c["text_muted"],
                            "#5c7a99",
                            "#2d4a62",
                        ]
                    ),
                    hovertemplate="%{label}<br>R$ %{value:,.2f}<extra></extra>",
                )
            )
            apply_plotly_bi_theme(fig, None)
            st.plotly_chart(fig, use_container_width=True, key="bi_pie_pay")
        bi_card_end()

    # --- Tabelas (fundo) — contentores estilados ---
    bi_page_divider()
    bi_section_tables_heading("Detalhes operacionais")

    tbl_left, tbl_right = st.columns(2)
    with tbl_left:
        bi_table_shell_start()
        st.markdown(
            '<p class="bi-section-title">Stock crítico (≤ 5 un.)</p>',
            unsafe_allow_html=True,
        )
        low_df = _cached_low_stock(tenant_key)
        if low_df.empty:
            st.success("Nenhum produto abaixo do limiar.")
        else:
            disp = low_df.copy()
            disp["critico"] = disp["stock"] <= 2
            disp = disp.assign(
                unit_cost=disp["unit_cost"].map(format_money),
                sell_price=disp["sell_price"].map(format_money),
                stock=disp["stock"].apply(lambda x: f"{x:g}"),
                alerta=disp["critico"].map(
                    lambda x: "Crítico" if x else "Baixo"
                ),
            )
            st.dataframe(
                disp[["sku", "name", "stock", "alerta", "unit_cost", "sell_price"]],
                width="stretch",
                hide_index=True,
                column_config={
                    "alerta": st.column_config.TextColumn(
                        "Prioridade",
                        help="Crítico: stock ≤ 2",
                    ),
                },
            )
        bi_table_shell_end()

    with tbl_right:
        bi_table_shell_start()
        st.markdown(
            '<p class="bi-section-title">Inventário envelhecido</p>',
            unsafe_allow_html=True,
        )
        aging_days = st.slider(
            "Dias sem venda",
            15,
            180,
            45,
            key="bi_aging_days",
            help="SKUs com stock e sem venda há pelo menos este intervalo (ou nunca vendidos).",
        )
        aging = _cached_stock_aging(tenant_key, int(aging_days))
        if aging.empty:
            st.caption("Nenhum SKU em risco com estes critérios.")
        else:
            st.dataframe(
                aging.assign(
                    total_stock=aging["total_stock"].apply(lambda x: f"{x:g}")
                ),
                width="stretch",
                hide_index=True,
            )
        bi_table_shell_end()

    bi_table_shell_start()
    st.markdown(
        '<p class="bi-section-title">Resumo de inventário</p>',
        unsafe_allow_html=True,
    )
    st.metric(
        "Valor inventário (CMP)",
        format_money(inv_summary["value_cmp"]),
        help="Somatório stock × custo médio",
    )
    st.caption(
        f"Unidades em produtos: **{inv_summary['total_units']:,.0f}** · "
        f"Itens críticos (≤5): **{int(inv_summary['n_critical_skus'])}**"
    )
    bi_table_shell_end()
