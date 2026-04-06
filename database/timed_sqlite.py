"""Conexão SQLite com registo de duração de ``execute`` / ``executemany`` / ``executescript``."""

from __future__ import annotations

import logging
import os
import sqlite3
import time

_logger = logging.getLogger(__name__)


def _info_ms_threshold() -> float:
    try:
        return float((os.environ.get("ALIEH_DB_QUERY_INFO_MS") or "100").strip())
    except ValueError:
        return 100.0


def _warn_ms_threshold() -> float:
    try:
        return float((os.environ.get("ALIEH_DB_QUERY_WARN_MS") or "1000").strip())
    except ValueError:
        return 1000.0


def _sql_preview(sql: str, limit: int = 200) -> str:
    return " ".join(str(sql).split())[:limit]


def _log_sql_duration(label: str, sql: str, elapsed_ms: float) -> None:
    preview = _sql_preview(sql)
    warn_after = _warn_ms_threshold()
    info_after = _info_ms_threshold()
    if elapsed_ms >= warn_after:
        _logger.warning(
            "%s query slow %.2f ms (warn>=%.0fms) | %s",
            label,
            elapsed_ms,
            warn_after,
            preview,
        )
    elif elapsed_ms >= info_after:
        _logger.info("%s query %.2f ms | %s", label, elapsed_ms, preview)
    else:
        _logger.debug("%s query %.2f ms | %s", label, elapsed_ms, preview)


def _log_sql_error(label: str, sql: str, elapsed_ms: float, exc: BaseException) -> None:
    _logger.error(
        "%s query failed after %.2f ms | %s | %s: %s",
        label,
        elapsed_ms,
        _sql_preview(sql),
        type(exc).__name__,
        exc,
        exc_info=exc,
    )


class TimedSqliteConnection(sqlite3.Connection):
    def execute(self, sql, parameters=()):  # type: ignore[override]
        t0 = time.perf_counter()
        try:
            result = super().execute(sql, parameters)
        except Exception as exc:
            _log_sql_error("sqlite", sql, (time.perf_counter() - t0) * 1000, exc)
            raise
        else:
            _log_sql_duration("sqlite", sql, (time.perf_counter() - t0) * 1000)
            return result

    def executemany(self, sql, seq_of_parameters):  # type: ignore[override]
        label_sql = f"{sql} [executemany]"
        t0 = time.perf_counter()
        try:
            result = super().executemany(sql, seq_of_parameters)
        except Exception as exc:
            _log_sql_error("sqlite", label_sql, (time.perf_counter() - t0) * 1000, exc)
            raise
        else:
            _log_sql_duration("sqlite", label_sql, (time.perf_counter() - t0) * 1000)
            return result

    def executescript(self, sql_script: str):  # type: ignore[override]
        t0 = time.perf_counter()
        try:
            result = super().executescript(sql_script)
        except Exception as exc:
            _log_sql_error("sqlite", "[executescript]", (time.perf_counter() - t0) * 1000, exc)
            raise
        else:
            _log_sql_duration("sqlite", "[executescript]", (time.perf_counter() - t0) * 1000)
            return result
