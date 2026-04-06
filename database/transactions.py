"""Transacções explícitas: SQLite (BEGIN…) e Postgres (psycopg ``conn.transaction()``)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import sqlite3

from database import shadow_mode

if TYPE_CHECKING:
    pass


@contextmanager
def transaction(conn: Any, *, immediate: bool = False):
    """
    SQLite: ``BEGIN [IMMEDIATE]`` … ``COMMIT`` / ``rollback`` em erro.
    Postgres: bloco transaccional nativo do psycopg (``immediate`` ignorado).
    """
    if isinstance(conn, sqlite3.Connection):
        conn.isolation_level = None
        if immediate:
            conn.execute("BEGIN IMMEDIATE;")
        else:
            conn.execute("BEGIN;")
        try:
            yield conn
        except BaseException:
            try:
                conn.rollback()
            except sqlite3.OperationalError:
                pass
            raise
        conn.execute("COMMIT;")
        return

    import psycopg

    if isinstance(conn, psycopg.Connection):
        with shadow_mode.mirrored_write_transaction(immediate):
            with conn.transaction():
                yield conn
        return

    raise TypeError(f"Tipo de conexão não suportado em transaction(): {type(conn)!r}")
