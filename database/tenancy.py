"""Identificação de inquilino (multi-tenant): valor único por defeito preserva comportamento mono-inquilino."""

from __future__ import annotations

import sqlite3

from database.sql_compat import db_execute, is_sqlite_conn

# Instalações existentes e chamadas sem argumento usam sempre este id até evolução para SaaS.
DEFAULT_TENANT_ID = "default"

try:
    import psycopg

    _DB_COLLECT_ERRORS: tuple[type[BaseException], ...] = (sqlite3.Error, psycopg.Error)
except ImportError:
    _DB_COLLECT_ERRORS = (sqlite3.Error,)


def resolve_tenant_id(tenant_id: str | None) -> str:
    t = (tenant_id or "").strip()
    return t if t else DEFAULT_TENANT_ID


def effective_tenant_id_for_request(tenant_id: str | None = None) -> str:
    """
    Inquilino efetivo para uma operação na app:

    - Se ``tenant_id`` é passado e não vazio → ``resolve_tenant_id`` desse valor.
    - Senão → sessão Streamlit (após login) via ``get_session_tenant_id``.
    - Fora de sessão / erro de import → ``DEFAULT_TENANT_ID``.
    """
    if tenant_id is not None and str(tenant_id).strip():
        return resolve_tenant_id(tenant_id)
    try:
        from utils import app_auth as _auth

        return _auth.get_session_tenant_id()
    except Exception:
        return DEFAULT_TENANT_ID


def iter_distinct_tenant_ids(conn) -> list[str]:  # noqa: ANN001
    """Lista inquilinos presentes nas tabelas principais (para sincronizar contadores no init)."""
    seen: set[str] = set()
    for table in (
        "users",
        "products",
        "sales",
        "customers",
        "sku_master",
        "sku_sequence_counter",
        "sale_sequence_counter",
        "customer_sequence_counter",
    ):
        try:
            if is_sqlite_conn(conn):
                rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
                if not rows:
                    continue
                cols = {str(r[1]) for r in rows}
            else:
                col_rows = db_execute(
                    conn,
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    """,
                    (table.lower(),),
                ).fetchall()
                if not col_rows:
                    continue
                cols = {str(r["column_name"]) for r in col_rows}
            if "tenant_id" not in cols:
                continue
            for r in db_execute(conn, f"SELECT DISTINCT tenant_id FROM {table};"):
                v = r["tenant_id"]
                if v is not None and str(v).strip():
                    seen.add(str(v).strip())
        except _DB_COLLECT_ERRORS:
            continue
    out = sorted(seen)
    return out if out else [DEFAULT_TENANT_ID]
