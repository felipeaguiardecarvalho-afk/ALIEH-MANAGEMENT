"""Operações administrativas sobre o ficheiro SQLite (sem SQL na app)."""

from __future__ import annotations

from pathlib import Path


def get_sqlite_db_path() -> Path:
    from database.connection import DB_PATH

    return DB_PATH
