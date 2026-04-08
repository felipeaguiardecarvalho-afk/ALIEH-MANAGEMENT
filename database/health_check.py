"""Teste isolado de conectividade PostgreSQL (ex.: Supabase).

Não altera :func:`database.connection.get_db_conn` nem o motor activo da aplicação.
Usa :func:`database.connection.get_postgres_conn` com ``silent_probe=True`` para evitar
logs de selecção de base de dados do processo principal.

No arranque, :func:`schedule_postgres_connectivity_probe_on_startup` corre o teste
em **thread daemon** (não bloqueia). Para desactivar: ``ALIEH_SKIP_POSTGRES_STARTUP_PROBE=1``.

Linha de comando::

    python -m database.health_check
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Raiz do repositório (database/ → parents[1]); não sobrescreve variáveis já definidas.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
logging.getLogger(__name__).info(
    "DATABASE_URL detected: %s",
    "yes" if (os.environ.get("DATABASE_URL") or "").strip() else "no",
)

import sys
import threading

_logger = logging.getLogger(__name__)

SKIP_POSTGRES_STARTUP_PROBE_ENV = "ALIEH_SKIP_POSTGRES_STARTUP_PROBE"


def test_postgres_connection() -> bool:
    """
    Abre uma ligação Postgres (timeout configurado em :mod:`database.connection`),
    executa ``SELECT 1``, fecha.

    Returns:
        ``True`` se o comando obteve uma linha; ``False`` em qualquer falha
        (DSN em falta, rede, SQL, etc.). Nunca expõe credenciais nos logs.
    """
    try:
        from database.config import get_postgres_dsn

        if not get_postgres_dsn():
            _logger.warning("PostgreSQL connection FAILED: DSN not configured")
            return False

        from database.connection import get_postgres_conn

        with get_postgres_conn(silent_probe=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1", prepare=False)
                row = cur.fetchone()
                if row is None:
                    _logger.warning("PostgreSQL connection FAILED: empty SELECT 1")
                    return False
        _logger.info("PostgreSQL connection OK")
        return True
    except Exception as exc:
        _logger.warning(
            "PostgreSQL connection FAILED: %s",
            type(exc).__name__,
        )
        return False


def schedule_postgres_connectivity_probe_on_startup() -> None:
    """Agenda :func:`test_postgres_connection` em thread daemon — visibilidade Postgres sem bloquear a app.

    Qualquer falha fica só em log; nunca propaga excepção para o chamador. Respeita
    ``ALIEH_SKIP_POSTGRES_STARTUP_PROBE`` para ambientes que não devem lançar threads.
    """
    raw = (os.environ.get(SKIP_POSTGRES_STARTUP_PROBE_ENV) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return

    def _run() -> None:
        try:
            test_postgres_connection()
        except Exception:
            _logger.exception("PostgreSQL startup probe failed unexpectedly")

    threading.Thread(
        target=_run,
        daemon=True,
        name="alieh-pg-connectivity-probe",
    ).start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ok = test_postgres_connection()
    sys.exit(0 if ok else 1)
