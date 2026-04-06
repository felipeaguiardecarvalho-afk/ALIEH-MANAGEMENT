"""Tipos de excepção de drivers de BD para ``except`` sem espalhar ``sqlite3`` fora de ``database/``."""

from __future__ import annotations

import sqlite3

try:
    import psycopg

    DB_DRIVER_ERRORS: tuple[type[BaseException], ...] = (sqlite3.Error, psycopg.Error)
except ImportError:  # pragma: no cover
    DB_DRIVER_ERRORS = (sqlite3.Error,)
