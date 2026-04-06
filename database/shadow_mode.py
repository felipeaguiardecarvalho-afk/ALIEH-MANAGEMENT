"""Modo *shadow*: Postgres como fonte de verdade; mesma transacção replicada em SQLite (opt-in).

Activar com ``ALIEH_DB_SHADOW_MODE=1`` e ``ALIEH_DB_SHADOW_SQLITE`` = caminho do ``.db``
espelho (schema alinhado ao SQLite da app). Falhas no SQLite **não** afectam o fluxo em
Postgres — registo a ERROR. Divergências de ``rowcount`` em escritos em série
(INSERT/UPDATE/DELETE) logam WARNING.

Limitações:

- Transacções aninhadas em Postgres (savepoints) não têm espelho 1:1 no SQLite; o espelho
  usa uma única transacção plana — possíveis falsos positivos em fluxos com rollback parcial.
- Parâmetros só posicionais (``?``); ``Mapping`` em :func:`db_execute` não é replicado.
- Leituras fora de :func:`~database.repositories.session.write_transaction` não são espelhadas.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

_ENV_MODE = "ALIEH_DB_SHADOW_MODE"
_ENV_SQLITE = "ALIEH_DB_SHADOW_SQLITE"

_shadow_sqlite_conn_var: ContextVar[sqlite3.Connection | None] = ContextVar(
    "shadow_sqlite_conn", default=None
)
_shadow_depth_var: ContextVar[int] = ContextVar("shadow_depth", default=0)


def is_shadow_mode_enabled() -> bool:
    v = (os.environ.get(_ENV_MODE) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def shadow_sqlite_path() -> Path | None:
    raw = (os.environ.get(_ENV_SQLITE) or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def get_active_shadow_connection() -> sqlite3.Connection | None:
    return _shadow_sqlite_conn_var.get()


def _preview(sql: str, limit: int = 200) -> str:
    return " ".join(str(sql).split())[:limit]


def _open_shadow() -> sqlite3.Connection:
    p = shadow_sqlite_path()
    if p is None:
        raise RuntimeError("ALIEH_DB_SHADOW_SQLITE não definido")
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def mirrored_write_transaction(immediate: bool) -> Iterator[None]:
    """Envolve a transacção de escrita Postgres com BEGIN/COMMIT paralelos no SQLite."""
    if not is_shadow_mode_enabled():
        yield
        return

    depth = _shadow_depth_var.get()
    if depth > 0:
        _shadow_depth_var.set(depth + 1)
        try:
            yield
        finally:
            _shadow_depth_var.set(depth)
        return

    p = shadow_sqlite_path()
    if p is None:
        _logger.warning(
            "%s activo mas %s não definido — espelho SQLite desactivado.",
            _ENV_MODE,
            _ENV_SQLITE,
        )
        yield
        return

    sconn = _open_shadow()
    token: Token = _shadow_sqlite_conn_var.set(sconn)
    _shadow_depth_var.set(1)
    try:
        if immediate:
            sconn.execute("BEGIN IMMEDIATE;")
        else:
            sconn.execute("BEGIN;")
        yield
    except BaseException:
        try:
            sconn.rollback()
        except sqlite3.Error:
            pass
        raise
    else:
        try:
            sconn.execute("COMMIT;")
        except sqlite3.Error as exc:
            _logger.error(
                "shadow SQLite COMMIT falhou (Postgres já consolidou). %s",
                exc,
                exc_info=True,
            )
    finally:
        _shadow_depth_var.set(0)
        _shadow_sqlite_conn_var.reset(token)
        try:
            sconn.close()
        except sqlite3.Error:
            pass


def replay_statement(
    sql_qmarks: str,
    params: Sequence[Any] | Mapping[str, Any],
    *,
    pg_cursor: Any | None = None,
) -> None:
    """Reexecuta ``sql_qmarks`` com ``?`` no SQLite da sombra e compara ``rowcount``."""
    sconn = get_active_shadow_connection()
    if sconn is None:
        return
    if isinstance(params, Mapping):
        _logger.warning(
            "shadow replay ignorado (parâmetros como dict; usar tupla para espelho) | %s",
            _preview(sql_qmarks),
        )
        return
    try:
        scur = sconn.execute(sql_qmarks, params)
    except Exception as exc:
        _logger.error(
            "shadow replay falhou no SQLite | %s | %s: %s",
            _preview(sql_qmarks),
            type(exc).__name__,
            exc,
            exc_info=exc,
        )
        return

    if pg_cursor is None:
        return
    try:
        pr = int(pg_cursor.rowcount)
        sr = int(scur.rowcount)
    except (TypeError, ValueError):
        return
    if pr < 0 or sr < 0:
        return
    if pr != sr:
        _logger.warning(
            "shadow divergência rowcount postgres=%s sqlite=%s | %s",
            pr,
            sr,
            _preview(sql_qmarks),
        )
