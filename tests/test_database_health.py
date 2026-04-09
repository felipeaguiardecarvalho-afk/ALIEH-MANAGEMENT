"""Saúde da BD: SELECT 1, arranque e verificação periódica."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def reload_conn(monkeypatch):
    def _inner(**env: str):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        import database.config as cfg
        import database.connection as conn

        importlib.reload(cfg)
        importlib.reload(conn)
        return conn

    return _inner


def test_check_database_health_returns_true_when_postgres_ok(reload_conn, monkeypatch):
    conn_mod = reload_conn(
        DB_PROVIDER="postgres",
        SUPABASE_DB_URL="postgresql://u:p@localhost/db",
    )

    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = {"ok": 1}
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value = cur

    with patch.object(conn_mod, "get_db_conn", return_value=mock_conn):
        assert conn_mod.check_database_health() is True


def test_check_database_health_propagates_get_db_conn_failure(reload_conn, monkeypatch):
    conn = reload_conn(
        DB_PROVIDER="postgres",
        SUPABASE_DB_URL="postgresql://u:p@localhost/db",
    )

    def boom():
        raise RuntimeError("no db")

    with patch.object(conn, "get_db_conn", side_effect=boom):
        with pytest.raises(RuntimeError, match="no db"):
            conn.check_database_health()


def test_maybe_periodic_skips_when_interval_zero(reload_conn, monkeypatch):
    conn = reload_conn()
    monkeypatch.delenv("DATABASE_HEALTH_INTERVAL_SECONDS", raising=False)
    called: list[bool] = []

    monkeypatch.setattr(conn, "check_database_health", lambda **k: called.append(True))
    conn.maybe_run_periodic_database_health()
    assert called == []


def test_maybe_periodic_respects_interval(reload_conn, monkeypatch):
    conn = reload_conn()
    monkeypatch.setenv("DATABASE_HEALTH_INTERVAL_SECONDS", "30")
    called: list[bool] = []

    monkeypatch.setattr(conn, "check_database_health", lambda **k: called.append(True))

    with patch.object(conn.time, "monotonic", side_effect=[100.0, 115.0, 200.0]):
        conn.maybe_run_periodic_database_health()
        assert len(called) == 1
        conn.maybe_run_periodic_database_health()
        assert len(called) == 1
        conn.maybe_run_periodic_database_health()
        assert len(called) == 2


def test_run_database_init_calls_check_health(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PROVIDER", "postgres")
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://u:p@localhost/db")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ALIEH_SKIP_POSTGRES_STARTUP_PROBE", "1")

    import database.config as cfg
    import database.connection as conn
    import services.db_startup as dbs

    importlib.reload(cfg)
    importlib.reload(conn)

    idb_mod = importlib.import_module("database.init_db")
    monkeypatch.setattr(idb_mod, "init_db", lambda: None)

    importlib.reload(dbs)

    called: list[bool] = []

    def track():
        called.append(True)

    conn_mod = importlib.import_module("database.connection")
    monkeypatch.setattr(conn_mod, "check_database_health", track)
    dbs.run_database_init()
    assert called == [True]
