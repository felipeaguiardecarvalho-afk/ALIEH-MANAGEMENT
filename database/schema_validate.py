"""Validar que o schema PostgreSQL ``public`` está completo (paridade com :file:`schema.sql`)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from database.connection import get_postgres_conn
from database.schema_apply import list_public_base_tables

_logger = logging.getLogger(__name__)

# Tabelas base definidas em schema.sql (ordem alfabética só para leitura humana).
EXPECTED_CORE_TABLES: frozenset[str] = frozenset(
    (
        "app_schema_migrations",
        "customer_sequence_counter",
        "customers",
        "login_attempt_audit",
        "login_user_throttle",
        "price_history",
        "products",
        "sale_sequence_counter",
        "sales",
        "sku_cost_components",
        "sku_deletion_audit",
        "sku_master",
        "sku_pricing_records",
        "sku_sequence_counter",
        "stock_cost_entries",
        "uat_manual_checklist",
        "users",
    )
)


@dataclass(frozen=True)
class PostgresSchemaValidationResult:
    """Resultado de :func:`validate_postgres_schema`."""

    ok: bool
    """Todas as tabelas obrigatórias existem em ``public``."""

    tables: tuple[str, ...]
    """Tabelas base em ``public`` (ordenadas)."""

    required: frozenset[str]
    """Conjunto esperado (obrigatório)."""

    missing: tuple[str, ...]
    """Tabelas obrigatórias em falta."""

    extra: tuple[str, ...]
    """Tabelas em ``public`` que não estão na lista obrigatória (informativo)."""


def validate_postgres_schema(
    *,
    required_tables: frozenset[str] | None = None,
) -> PostgresSchemaValidationResult:
    """
    Liga ao Postgres, lista tabelas ``BASE TABLE`` em ``public`` e confirma as principais.

    Regista no log a lista completa, contagem, obrigatórias em falta (se houver) e PASS/FAIL.
    """
    required = (
        required_tables if required_tables is not None else EXPECTED_CORE_TABLES
    )
    _logger.info("Validating PostgreSQL schema (public)...")

    with get_postgres_conn() as conn:
        found = list_public_base_tables(conn)

    found_set = set(found)
    missing = sorted(required - found_set)
    extra = sorted(found_set - required)
    ok = len(missing) == 0

    _logger.info(
        "PostgreSQL public: %d base table(s): %s",
        len(found),
        ", ".join(found) if found else "(none)",
    )
    _logger.info(
        "Core tables expected: %d; present: %d",
        len(required),
        len(required) - len(missing),
    )
    if missing:
        _logger.error(
            "PostgreSQL schema validation: FAIL — missing table(s): %s",
            ", ".join(missing),
        )
    else:
        _logger.info("PostgreSQL schema validation: PASS — all core tables present")
    if extra:
        _logger.info(
            "Additional tables in public (not in core list): %s",
            ", ".join(extra),
        )

    return PostgresSchemaValidationResult(
        ok=ok,
        tables=tuple(found),
        required=required,
        missing=tuple(missing),
        extra=tuple(extra),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    validate_postgres_schema()
