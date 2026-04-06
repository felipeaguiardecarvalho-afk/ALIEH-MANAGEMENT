"""Teste isolado Supabase/Postgres (database.health_check) sem ligar à rede real por defeito."""

from __future__ import annotations

import importlib
import logging
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def reload_health(monkeypatch):
    def _inner(**env: str):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        import database.config as cfg
        import database.connection as conn
        import database.health_check as hc

        importlib.reload(cfg)
        importlib.reload(conn)
        importlib.reload(hc)
        return hc, conn

    return _inner


def test_test_postgres_connection_ok(reload_health, monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://u:p@localhost:5432/db")
    hc, conn = reload_health()

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_cur = MagicMock()
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchone.return_value = (1,)
    mock_conn.cursor.return_value = mock_cur

    with patch.object(conn, "get_postgres_conn", return_value=mock_conn):
        assert hc.test_postgres_connection() is True


def test_test_postgres_connection_ok_logs(caplog, reload_health, monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://u:p@localhost:5432/db")
    hc, conn = reload_health()
    caplog.set_level(logging.INFO)

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_cur = MagicMock()
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchone.return_value = {"?column?": 1}
    mock_conn.cursor.return_value = mock_cur

    with patch.object(conn, "get_postgres_conn", return_value=mock_conn):
        assert hc.test_postgres_connection() is True
    assert any("PostgreSQL connection OK" in r.message for r in caplog.records)


def test_test_postgres_connection_failure_logs_summary(caplog, reload_health, monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://u:p@localhost:5432/db")
    hc, conn = reload_health()
    caplog.set_level(logging.WARNING)

    def boom(**_k):
        raise ConnectionError("x")

    with patch.object(conn, "get_postgres_conn", side_effect=boom):
        assert hc.test_postgres_connection() is False
    assert any(
        "PostgreSQL connection FAILED: ConnectionError" in r.message
        for r in caplog.records
    )


def test_get_postgres_conn_silent_probe_skips_using_database_log(
    caplog, reload_db_config, monkeypatch
):
    """Regressão: probe não deve marcar «Active database backend=postgresql»."""
    import logging

    monkeypatch.delenv("DB_PROVIDER", raising=False)
    reload_db_config(SUPABASE_DB_URL="postgresql://user:pass@localhost:5432/db")
    import database.connection as conn

    importlib.reload(conn)
    caplog.set_level(logging.INFO)
    mock = MagicMock()
    with patch.object(conn.psycopg, "connect", return_value=mock):
        out = conn.get_postgres_conn(silent_probe=True)
    assert out is mock
    assert not any(
        "Active database backend=postgresql" in r.message for r in caplog.records
    )


def test_schedule_postgres_probe_skipped_when_skip_env(reload_health, monkeypatch):
    monkeypatch.setenv("ALIEH_SKIP_POSTGRES_STARTUP_PROBE", "1")
    hc, _ = reload_health()
    called: list[bool] = []

    monkeypatch.setattr(hc, "test_postgres_connection", lambda: called.append(True))
    hc.schedule_postgres_connectivity_probe_on_startup()
    assert called == []


def test_schedule_postgres_probe_starts_daemon_thread(reload_health, monkeypatch):
    from unittest.mock import MagicMock

    monkeypatch.delenv("ALIEH_SKIP_POSTGRES_STARTUP_PROBE", raising=False)
    hc, _ = reload_health()
    mock_thread = MagicMock()
    monkeypatch.setattr(hc.threading, "Thread", mock_thread)
    hc.schedule_postgres_connectivity_probe_on_startup()
    mock_thread.assert_called_once()
    assert mock_thread.call_args.kwargs.get("daemon") is True
    assert mock_thread.return_value.start.called


def test_test_postgres_connection_no_dsn(caplog, reload_health, monkeypatch):
    for k in ("DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_DSN", "ALIEH_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    hc, _ = reload_health()
    for k in ("DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_DSN", "ALIEH_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    import database.config as cfg

    monkeypatch.setattr(cfg, "_read_optional_streamlit_secret_text", lambda *keys: None)
    caplog.set_level(logging.WARNING)
    assert hc.test_postgres_connection() is False
    assert any("PostgreSQL connection FAILED: DSN not configured" in r.getMessage() for r in caplog.records)


# reload_db_config from test_database_config - duplicate minimal fixture
@pytest.fixture
def reload_db_config(monkeypatch):
    def _reload(**env: str):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        import database.config as cfg

        return importlib.reload(cfg)

    return _reload
