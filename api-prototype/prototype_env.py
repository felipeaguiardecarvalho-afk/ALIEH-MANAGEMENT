"""Ambiente canónico (development / staging / production) e validação no arranque da api-prototype."""

from __future__ import annotations

import logging
import os

_logger = logging.getLogger("alieh.prototype.env")


def alieh_runtime_env() -> str:
    """``development`` | ``staging`` | ``production`` — espelha a lógica do Next (`ALIEH_ENV` / `VERCEL_ENV`)."""
    explicit = (os.environ.get("ALIEH_ENV") or os.environ.get("API_PROTOTYPE_ENV") or "").strip().lower()
    if explicit in ("production", "prod"):
        return "production"
    if explicit in ("staging", "stg", "preview"):
        return "staging"
    if explicit in ("development", "dev"):
        return "development"
    return "development"


def is_production_runtime() -> bool:
    if alieh_runtime_env() == "production":
        return True
    # Paridade com Next: arranques com NODE_ENV=production sem ALIEH_ENV explícito.
    return (os.environ.get("NODE_ENV") or "").strip().lower() == "production"


def validate_production_environment() -> None:
    """Falha rápido em tier produção se faltar DSN ou config insegura."""
    if not is_production_runtime():
        return
    dsn = (os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not dsn:
        raise RuntimeError(
            "Tier produção (api-prototype: ALIEH_ENV=production ou NODE_ENV=production): "
            "defina DATABASE_URL ou SUPABASE_DB_URL. A API não deve arrancar sem base de dados configurada."
        )
    open_raw = (os.environ.get("ALIEH_PROTOTYPE_OPEN") or "").strip()
    if open_raw != "0":
        val = repr(open_raw) if open_raw else "(ausente)"
        raise RuntimeError(
            "Tier produção (api-prototype): defina ALIEH_PROTOTYPE_OPEN=0. "
            f"Valor actual: {val}"
        )
    _logger.info(
        "production_env_validated",
        extra={"alieh_env": "production", "database_configured": True},
    )


def validate_staging_environment() -> None:
    """Homologação / preview: exige DSN para não servir tráfego sem persistência configurada."""
    if alieh_runtime_env() != "staging":
        return
    dsn = (os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not dsn:
        raise RuntimeError(
            "ALIEH_ENV=staging (api-prototype): defina DATABASE_URL ou SUPABASE_DB_URL antes de servir tráfego."
        )
    _logger.info("staging_env_validated", extra={"alieh_env": "staging", "database_configured": True})


def validate_runtime_environment() -> None:
    """Chamado no lifespan antes de servir tráfego."""
    validate_production_environment()
    validate_staging_environment()
