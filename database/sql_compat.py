"""Compatibilidade SQL SQLite ↔ PostgreSQL (placeholders e fragmentos portáveis).

- Placeholders nas queries da app: ``%s`` (psycopg). Em SQLite, :func:`adapt_sql` converte para ``?``.
- ``?`` residual é ainda convertido para ``%s`` em PostgreSQL (compatibilidade).
- PostgreSQL sem passar por adapt: :func:`pg_execute_no_prepare` (cursor + ``prepare=False``).
- Não altera a semântica das queries; apenas o formato de bind e pequenos fragmentos
  expostos como :func:`sql_order_ci`.

No SQLite, o tempo e falhas de ``execute`` são registados em
:class:`database.timed_sqlite.TimedSqliteConnection`. Aqui regista-se duração e erros em
``db_execute`` / ``run_insert_returning_id`` / ``db_fetch_all`` / ``db_fetch_one`` para Postgres
(placeholders ``%s``; linhas como ``dict``).
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


def pg_execute_no_prepare(
    conn: Any,
    query: Any,
    params: Sequence[Any] | Mapping[str, Any] | None = None,
) -> Any:
    """PostgreSQL apenas: ``cursor().execute(..., prepare=False)`` para compatibilidade PgBouncer.

    Devolve o cursor **aberto**; o chamador deve invocar ``close()`` após ``fetch*`` ou
    consumir o resultado por completo. ``query`` pode ser ``str`` ou composição
    :mod:`psycopg.sql`.
    """
    if is_sqlite_conn(conn):
        raise TypeError("pg_execute_no_prepare requer ligação psycopg (não SQLite)")
    cur = conn.cursor(binary=False)
    try:
        if params is None:
            cur.execute(query, prepare=False)
        else:
            cur.execute(query, params, prepare=False)
        return cur
    except BaseException:
        cur.close()
        raise


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


def percent_s_to_qmarks(sql: str) -> str:
    """Troca ``%s`` por ``?`` fora de literais entre aspas simples (uso com SQLite)."""
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
        if i + 1 < n and sql[i : i + 2] == "%s":
            out.append("?")
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def adapt_sql(sql: str) -> str:
    if get_db_provider() == "sqlite":
        return percent_s_to_qmarks(sql)
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
    """SQL adaptado ao provedor; Postgres usa cursor com ``prepare=False`` (pooler PgBouncer).

    Devolve o cursor **aberto** para ``fetchone`` / ``fetchall`` / ``rowcount``. Com ligação
    PostgreSQL e ``row_factory=dict_row``, cada linha é um ``dict`` — use chaves de coluna,
    não índices numéricos.

    Para leituras que devem fechar o cursor de imediato e devolver ``list[dict]``, use
    :func:`db_fetch_all` ou :func:`db_fetch_one`.
    """
    sql_a = adapt_sql(sql)
    if is_sqlite_conn(conn):
        return conn.execute(sql_a, params)
    t0 = time.perf_counter()
    cur = conn.cursor(binary=False)
    try:
        cur.execute(sql_a, params, prepare=False)
    except BaseException as exc:
        _log_pg_execute_error(sql_a, (time.perf_counter() - t0) * 1000, exc)
        try:
            cur.close()
        except Exception:
            pass
        raise
    _log_pg_duration(sql_a, (time.perf_counter() - t0) * 1000)
    return cur


def _materialized_rows_as_dicts(rows: Sequence[Any], description: Any) -> list[dict[str, Any]]:
    if not rows:
        return []
    first = rows[0]
    if isinstance(first, Mapping):
        return [dict(r) for r in rows]
    cols = [d[0] for d in (description or [])]
    return [dict(zip(cols, tuple(r))) for r in rows]


def db_fetch_all(
    conn: Any,
    sql: str,
    params: Sequence[Any] | Mapping[str, Any] = (),
) -> list[dict[str, Any]]:
    """Executa SELECT e devolve todas as linhas como ``dict`` (cursor fechado no Postgres)."""
    sql_a = adapt_sql(sql)
    if is_sqlite_conn(conn):
        try:
            cur = conn.execute(sql_a, params)
            raw = cur.fetchall()
            desc = cur.description
        except Exception as exc:
            _logger.error(
                "sqlite query failed | %s | %s: %s",
                _sql_preview(sql_a),
                type(exc).__name__,
                exc,
                exc_info=exc,
            )
            raise
        return _materialized_rows_as_dicts(raw, desc)
    t0 = time.perf_counter()
    try:
        with conn.cursor(binary=False) as cur:
            cur.execute(sql_a, params, prepare=False)
            raw = cur.fetchall()
            desc = cur.description
    except BaseException as exc:
        _log_pg_execute_error(sql_a, (time.perf_counter() - t0) * 1000, exc)
        raise
    _log_pg_duration(sql_a, (time.perf_counter() - t0) * 1000)
    return _materialized_rows_as_dicts(raw, desc)


def db_fetch_one(
    conn: Any,
    sql: str,
    params: Sequence[Any] | Mapping[str, Any] = (),
) -> dict[str, Any] | None:
    """Executa SELECT e devolve uma linha como ``dict`` ou ``None`` (cursor fechado no Postgres)."""
    sql_a = adapt_sql(sql)
    if is_sqlite_conn(conn):
        try:
            cur = conn.execute(sql_a, params)
            raw = cur.fetchone()
            desc = cur.description
        except Exception as exc:
            _logger.error(
                "sqlite query failed | %s | %s: %s",
                _sql_preview(sql_a),
                type(exc).__name__,
                exc,
                exc_info=exc,
            )
            raise
        if raw is None:
            return None
        return _materialized_rows_as_dicts([raw], desc)[0]
    t0 = time.perf_counter()
    try:
        with conn.cursor(binary=False) as cur:
            cur.execute(sql_a, params, prepare=False)
            raw = cur.fetchone()
            desc = cur.description
    except BaseException as exc:
        _log_pg_execute_error(sql_a, (time.perf_counter() - t0) * 1000, exc)
        raise
    _log_pg_duration(sql_a, (time.perf_counter() - t0) * 1000)
    if raw is None:
        return None
    return _materialized_rows_as_dicts([raw], desc)[0]

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
    cur = conn.cursor(binary=False)
    try:
        cur.execute(returning_sql, params, prepare=False)
        row = cur.fetchone()
    except BaseException as exc:
        _log_pg_execute_error(returning_sql, (time.perf_counter() - t0) * 1000, exc)
        try:
            cur.close()
        except Exception:
            pass
        raise
    else:
        _log_pg_duration(returning_sql, (time.perf_counter() - t0) * 1000)
        shadow_mode.replay_statement(sql, params, pg_cursor=cur)
    if row is None:
        raise RuntimeError("INSERT sem linha em RETURNING.")
    if isinstance(row, Mapping):
        return int(row[pk])
    cols = [d[0] for d in (cur.description or [])]
    if cols and pk in cols:
        idx = cols.index(pk)
        return int(tuple(row)[idx])
    return int(tuple(row)[0])
