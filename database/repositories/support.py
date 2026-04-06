"""Suporte partilhado da camada de repositórios."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from database.connection import DbConnection, get_db_conn


@contextmanager
def use_connection(conn: DbConnection | None) -> Iterator[DbConnection]:
    """
    ``conn`` explícito (transacção do chamador) ou nova ligação via :func:`~database.connection.get_db_conn`.
    """
    if conn is None:
        with get_db_conn() as c:
            yield c
    else:
        yield conn
