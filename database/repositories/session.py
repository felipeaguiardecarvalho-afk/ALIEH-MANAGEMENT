"""Sessão de escrita transaccional (apenas dentro da camada ``database``).

``services`` devem usar este módulo em vez de ``use_connection`` + ``transaction``
directos — mantém o fluxo app → services → repositories/DB.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from database.connection import DbConnection
from database.repositories.support import use_connection
from database.transactions import transaction

if TYPE_CHECKING:
    pass


@contextmanager
def connection_scope(conn: DbConnection | None = None) -> Iterator[DbConnection]:
    """Ligação sem ``BEGIN`` explícito (cada ``execute`` no SQLite em modo autocommit)."""
    with use_connection(conn) as c:
        yield c


@contextmanager
def write_transaction(
    conn: DbConnection | None = None,
    *,
    immediate: bool = False,
) -> Iterator[DbConnection]:
    """Nova ligação (se ``conn`` é None) + transaccão; ou só transaccão sobre ``conn``."""
    if conn is not None:
        with transaction(conn, immediate=immediate):
            yield conn
        return
    with use_connection(None) as c:
        with transaction(c, immediate=immediate):
            yield c
