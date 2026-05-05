"""Testes da camada database.config (provedor e DSN Postgres)."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def reload_db_config(monkeypatch):
    """Isola env e recarrega database.config entre casos."""

    def _reload(**env: str):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        import database.config as cfg

        return importlib.reload(cfg)

    return _reload


def test_db_provider_defaults_sqlite(reload_db_config, monkeypatch):
    """Após import da package ``database``, ``health_check`` pode carregar ``.env``; limpar de novo."""
    cfg = reload_db_config()
    monkeypatch.delenv("DB_PROVIDER", raising=False)
    for k in ("DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_DSN", "ALIEH_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(cfg, "_read_optional_streamlit_secret_text", lambda *keys: None)
    assert cfg.get_db_provider() == "sqlite"
    assert cfg.get_database_provider() == "sqlite"
    assert cfg.get_database_url() is None


def test_get_database_provider_postgres_when_database_url_only(
    reload_db_config, monkeypatch
):
    monkeypatch.delenv("DB_PROVIDER", raising=False)
    cfg = reload_db_config(DATABASE_URL="postgresql://u:p@localhost/db")
    assert cfg.get_database_provider() == "postgres"
    assert cfg.get_database_url() == "postgresql://u:p@localhost/db"


def test_database_selected_log_fallback_mode(caplog, reload_db_config, monkeypatch):
    import logging

    monkeypatch.delenv("DB_PROVIDER", raising=False)
    for k in ("DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_DSN", "ALIEH_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    cfg = reload_db_config()
    caplog.set_level(logging.INFO, logger="database.config")
    cfg.get_database_provider()
    assert any(
        "Database selected: sqlite (fallback mode)" in r.message for r in caplog.records
    )


def test_database_selected_log_postgres_url(caplog, reload_db_config, monkeypatch):
    import logging

    monkeypatch.delenv("DB_PROVIDER", raising=False)
    cfg = reload_db_config(DATABASE_URL="postgresql://u:p@localhost/db")
    caplog.set_level(logging.INFO, logger="database.config")
    cfg.get_database_provider()
    assert any(
        "Database selected: postgres (postgres DSN configured)" in r.message
        for r in caplog.records
    )


def test_get_db_conn_raises_when_postgres_connect_fails(
    reload_db_config, monkeypatch, caplog
):
    import logging

    import psycopg

    monkeypatch.delenv("DB_PROVIDER", raising=False)
    reload_db_config(DATABASE_URL="postgresql://u:p@badhost:5432/db")
    import database.config as cfg
    import database.connection as conn

    importlib.reload(cfg)
    importlib.reload(conn)
    caplog.set_level(logging.ERROR)

    def boom(*_a, **_k):
        raise psycopg.OperationalError("simulated failure")

    with patch.object(conn.psycopg, "connect", side_effect=boom):
        with pytest.raises(ConnectionError, match="PostgreSQL connection required but failed"):
            conn.get_db_conn()
    assert any(
        "FATAL: PostgreSQL connection failed — no fallback allowed" in r.getMessage()
        for r in caplog.records
    )


def test_get_db_conn_raises_when_explicit_postgres_with_database_url(
    reload_db_config, caplog
):
    import logging

    reload_db_config(
        DB_PROVIDER="postgres",
        DATABASE_URL="postgresql://u:p@badhost:5432/db",
    )
    import database.config as cfg
    import database.connection as conn

    importlib.reload(cfg)
    importlib.reload(conn)
    caplog.set_level(logging.ERROR)

    def boom(*_a, **_k):
        raise ConnectionError("fail")

    with patch.object(conn.psycopg, "connect", side_effect=boom):
        with pytest.raises(ConnectionError, match="PostgreSQL connection required but failed"):
            conn.get_db_conn()
    assert any(
        "FATAL: PostgreSQL connection failed — no fallback allowed" in r.getMessage()
        for r in caplog.records
    )


def test_get_db_conn_no_fallback_explicit_postgres_supabase_url_only(
    reload_db_config, monkeypatch
):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reload_db_config(
        DB_PROVIDER="postgres",
        SUPABASE_DB_URL="postgresql://u:p@badhost:5432/db",
    )
    import database.config as cfg
    import database.connection as conn

    importlib.reload(cfg)
    importlib.reload(conn)

    def boom(*_a, **_k):
        raise ConnectionError("fail")

    with patch.object(conn.psycopg, "connect", side_effect=boom):
        with pytest.raises(ConnectionError):
            conn.get_db_conn()


def test_db_provider_postgres_synonyms(reload_db_config):
    for raw in ("postgres", "POSTGRES", "pg", "supabase"):
        cfg = reload_db_config(DB_PROVIDER=raw)
        assert cfg.get_db_provider() == "postgres"


def test_db_provider_invalid(reload_db_config):
    cfg = reload_db_config(DB_PROVIDER="mysql")
    with pytest.raises(ValueError, match="Invalid DB_PROVIDER"):
        cfg.get_db_provider()


def test_get_postgres_dsn_from_env(reload_db_config, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    cfg = reload_db_config()
    assert cfg.get_postgres_dsn() is None

    cfg = reload_db_config(SUPABASE_DB_URL="postgresql://u:p@localhost/db")
    assert cfg.get_postgres_dsn() == "postgresql://u:p@localhost/db"
    assert cfg.get_supabase_db_url() == "postgresql://u:p@localhost/db"


def test_get_postgres_conn_uses_supabase_url(reload_db_config, monkeypatch):
    for k in ("DATABASE_URL", "POSTGRES_DSN", "ALIEH_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    reload_db_config(SUPABASE_DB_URL="postgresql://user:pass@localhost:5432/db")
    for k in ("DATABASE_URL", "POSTGRES_DSN", "ALIEH_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    import database.connection as conn

    importlib.reload(conn)
    mock = MagicMock()
    with patch.object(conn.psycopg, "connect", return_value=mock) as p:
        out = conn.get_postgres_conn()
        assert out is mock
        p.assert_called_once()
        assert p.call_args.args[0] == "postgresql://user:pass@localhost:5432/db?sslmode=require"
        assert p.call_args.kwargs.get("autocommit") is True
        assert p.call_args.kwargs.get("connect_timeout") == 15
        assert p.call_args.kwargs.get("keepalives") == 1
        assert p.call_args.kwargs.get("keepalives_idle") == 30
        assert p.call_args.kwargs.get("keepalives_interval") == 10
        assert p.call_args.kwargs.get("keepalives_count") == 5
        assert p.call_args.kwargs.get("prepare_threshold") == 0
        assert p.call_args.kwargs.get("sslmode") == "require"


def test_get_postgres_conn_prefers_database_url(reload_db_config):
    reload_db_config(
        DATABASE_URL="postgresql://a:a@db/from-database-url",
        SUPABASE_DB_URL="postgresql://user:pass@localhost:5432/db",
    )
    import database.connection as conn

    importlib.reload(conn)
    mock = MagicMock()
    with patch.object(conn.psycopg, "connect", return_value=mock) as p:
        conn.get_postgres_conn()
        assert p.call_args.args[0] == "postgresql://a:a@db/from-database-url?sslmode=require"


def test_get_postgres_conn_preserves_existing_sslmode(reload_db_config, monkeypatch):
    for k in ("DATABASE_URL", "POSTGRES_DSN", "ALIEH_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    reload_db_config(
        SUPABASE_DB_URL="postgresql://user:pass@localhost:5432/db?sslmode=verify-full"
    )
    for k in ("DATABASE_URL", "POSTGRES_DSN", "ALIEH_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    import database.connection as conn

    importlib.reload(conn)
    mock = MagicMock()
    with patch.object(conn.psycopg, "connect", return_value=mock) as p:
        conn.get_postgres_conn()
        assert p.call_args.args[0] == (
            "postgresql://user:pass@localhost:5432/db?sslmode=verify-full"
        )
        assert p.call_args.kwargs.get("sslmode") == "verify-full"


def test_get_postgres_conn_uses_fixed_connect_timeout_and_keepalives(
    reload_db_config, monkeypatch
):
    """Defeito 15s; ``DATABASE_CONNECT_TIMEOUT`` legado não altera psycopg; ``POSTGRES_CONNECT_TIMEOUT`` sim."""
    for k in ("DATABASE_URL", "POSTGRES_DSN", "ALIEH_DATABASE_URL", "POSTGRES_CONNECT_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)
    reload_db_config(
        SUPABASE_DB_URL="postgresql://user:pass@localhost:5432/db",
        DATABASE_CONNECT_TIMEOUT="45",
    )
    for k in ("DATABASE_URL", "POSTGRES_DSN", "ALIEH_DATABASE_URL", "POSTGRES_CONNECT_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)
    import database.connection as conn

    importlib.reload(conn)
    mock = MagicMock()
    with patch.object(conn.psycopg, "connect", return_value=mock) as p:
        conn.get_postgres_conn()
        assert p.call_args.args[0] == "postgresql://user:pass@localhost:5432/db?sslmode=require"
        assert p.call_args.kwargs.get("connect_timeout") == 15
        assert p.call_args.kwargs.get("keepalives") == 1

    monkeypatch.setenv("POSTGRES_CONNECT_TIMEOUT", "45")
    reload_db_config(SUPABASE_DB_URL="postgresql://user:pass@localhost:5432/db")
    for k in ("DATABASE_URL", "POSTGRES_DSN", "ALIEH_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    importlib.reload(conn)
    mock = MagicMock()
    with patch.object(conn.psycopg, "connect", return_value=mock) as p:
        conn.get_postgres_conn()
        assert p.call_args.kwargs.get("connect_timeout") == 45


def test_get_postgres_conn_strips_wrapping_quotes_on_database_url(reload_db_config, monkeypatch):
    reload_db_config(DATABASE_URL="'postgresql://u:p@localhost/db'")
    import database.connection as conn

    importlib.reload(conn)
    mock = MagicMock()
    with patch.object(conn.psycopg, "connect", return_value=mock) as p:
        conn.get_postgres_conn()
        assert p.call_args.args[0] == "postgresql://u:p@localhost/db?sslmode=require"


def test_get_database_provider_postgres_when_supabase_url_only_no_database_url(
    reload_db_config, monkeypatch
):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    cfg = reload_db_config(SUPABASE_DB_URL="postgresql://u:p@localhost/db")
    assert cfg.get_database_provider() == "postgres"


