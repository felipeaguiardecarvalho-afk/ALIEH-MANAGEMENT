"""Isolated prototype audit table (CREATE IF NOT EXISTS — no changes to core app tables)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

_logger = logging.getLogger(__name__)

_TABLE_READY = False

_DDL_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS prototype_audit_events (
        id BIGSERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT 'default',
        domain TEXT NOT NULL,
        action TEXT NOT NULL,
        user_id TEXT,
        username TEXT,
        detail_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_proto_audit_tenant_created
    ON prototype_audit_events (tenant_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_proto_audit_domain
    ON prototype_audit_events (tenant_id, domain)
    """,
)


def ensure_prototype_audit_table() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    from database.repositories.support import use_connection
    from database.sql_compat import db_execute

    try:
        with use_connection(None) as conn:
            for stmt in _DDL_STATEMENTS:
                db_execute(conn, stmt.strip(), ())
        _TABLE_READY = True
    except Exception:
        _logger.exception("prototype_audit_events: ensure table failed")
        raise


def insert_audit_event(
    *,
    tenant_id: str,
    domain: str,
    action: str,
    user_id: Optional[str],
    username: Optional[str],
    detail: dict[str, Any],
) -> None:
    ensure_prototype_audit_table()
    from database.repositories.support import use_connection
    from database.sql_compat import db_execute

    tid = (tenant_id or "").strip() or "default"
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = json.dumps(detail, ensure_ascii=False, default=str)
    if len(payload) > 16000:
        payload = payload[:16000] + "…"

    with use_connection(None) as conn:
        db_execute(
            conn,
            """
            INSERT INTO prototype_audit_events
                (tenant_id, domain, action, user_id, username, detail_json, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tid,
                domain.strip()[:64],
                action.strip()[:200],
                (user_id or "").strip()[:128] or None,
                (username or "").strip()[:200] or None,
                payload,
                created,
            ),
        )
