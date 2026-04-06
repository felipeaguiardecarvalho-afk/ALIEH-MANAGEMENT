"""Saúde da BD: SELECT 1, arranque e verificação periódica."""

from __future__ import annotations

import importlib
from unittest.mock import patch

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


def test_check_database_health_returns_true_for_sqlite(
    reload_conn, monkeypatch, tmp_path
):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    conn = reload_conn(DB_PROVIDER="sqlite", ALIEH_SQLITE=str(tmp_path / "health.db"))
    assert conn.check_database_health() is True


def test_check_database_health_no_fallback_explicit_postgres(reload_conn, monkeypatch):
    conn = reload_conn(
        DB_PROVIDER="postgres",
        SUPABASE_DB_URL="postgresql://u:p@localhost/db",
    )

    def boom():
        raise RuntimeError("no db")

    with patch.object(conn, "get_db_conn", side_effect=boom):
        assert conn.check_database_health() is False


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
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_PROVIDER", "sqlite")
    monkeypatch.setenv("ALIEH_SQLITE", str(tmp_path / "startup.db"))
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

    def track(**_k):
        called.append(True)

    conn_mod = importlib.import_module("database.connection")
    monkeypatch.setattr(conn_mod, "check_database_health", track)
    dbs.run_database_init()
    assert called == [True]
