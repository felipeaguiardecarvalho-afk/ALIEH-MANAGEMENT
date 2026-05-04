"""Optional strict startup checks for api-prototype."""

from __future__ import annotations

import logging
import os

from prototype_env import validate_runtime_environment

_logger = logging.getLogger("alieh.prototype.startup")


def validate_prototype_startup() -> None:
    """Validação de ambiente + opcionalmente ligação à BD se ``API_PROTOTYPE_STRICT_STARTUP``."""
    validate_runtime_environment()
    raw = (os.environ.get("API_PROTOTYPE_STRICT_STARTUP") or "").strip().lower()
    if raw not in ("1", "true", "yes", "on"):
        return
    try:
        from database.connection import check_database_health

        check_database_health()
    except Exception as e:
        raise RuntimeError(
            "API_PROTOTYPE_STRICT_STARTUP: base de dados inacessível. "
            "Defina DATABASE_URL / SUPABASE_DB_URL ou desactive API_PROTOTYPE_STRICT_STARTUP."
        ) from e
    _logger.info("startup_db_ok", extra={"strict": True})
