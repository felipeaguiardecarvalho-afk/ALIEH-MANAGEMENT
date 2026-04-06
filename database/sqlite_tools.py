"""Operações de ficheiro SQLite (backup, ligação por path) — todo o ``sqlite3`` directo a ficheiros fica aqui."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def sqlite_backup_file_to_file(src: Path, dest: Path) -> None:
    """Cópia consistente entre dois ficheiros (API ``backup``)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(str(src), timeout=30.0) as sconn:
            with sqlite3.connect(str(dest), timeout=30.0) as dconn:
                sconn.backup(dconn)
    except (sqlite3.Error, OSError) as exc:
        raise ConnectionError(f"Backup SQLite falhou ({src} -> {dest}): {exc}") from exc


def sqlite_connect_path(
    path: Path | str,
    *,
    row_factory: type | None = None,
    timeout: float = 30.0,
) -> sqlite3.Connection:
    """Ligação a um path arbitrário (validação, scripts). Não define PRAGMA foreign_keys."""
    try:
        conn = sqlite3.connect(str(path), timeout=timeout)
    except (sqlite3.Error, OSError) as exc:
        raise ConnectionError(f"Não foi possível abrir o ficheiro SQLite {path!s}: {exc}") from exc
    if row_factory is not None:
        conn.row_factory = row_factory
    return conn
