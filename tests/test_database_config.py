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
    monkeypatch.delenv("DATABASE_URL", raising=False)
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
        "Database selected: postgres (DATABASE_URL detected)" in r.message
        for r in caplog.records
    )


def test_get_db_conn_fallback_sqlite_when_postgres_fails(
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
    caplog.set_level(logging.INFO)

    def boom(*_a, **_k):
        raise psycopg.OperationalError("simulated failure")

    with patch.object(conn.psycopg, "connect", side_effect=boom):
        with conn.get_db_conn() as c:
            assert c.execute("SELECT 1").fetchone()[0] == 1
    messages = [r.getMessage() for r in caplog.records]
    assert any("Database selected: postgres (DATABASE_URL detected)" == m for m in messages)
    assert any(
        "PostgreSQL connection failed" in m and "fallback" in m.lower() for m in messages
    )
    assert any(
        "Database selected: sqlite (PostgreSQL connection failed; using fallback)" == m
        for m in messages
    )
    assert any("Primary database: PostgreSQL" in m for m in messages)
    assert any("Fallback activated: SQLite" in m for m in messages)


def test_get_db_conn_fallback_when_explicit_postgres_with_database_url(
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
    caplog.set_level(logging.INFO)

    def boom(*_a, **_k):
        raise ConnectionError("fail")

    with patch.object(conn.psycopg, "connect", side_effect=boom):
        with conn.get_db_conn() as c:
            assert c.execute("SELECT 1").fetchone()[0] == 1
    messages = [r.getMessage() for r in caplog.records]
    assert any("Primary database: PostgreSQL" in m for m in messages)
    assert any("Fallback activated: SQLite" in m for m in messages)


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


def test_get_conn_rejects_postgres_provider(reload_db_config):
    reload_db_config(DB_PROVIDER="postgres")
    import database.connection as conn

    importlib.reload(conn)
    with pytest.raises(RuntimeError, match="SQLite-only"):
        conn.get_conn()


def test_get_conn_sqlite_after_revert(reload_db_config, tmp_path):
    """Com sqlite activo, get_conn abre o ficheiro configurado."""
    reload_db_config(DB_PROVIDER="sqlite", ALIEH_SQLITE=str(tmp_path / "t.db"))
    import database.connection as conn

    importlib.reload(conn)
    with conn.get_conn() as c:
        assert c.execute("SELECT 1").fetchone()[0] == 1


def test_get_db_conn_matches_sqlite_path(reload_db_config, tmp_path):
    reload_db_config(DB_PROVIDER="sqlite", ALIEH_SQLITE=str(tmp_path / "unified.db"))
    import database.connection as conn

    importlib.reload(conn)
    with conn.get_db_conn() as c:
        assert c.execute("SELECT 1").fetchone()[0] == 1


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
        assert p.call_args.kwargs.get("connect_timeout") == 30
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


def test_get_postgres_conn_connect_timeout_env(reload_db_config, monkeypatch):
    for k in ("DATABASE_URL", "POSTGRES_DSN", "ALIEH_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    reload_db_config(
        SUPABASE_DB_URL="postgresql://user:pass@localhost:5432/db",
        DATABASE_CONNECT_TIMEOUT="45",
    )
    for k in ("DATABASE_URL", "POSTGRES_DSN", "ALIEH_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    import database.connection as conn

    importlib.reload(conn)
    mock = MagicMock()
    with patch.object(conn.psycopg, "connect", return_value=mock) as p:
        conn.get_postgres_conn()
        assert p.call_args.args[0] == "postgresql://user:pass@localhost:5432/db?sslmode=require"
        assert p.call_args.kwargs.get("connect_timeout") == 45


def test_log_using_database_sqlite(caplog, reload_db_config, tmp_path):
    import logging

    reload_db_config(DB_PROVIDER="sqlite", ALIEH_SQLITE=str(tmp_path / "logt.db"))
    import database.connection as conn

    importlib.reload(conn)
    caplog.set_level(logging.INFO, logger=conn.__name__)
    with conn.get_db_conn() as c:
        assert c.execute("SELECT 1").fetchone()[0] == 1
    assert any("Active database backend=sqlite" in r.message for r in caplog.records)
