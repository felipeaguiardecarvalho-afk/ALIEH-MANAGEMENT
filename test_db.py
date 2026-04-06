"""Script legado: lista tabelas do ficheiro ``database.db`` na raiz do projecto (se existir)."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

from database.config import BASE_DIR
from database.sqlite_tools import sqlite_connect_path

_db = BASE_DIR / "database.db"
if not _db.is_file():
    print("Ficheiro não encontrado:", _db)
    raise SystemExit(1)

with closing(sqlite_connect_path(_db)) as conn:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cur.fetchall()

print("Tabelas no banco:", tables)
