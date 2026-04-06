"""Arranque da camada de persistência (só chamado a partir do entrypoint da app)."""

from __future__ import annotations


def run_database_init() -> None:
    from database.connection import check_database_health
    from database.health_check import schedule_postgres_connectivity_probe_on_startup
    from database.init_db import init_db

    init_db()
    check_database_health()
    schedule_postgres_connectivity_probe_on_startup()
