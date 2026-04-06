"""Camada de repositórios (padrão get/create/update/delete; ``conn`` ou ``get_db_conn`` via :func:`use_connection`)."""

from __future__ import annotations

from database.repositories import customer_repository
from database.repositories import product_repository
from database.repositories import query_repository
from database.repositories import sales_repository
from database.repositories import user_repository
from database.repositories.session import connection_scope, write_transaction
from database.repositories.support import use_connection

__all__ = [
    "connection_scope",
    "customer_repository",
    "product_repository",
    "query_repository",
    "sales_repository",
    "user_repository",
    "use_connection",
    "write_transaction",
]
