"""Exportação JSON de tabelas de auditoria (acesso exclusivo em ``database/``)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from database.connection import DB_PATH, DbConnection
from database.db_errors import DB_DRIVER_ERRORS
from database.repositories.support import use_connection
from database.sql_compat import db_execute, is_sqlite_conn

_AUDIT_TABLES = (
    "login_attempt_audit",
    "sku_deletion_audit",
    "price_history",
    "uat_manual_checklist",
)


def _rows_to_list(conn: DbConnection, table: str) -> list[dict[str, Any]]:
    cur = db_execute(conn, f"SELECT * FROM {table}")
    if is_sqlite_conn(conn):
        cols = [d[0] for d in cur.description]
        out: list[dict[str, Any]] = []
        for row in cur.fetchall():
            out.append({cols[i]: row[i] for i in range(len(cols))})
        return out
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def export_audit_db_payload() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "database_path": str(DB_PATH),
        "tables": {},
    }
    with use_connection(None) as conn:
        for name in _AUDIT_TABLES:
            try:
                payload["tables"][name] = _rows_to_list(conn, name)
            except DB_DRIVER_ERRORS as exc:
                payload["tables"][name] = {"error": str(exc)}
    return payload
