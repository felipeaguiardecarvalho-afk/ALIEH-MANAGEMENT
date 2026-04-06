"""
Componentes visuais reutilizáveis para o dashboard BI (apresentação).

Design system (Power BI–style, escuro): fundo #0B1C2C, cartões #132F4C, acento #F2A900.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

# —— Design tokens (premium dark) ——
BI_COLORS = {
    "bg": "#0B1C2C",
    "card": "#132F4C",
    "card_elevated": "#1a3d5c",
    "accent": "#F2A900",
    "accent_soft": "#c98a00",
    "text": "#FFFFFF",
    "text_muted": "#B8C5D6",
    "grid": "#1e3a52",
    "sidebar_bg": "#081520",
    "sidebar_border": "#132F4C",
    "shadow": "rgba(0, 0, 0, 0.45)",
    # retrocompat com código que usa gold/gold_dim/accent/line
    "gold": "#F2A900",
    "gold_dim": "#c98a00",
    "line": "#FFFFFF",
    "muted": "#B8C5D6",
}


def inject_bi_dashboard_css() -> None:
    """CSS do painel BI: cartões, filtros, tabelas e tipografia .bi-* (sem fundo global nem sidebar)."""
    t = BI_COLORS
    st.markdown(
        f"""
<style>
/*
 * Tipografia do painel = mesma UI que o resto da app (--alieh-font-ui / Montserrat).
 * Garante Montserrat dentro dos contentores BI quando necessário.
 */
section.main .bi-hero,
section.main .bi-sub,
[data-testid="stMain"] .bi-hero,
[data-testid="stMain"] .bi-sub,
section.main .bi-filter-shell,
section.main .bi-filter-shell h3,
[data-testid="stMain"] .bi-filter-shell,
[data-testid="stMain"] .bi-filter-shell h3,
section.main .bi-card,
section.main .bi-section-title,
section.main .bi-section-header,
[data-testid="stMain"] .bi-card,
[data-testid="stMain"] .bi-section-title,
[data-testid="stMain"] .bi-section-header,
section.main .bi-kpi-tile,
[data-testid="stMain"] .bi-kpi-tile,
section.main .bi-rcard,
section.main .bi-rcard-title,
section.main .bi-rcard-value,
section.main .bi-rcard-sub,
[data-testid="stMain"] .bi-rcard,
[data-testid="stMain"] .bi-rcard-title,
[data-testid="stMain"] .bi-rcard-value,
[data-testid="stMain"] .bi-rcard-sub,
section.main .bi-insight-box,
section.main .bi-insight-box h4,
section.main .bi-insight-box ul,
section.main .bi-insight-box li,
[data-testid="stMain"] .bi-insight-box,
[data-testid="stMain"] .bi-insight-box h4,
[data-testid="stMain"] .bi-insight-box ul,
[data-testid="stMain"] .bi-insight-box li,
section.main .bi-table-shell,
section.main .bi-tables-head,
[data-testid="stMain"] .bi-table-shell,
[data-testid="stMain"] .bi-tables-head {{
  font-family: var(--alieh-font-ui) !important;
}}
section.main .bi-filter-shell h3,
[data-testid="stMain"] .bi-filter-shell h3 {{
  letter-spacing: 0.1em !important;
}}
section.main .bi-insight-box h4,
[data-testid="stMain"] .bi-insight-box h4 {{
  letter-spacing: 0.1em !important;
}}
section.main .bi-card [data-testid="stMetricLabel"],
section.main .bi-card [data-testid="stMetricValue"],
section.main .bi-card [data-testid="stMetricDelta"],
section.main .bi-kpi-tile [data-testid="stMetricLabel"],
section.main .bi-kpi-tile [data-testid="stMetricValue"],
section.main .bi-kpi-tile [data-testid="stMetricDelta"],
[data-testid="stMain"] .bi-card [data-testid="stMetricLabel"],
[data-testid="stMain"] .bi-card [data-testid="stMetricValue"],
[data-testid="stMain"] .bi-card [data-testid="stMetricDelta"],
[data-testid="stMain"] .bi-kpi-tile [data-testid="stMetricLabel"],
[data-testid="stMain"] .bi-kpi-tile [data-testid="stMetricValue"],
[data-testid="stMain"] .bi-kpi-tile [data-testid="stMetricDelta"] {{
  font-family: var(--alieh-font-ui) !important;
}}

.bi-hero {{
  font-size: 1.7rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: {t["text"]};
  margin: 0 0 0.25rem 0;
}}
.bi-sub {{
  color: {t["text_muted"]};
  font-size: 0.92rem;
  margin: 0 0 1.1rem 0;
  line-height: 1.5;
}}

.bi-filter-shell {{
  background: linear-gradient(160deg, {t["card"]} 0%, {t["card_elevated"]} 100%);
  border: 1px solid {t["grid"]};
  border-radius: 16px;
  padding: 1.05rem 1.15rem;
  margin-bottom: 1.2rem;
  box-shadow: 0 8px 32px {t["shadow"]};
}}
.bi-filter-shell h3 {{
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: {t["accent"]};
  margin: 0 0 0.7rem 0;
}}

.bi-card {{
  background: linear-gradient(165deg, {t["card"]} 0%, #122a40 100%);
  border: 1px solid {t["grid"]};
  border-radius: 16px;
  padding: 1rem 1.15rem 1.1rem 1.15rem;
  margin-bottom: 1rem;
  box-shadow: 0 6px 28px {t["shadow"]};
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}}
.bi-card:hover {{
  border-color: rgba(242, 169, 0, 0.35);
  box-shadow: 0 10px 36px rgba(0, 0, 0, 0.55);
}}
.bi-section-title {{
  font-size: 1rem;
  font-weight: 600;
  color: {t["text"]};
  margin: 0 0 0.7rem 0;
  letter-spacing: -0.02em;
}}

.bi-section-header {{
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: {t["accent"]};
  margin: 1.35rem 0 0.65rem 0;
  padding-bottom: 0.35rem;
  border-bottom: 1px solid {t["grid"]};
}}

.bi-kpi-tile {{
  background: rgba(19, 47, 76, 0.85);
  border: 1px solid {t["grid"]};
  border-radius: 14px;
  padding: 0.9rem 1rem 1rem 1rem;
  height: 100%;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
}}
.bi-kpi-tile:hover {{
  border-color: rgba(242, 169, 0, 0.3);
}}

[data-testid="stMetricValue"] {{
  color: {t["text"]} !important;
  font-weight: 700 !important;
}}
[data-testid="stMetricLabel"] {{
  color: {t["text_muted"]} !important;
}}
[data-testid="stMetricDelta"] {{
  font-size: 0.78rem !important;
}}

/* Cartão genérico (título / valor / subtítulo) */
.bi-rcard {{
  background: linear-gradient(145deg, {t["card_elevated"]} 0%, {t["card"]} 100%);
  border: 1px solid {t["grid"]};
  border-radius: 14px;
  padding: 1rem 1.15rem;
  margin-bottom: 0.65rem;
  border-left: 3px solid {t["accent"]};
  box-shadow: 0 4px 20px {t["shadow"]};
}}
.bi-rcard-title {{
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: {t["text_muted"]};
  margin: 0 0 0.35rem 0;
}}
.bi-rcard-value {{
  font-size: 1.35rem;
  font-weight: 700;
  color: {t["text"]};
  margin: 0;
  line-height: 1.2;
}}
.bi-rcard-sub {{
  font-size: 0.85rem;
  color: {t["accent"]};
  margin: 0.45rem 0 0 0;
  line-height: 1.4;
}}

/* Insight (painel lateral) */
.bi-insight-box {{
  background: linear-gradient(180deg, {t["card"]} 0%, #0f2840 100%);
  border: 1px solid {t["grid"]};
  border-radius: 16px;
  padding: 1.15rem 1.2rem;
  min-height: 280px;
  box-shadow: 0 8px 32px {t["shadow"]};
}}
.bi-insight-box h4 {{
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: {t["accent"]};
  margin: 0 0 0.85rem 0;
}}
.bi-insight-box ul {{
  margin: 0;
  padding-left: 1.1rem;
  color: {t["text_muted"]};
  font-size: 0.92rem;
  line-height: 1.65;
}}
.bi-insight-box li {{
  margin-bottom: 0.45rem;
}}
.bi-insight-box strong {{
  color: {t["text"]};
}}

/* Tabelas */
.bi-table-shell {{
  background: {t["card"]};
  border: 1px solid {t["grid"]};
  border-radius: 16px;
  padding: 1rem 1.1rem;
  margin-bottom: 1rem;
  box-shadow: 0 6px 28px {t["shadow"]};
}}
.bi-tables-head {{
  font-size: 0.76rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: {t["accent"]};
  margin: 1.5rem 0 0.75rem 0;
}}

hr.bi-rule {{
  border: none;
  border-top: 1px solid {t["grid"]};
  margin: 1.25rem 0;
}}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_section(title: str) -> None:
    """Cabeçalho de secção (hierarquia visual)."""
    st.markdown(
        f'<div class="bi-section-header">{title}</div>',
        unsafe_allow_html=True,
    )


def render_card(title: str, value: str, subtitle: str | None = None) -> None:
    """
    Cartão de métrica textual (sem ``st.metric`` — usar para destaques estáticos
    ou subtítulos já formatados)."""
    sub_html = (
        f'<p class="bi-rcard-sub">{subtitle}</p>' if subtitle else ""
    )
    st.markdown(
        f'<div class="bi-rcard">'
        f'<p class="bi-rcard-title">{title}</p>'
        f'<p class="bi-rcard-value">{value}</p>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def render_container():
    """Contentor Streamlit para agrupar widgets com alinhamento consistente."""
    return st.container()


def render_insight_box(title: str, items_html: list[str]) -> None:
    """Caixa de insights com lista HTML (cada item é uma linha já escapada)."""
    lis = "".join(f"<li>{line}</li>" for line in items_html)
    st.markdown(
        f'<div class="bi-insight-box"><h4>{title}</h4><ul>{lis}</ul></div>',
        unsafe_allow_html=True,
    )


def bi_hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<p class="bi-hero">{title}</p><p class="bi-sub">{subtitle}</p>',
        unsafe_allow_html=True,
    )


def bi_filter_bar_heading(label: str = "Filtros") -> None:
    st.markdown(
        f'<div class="bi-filter-shell"><h3>{label}</h3>',
        unsafe_allow_html=True,
    )


def bi_filter_bar_end() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def bi_card_start(title: str) -> None:
    st.markdown(
        f'<div class="bi-card"><p class="bi-section-title">{title}</p>',
        unsafe_allow_html=True,
    )


def bi_card_end() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def bi_kpi_tile_start() -> None:
    st.markdown('<div class="bi-kpi-tile">', unsafe_allow_html=True)


def bi_kpi_tile_end() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def bi_section_tables_heading(text: str = "Detalhes operacionais") -> None:
    st.markdown(f'<p class="bi-tables-head">{text}</p>', unsafe_allow_html=True)


def bi_page_divider() -> None:
    st.markdown('<hr class="bi-rule"/>', unsafe_allow_html=True)


def bi_table_shell_start() -> None:
    st.markdown('<div class="bi-table-shell">', unsafe_allow_html=True)


def bi_table_shell_end() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def apply_plotly_bi_theme(
    fig: go.Figure,
    title: str | None = None,
    *,
    show_grid: bool = False,
) -> go.Figure:
    """Tema Plotly alinhado ao design system (sem grelha por defeito)."""
    t = BI_COLORS
    gridc = t["grid"] if show_grid else "rgba(0,0,0,0)"
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=t["bg"],
        plot_bgcolor=t["bg"],
        font=dict(
            color=t["text_muted"],
            family="Montserrat, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
            size=12,
        ),
        title=dict(
            text=title or "",
            font=dict(
                size=15,
                color=t["text"],
                family="Montserrat, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
            ),
            x=0,
            xanchor="left",
        ),
        margin=dict(l=8, r=8, t=54 if title else 26, b=32),
        xaxis=dict(
            showgrid=show_grid,
            gridcolor=gridc,
            zeroline=False,
            showline=False,
            tickfont=dict(color=t["text_muted"]),
        ),
        yaxis=dict(
            showgrid=show_grid,
            gridcolor=gridc,
            zeroline=False,
            showline=False,
            tickfont=dict(color=t["text_muted"]),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11, color=t["text_muted"]),
            bgcolor="rgba(0,0,0,0)",
        ),
        hoverlabel=dict(
            bgcolor=t["card"],
            bordercolor=t["accent"],
            font_size=12,
            font_family="Montserrat, system-ui, sans-serif",
            font_color=t["text"],
        ),
    )
    return fig
