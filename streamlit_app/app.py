"""
Dashboard Streamlit ligado ao PostgreSQL (Supabase).

Configuracao: defina DATABASE_URL em .streamlit/secrets.toml na raiz desta pasta
de aplicacao, ou nos segredos do Streamlit Cloud — nunca no codigo fonte.

Executar (a partir da pasta streamlit_app):
    streamlit run app.py
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import psycopg
from psycopg.rows import dict_row


def _fmt_brl(value: float) -> str:
    """Formato monetario simples (pt-BR)."""
    txt = f"{abs(value):,.2f}"
    inteiro, frac = txt.split(".")
    inteiro = inteiro.replace(",", ".")
    return f"R$ {inteiro},{frac}"


def _friendly_db_error(exc: Exception) -> str:
    return (
        "Não foi possível ligar à base de dados ou executar as consultas. "
        "Confirme o **DATABASE_URL** nos segredos, a rede, SSL e permissões da role.\n\n"
        f"**Tipo:** `{type(exc).__name__}`  \n**Mensagem:** {exc}"
    )


st.set_page_config(
    page_title="Dashboard de Gestão",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("Dashboard de Gestão")

try:
    _ = st.secrets["DATABASE_URL"]
except (KeyError, FileNotFoundError):
    st.error(
        "Segredo **DATABASE_URL** não encontrado. "
        "Crie `.streamlit/secrets.toml` com `DATABASE_URL = \"postgresql://...\"` "
        "ou configure o mesmo segredo na plataforma de deploy."
    )
    st.stop()

conn: psycopg.Connection | None = None
try:
    conn = psycopg.connect(
        st.secrets["DATABASE_URL"],
        connect_timeout=20,
        row_factory=dict_row,
        autocommit=True,
    )
except Exception as e:
    st.error(_friendly_db_error(e))
    st.stop()

try:
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(SUM(total), 0) AS s_total FROM sales;")
        total_vendas = float(cur.fetchone()["s_total"] or 0)

        cur.execute("SELECT COALESCE(SUM(cogs_total), 0) AS s_cogs FROM sales;")
        total_cogs = float(cur.fetchone()["s_cogs"] or 0)

        cur.execute("SELECT COUNT(*)::bigint AS n FROM sales;")
        num_pedidos = int(cur.fetchone()["n"] or 0)

    lucro_total = total_vendas - total_cogs
    ticket_medio = (total_vendas / num_pedidos) if num_pedidos else 0.0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total de vendas", _fmt_brl(total_vendas))
    with c2:
        st.metric("Total de lucro", _fmt_brl(lucro_total))
    with c3:
        st.metric("Ticket médio", _fmt_brl(ticket_medio))
    with c4:
        st.metric("Número de pedidos", f"{num_pedidos:,}".replace(",", "."))

    st.subheader("Vendas nos últimos 30 dias")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT (date_trunc('day', sold_at::timestamp))::date AS day,
                   SUM(total::numeric) AS revenue
            FROM sales
            WHERE sold_at::timestamp >= (CURRENT_TIMESTAMP - INTERVAL '30 days')
            GROUP BY 1
            ORDER BY 1;
            """
        )
        rows = cur.fetchall()

    if not rows:
        st.info("Não há vendas no período selecionado.")
    else:
        df = pd.DataFrame([{"day": r["day"], "revenue": float(r["revenue"] or 0)} for r in rows])
        # Evita eixo temporal com horas (12:00, 18:00): usar rótulos de dia em texto.
        df["dia"] = pd.to_datetime(df["day"], errors="coerce").dt.strftime("%d/%m/%Y")
        fig = px.bar(
            df,
            x="dia",
            y="revenue",
            labels={"dia": "Dia", "revenue": "Receita (R$)"},
            text_auto=".2f",
        )
        fig.update_traces(marker_color="#1f77b4")
        fig.update_layout(
            template="plotly_white",
            yaxis_tickformat=",.2f",
            hovermode="x unified",
            margin=dict(l=20, r=20, t=40, b=20),
        )
        fig.update_xaxes(type="category", title="Dia")
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(_friendly_db_error(e))
finally:
    if conn is not None and not conn.closed:
        conn.close()
