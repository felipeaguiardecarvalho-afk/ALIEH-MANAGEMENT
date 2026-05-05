"""Configuração de base de dados — detecção automática (MCP-friendly) com sobreposição opcional.

**Modo automático** (``DB_PROVIDER`` ausente ou vazio):

- ``DATABASE_URL`` definido (env `DATABASE_URL` ou segredos ``DATABASE_URL`` / ``database_url``)
  → PostgreSQL.
- Caso contrário → SQLite (**fallback mode**), sem configuração manual.

**Sobreposição explícita:** ``DB_PROVIDER`` = ``sqlite`` | ``postgres`` (ou sinónimos) —
comportamento legado preservado.

**Sem fallback SQLite em produção:** :func:`database.connection.get_db_conn` usa apenas
PostgreSQL; falhas de ligação propagam :exc:`ConnectionError`.

DSN completo (Supabase, etc.): :func:`get_postgres_dsn` —
``SUPABASE_DB_URL``, ``DATABASE_URL``, ``POSTGRES_DSN``, ``ALIEH_DATABASE_URL`` e segredos.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

from utils.env_safe import PATH_RESOLVE_ERRORS, STREAMLIT_CONFIG_READ_ERRORS

_PKG_DIR = Path(__file__).resolve().parent
BASE_DIR = _PKG_DIR.parent

_logger = logging.getLogger(__name__)

DB_PROVIDER_ENV = "DB_PROVIDER"
DATABASE_URL_ENV = "DATABASE_URL"

_PRIMARY_SELECTION_LOGGED = False

_PRODUCTION_DB_NAME = "business.db"
_DEV_DEFAULT_DB_NAME = "businessdev.db"

# Ordem de precedência para o DSN Postgres (sem dependência de driver aqui)
POSTGRES_DSN_ENV_VARS = (
    "SUPABASE_DB_URL",
    "DATABASE_URL",
    "POSTGRES_DSN",
    "ALIEH_DATABASE_URL",
)

SUPABASE_DB_URL_ENV = "SUPABASE_DB_URL"

_POSTGRES_SECRET_KEYS = (
    "database_url",
    "postgres_url",
    "supabase_db_url",
    "DATABASE_URL",
)


def is_public_streamlit_deploy() -> bool:
    """
    Streamlit Community Cloud coloca o repositório sob ``/mount/src/<app>/``.
    NEsse ambiente o SQLite deve ser sempre ``business.db`` (ignora secrets de dev).
    """
    try:
        return "/mount/src/" in Path(__file__).resolve().as_posix()
    except PATH_RESOLVE_ERRORS:
        return False


def is_production_db_forced_by_env() -> bool:
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
    if is_public_streamlit_deploy() or is_production_db_forced_by_env():
        return _PRODUCTION_DB_NAME

    env = (os.environ.get("ALIEH_SQLITE") or "").strip()
    if env:
        return env
    try:
        import streamlit as st

        sec = st.secrets.get("sqlite_filename")
        if sec is not None and str(sec).strip():
            return str(sec).strip()
    except STREAMLIT_CONFIG_READ_ERRORS:
        pass
    return _DEV_DEFAULT_DB_NAME


def sqlite_db_path() -> Path:
    """
    Caminho histórico do SQLite na pasta do projeto (só para ferramentas / referência).

    A aplicação usa ``database.connection.DB_PATH`` (defeito ``/data/business.db``).
    """
    return BASE_DIR / _sqlite_filename()


def _normalize_db_provider(raw: str | None) -> Literal["sqlite", "postgres"]:
    if raw is None or not str(raw).strip():
        return "sqlite"
    v = str(raw).strip().lower()
    if v in ("sqlite", "file"):
        return "sqlite"
    if v in ("postgres", "postgresql", "pg", "supabase"):
        return "postgres"
    raise ValueError(
        f"Invalid {DB_PROVIDER_ENV}={raw!r}; expected 'sqlite' or 'postgres' "
        "(or synonyms: pg, postgresql, supabase, file)."
    )


def get_database_url() -> str | None:
    """URL de ligação Postgres para **auto-detecção** (env ``DATABASE_URL`` ou segredos).

    Nunca regista o valor. Use :func:`get_postgres_dsn` para a cadeia completa de DSNs.
    """
    v = (os.environ.get(DATABASE_URL_ENV) or "").strip()
    if v:
        return v
    return _read_optional_streamlit_secret_text(
        DATABASE_URL_ENV, "database_url", "postgres_url"
    )


def get_database_provider() -> Literal["sqlite", "postgres"]:
    """Provedor efectivo: modo automático ou ``DB_PROVIDER`` explícito."""
    global _PRIMARY_SELECTION_LOGGED

    raw = (os.environ.get(DB_PROVIDER_ENV) or "").strip()
    if raw:
        provider = _normalize_db_provider(raw)
        if provider == "postgres":
            reason = "explicit DB_PROVIDER requests PostgreSQL"
        else:
            reason = "explicit DB_PROVIDER requests SQLite"
    elif get_postgres_dsn():
        provider = "postgres"
        reason = "postgres DSN configured"
    else:
        provider = "sqlite"
        reason = "fallback mode"

    if not _PRIMARY_SELECTION_LOGGED:
        _logger.info("Database selected: %s (%s)", provider, reason)
        _PRIMARY_SELECTION_LOGGED = True
    return provider


def get_db_provider() -> Literal["sqlite", "postgres"]:
    """Compatível com código existente; equivalente a :func:`get_database_provider`."""
    return get_database_provider()


def _read_optional_streamlit_secret_text(*keys: str) -> str | None:
    try:
        import streamlit as st

        for k in keys:
            sec = st.secrets.get(k)
            if sec is not None and str(sec).strip():
                return str(sec).strip()
    except STREAMLIT_CONFIG_READ_ERRORS:
        pass
    return None


def get_supabase_db_url() -> str | None:
    """URI Supabase / Postgres: variável ``SUPABASE_DB_URL`` ou segredo ``supabase_db_url``."""
    v = (os.environ.get(SUPABASE_DB_URL_ENV) or "").strip()
    if v:
        return v
    return _read_optional_streamlit_secret_text("supabase_db_url", SUPABASE_DB_URL_ENV)


def get_postgres_dsn() -> str | None:
    """
    URI de ligação Postgres se configurado (env ou secrets); não valida nem abre conexão.
    Retorna ``None`` se nenhuma fonte estiver definida.
    """
    for var in POSTGRES_DSN_ENV_VARS:
        v = (os.environ.get(var) or "").strip()
        if v:
            return v
    return _read_optional_streamlit_secret_text(*_POSTGRES_SECRET_KEYS)
