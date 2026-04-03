"""Conexão SQLite compartilhada por todas as páginas."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
BASE_DIR = _PKG_DIR.parent

_PRODUCTION_DB_NAME = "business.db"
_DEV_DEFAULT_DB_NAME = "businessdev.db"


def _is_public_streamlit_deploy() -> bool:
    """
    Streamlit Community Cloud coloca o repositório sob ``/mount/src/<app>/``.
    Nesse ambiente o SQLite deve ser sempre ``business.db`` (ignora secrets de dev).
    """
    try:
        return "/mount/src/" in Path(__file__).resolve().as_posix()
    except Exception:
        return False


def _is_production_db_forced_by_env() -> bool:
    """Outros hosts (Docker, VPS): definir ``ALIEH_PRODUCTION=true`` no ambiente."""
    v = (
        os.environ.get("ALIEH_PRODUCTION")
        or os.environ.get("ALIEH_USE_BUSINESS_DB")
        or ""
    ).strip().lower()
    return v in ("1", "true", "yes", "on")


def _sqlite_filename() -> str:
    """
    Nome do ficheiro SQLite na raiz do projeto.

    - **Deploy live (Streamlit Cloud):** sempre ``business.db``.
    - **Outro deploy “live”:** ``ALIEH_PRODUCTION=true`` (ou ``ALIEH_USE_BUSINESS_DB``) → ``business.db``.
    - **Desenvolvimento local:** ``ALIEH_SQLITE`` → segredo ``sqlite_filename`` →
      padrão ``businessdev.db``.
    """
    if _is_public_streamlit_deploy() or _is_production_db_forced_by_env():
        return _PRODUCTION_DB_NAME

    env = (os.environ.get("ALIEH_SQLITE") or "").strip()
    if env:
        return env
    try:
        import streamlit as st

        sec = st.secrets.get("sqlite_filename")
        if sec is not None and str(sec).strip():
            return str(sec).strip()
    except Exception:
        pass
    return _DEV_DEFAULT_DB_NAME


DB_PATH = BASE_DIR / _sqlite_filename()


def get_conn() -> sqlite3.Connection:
    # Nova conexão por uso; Streamlit pode executar código em várias threads.
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
