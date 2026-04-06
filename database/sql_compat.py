"""Compatibilidade SQL SQLite ↔ PostgreSQL (placeholders e fragmentos portáveis).

- Placeholders: ``?`` (SQLite) vs ``%s`` (psycopg) — usar :func:`db_execute`.
- Não altera a semântica das queries; apenas o formato de bind e pequenos fragmentos
  expostos como :func:`sql_order_ci`.

No SQLite, o tempo e falhas de ``execute`` são registados em
:class:`database.timed_sqlite.TimedSqliteConnection`. Aqui regista-se duração e erros em
``db_execute`` / ``run_insert_returning_id`` para Postgres (placeholders ``%s``).
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from collections.abc import Mapping, Sequence
from typing import Any

from database.config import get_db_provider
from database import shadow_mode

_logger = logging.getLogger(__name__)


def _pg_info_ms_threshold() -> float:
    try:
        return float((os.environ.get("ALIEH_DB_QUERY_INFO_MS") or "100").strip())
    except ValueError:
        return 100.0


def _pg_warn_ms_threshold() -> float:
    try:
        return float((os.environ.get("ALIEH_DB_QUERY_WARN_MS") or "1000").strip())
    except ValueError:
        return 1000.0

try:
    import psycopg.errors

    INTEGRITY_VIOLATION_ERRORS: tuple[type[BaseException], ...] = (
        sqlite3.IntegrityError,
        psycopg.errors.UniqueViolation,
    )
except ImportError:
    INTEGRITY_VIOLATION_ERRORS = (sqlite3.IntegrityError,)


def is_sqlite_conn(conn: Any) -> bool:
    return isinstance(conn, sqlite3.Connection)


def qmarks_to_percent_s(sql: str) -> str:
    """Troca ``?`` por ``%s`` fora de literais entre aspas simples."""
    out: list[str] = []
    i = 0
    n = len(sql)
    in_single = False
    while i < n:
        c = sql[i]
        if c == "'" and not in_single:
            in_single = True
            out.append(c)
            i += 1
            continue
        if in_single:
            if c == "'":
                if i + 1 < n and sql[i + 1] == "'":
                    out.append("''")
                    i += 2
                    continue
                in_single = False
                out.append(c)
                i += 1
                continue
            out.append(c)
            i += 1
            continue
        if c == "?":
            out.append("%s")
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def adapt_sql(sql: str) -> str:
    if get_db_provider() == "sqlite":
        return sql
    return qmarks_to_percent_s(sql)


def _sql_preview(sql: str, limit: int = 200) -> str:
    return " ".join(str(sql).split())[:limit]


def _log_pg_duration(sql: str, elapsed_ms: float) -> None:
    preview = _sql_preview(sql)
    warn_after = _pg_warn_ms_threshold()
    info_after = _pg_info_ms_threshold()
    if elapsed_ms >= warn_after:
        _logger.warning(
            "postgres query slow %.2f ms (warn>=%.0fms) | %s",
            elapsed_ms,
            warn_after,
            preview,
        )
    elif elapsed_ms >= info_after:
        _logger.info("postgres query %.2f ms | %s", elapsed_ms, preview)
    else:
        _logger.debug("postgres query %.2f ms | %s", elapsed_ms, preview)


def _log_pg_execute_error(sql: str, elapsed_ms: float, exc: BaseException) -> None:
    _logger.error(
        "postgres query failed after %.2f ms | %s | %s: %s",
        elapsed_ms,
        _sql_preview(sql),
        type(exc).__name__,
        exc,
        exc_info=exc,
    )


def db_execute(conn: Any, sql: str, params: Sequence[Any] | Mapping[str, Any] = ()):
    """``conn.execute`` com SQL adaptado ao provedor activo."""
    sql_a = adapt_sql(sql)
    if is_sqlite_conn(conn):
        return conn.execute(sql_a, params)
    t0 = time.perf_counter()
    try:
        cur = conn.execute(sql_a, params)
    except Exception as exc:
        _log_pg_execute_error(sql_a, (time.perf_counter() - t0) * 1000, exc)
        raise
    else:
        _log_pg_duration(sql_a, (time.perf_counter() - t0) * 1000)
        return cur

def sql_order_ci(column_sql: str) -> str:
    """Expressão para ``ORDER BY`` case-insensitive (sem mudar resultados em dados iguais)."""
    if get_db_provider() == "sqlite":
        return f"{column_sql} COLLATE NOCASE"
    return f"LOWER({column_sql})"


def sql_numeric_sort_key_text(column_sql: str) -> str:
    """Expressão portável para ordenar TEXT numericamente (ex.: ``customer_code``).

    Usa ``REAL`` em ambos os motores: trata string vazia como 0 (paridade SQLite/Postgres).
    Valores não numéricos: SQLite trunca/reinterpreta; Postgres falha — dados devem ser
    essencialmente numéricos (como códigos gerados por ``format_customer_code``).
    """
    return (
        f"CAST(COALESCE(NULLIF(TRIM({column_sql}), ''), '0') AS REAL)"
    )


def run_insert_returning_id(conn: Any, sql: str, params: Sequence[Any], pk: str = "id") -> int:
    """INSERT e obtém chave primária numérica; SQLite usa ``lastrowid``, Postgres ``RETURNING``."""
    sql_a = adapt_sql(sql)
    if is_sqlite_conn(conn):
        try:
            cur = conn.execute(sql_a, params)
        except Exception as exc:
            _logger.error(
                "sqlite INSERT failed | %s | %s: %s",
                _sql_preview(sql_a),
                type(exc).__name__,
                exc,
                exc_info=exc,
            )
            raise
        rid = cur.lastrowid
        if rid is None:
            raise RuntimeError("SQLite lastrowid indisponível após INSERT.")
        return int(rid)
    base = sql_a.strip().rstrip(";")
    returning_sql = f"{base} RETURNING {pk}"
    t0 = time.perf_counter()
    try:
        cur = conn.execute(returning_sql, params)
        row = cur.fetchone()
    except Exception as exc:
        _log_pg_execute_error(returning_sql, (time.perf_counter() - t0) * 1000, exc)
        raise
    else:
        _log_pg_duration(returning_sql, (time.perf_counter() - t0) * 1000)
        shadow_mode.replay_statement(sql, params, pg_cursor=cur)
    if row is None:
        raise RuntimeError("INSERT sem linha em RETURNING.")
    if isinstance(row, Mapping):
        return int(row[pk])
    return int(row[0])
