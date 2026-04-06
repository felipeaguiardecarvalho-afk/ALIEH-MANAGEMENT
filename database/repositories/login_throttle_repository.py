"""Controlo de tentativas de login por utilizador e auditoria opcional (SQL)."""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from database.connection import DbConnection
from database.repositories.support import use_connection
from database.sql_compat import db_execute
from database.tenancy import resolve_tenant_id

MAX_FAILURES_BEFORE_LOCKOUT = 5
LOCKOUT_SECONDS = 300


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def _refresh_and_is_locked_impl(
    c: DbConnection,
    username_norm: str,
    tenant_id: str | None = None,
) -> Tuple[bool, int]:
    if not username_norm:
        return False, 0
    tid = resolve_tenant_id(tenant_id)
    row = db_execute(
        c,
        """
        SELECT failure_count, locked_until
        FROM login_user_throttle
        WHERE tenant_id = ? AND username_norm = ?
        """,
        (tid, username_norm),
    ).fetchone()
    if not row:
        return False, 0
    locked_until = float(row["locked_until"] or 0)
    now_j = time.time()
    if locked_until > now_j:
        return True, max(0, int(math.ceil(locked_until - now_j)))
    db_execute(
        c,
        """
        UPDATE login_user_throttle
        SET failure_count = 0, locked_until = 0, updated_at = ?
        WHERE tenant_id = ? AND username_norm = ?
        """,
        (_utc_iso_now(), tid, username_norm),
    )
    return False, 0


def refresh_and_is_locked(
    conn: DbConnection | None,
    username_norm: str,
    tenant_id: str | None = None,
) -> Tuple[bool, int]:
    """Se ``locked_until`` expirou, repõe contagem. Devolve (bloqueado, segundos_restantes)."""
    with use_connection(conn) as c:
        return _refresh_and_is_locked_impl(c, username_norm, tenant_id)


def _record_failed_attempt_impl(
    c: DbConnection,
    username_norm: str,
    tenant_id: str | None = None,
) -> Tuple[bool, int, int]:
    if not username_norm:
        return False, 0, 0
    tid = resolve_tenant_id(tenant_id)
    now_j = time.time()
    now_iso = _utc_iso_now()
    row = db_execute(
        c,
        """
        SELECT failure_count, locked_until
        FROM login_user_throttle
        WHERE tenant_id = ? AND username_norm = ?
        """,
        (tid, username_norm),
    ).fetchone()
    if row and float(row["locked_until"] or 0) > now_j:
        lu = float(row["locked_until"])
        return True, max(0, int(math.ceil(lu - now_j))), int(row["failure_count"] or 0)

    prev = int(row["failure_count"] or 0) if row else 0
    fc = prev + 1
    locked_until = 0.0
    consecutive_for_msg = fc
    if fc >= MAX_FAILURES_BEFORE_LOCKOUT:
        locked_until = now_j + LOCKOUT_SECONDS
        fc = 0

    db_execute(
        c,
        """
        INSERT INTO login_user_throttle (tenant_id, username_norm, failure_count, locked_until, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(tenant_id, username_norm) DO UPDATE SET
            failure_count = excluded.failure_count,
            locked_until = excluded.locked_until,
            updated_at = excluded.updated_at
        """,
        (tid, username_norm, fc, locked_until, now_iso),
    )
    if locked_until > now_j:
        return (
            True,
            max(0, int(math.ceil(locked_until - now_j))),
            consecutive_for_msg,
        )
    return False, 0, consecutive_for_msg


def record_failed_attempt(
    conn: DbConnection | None,
    username_norm: str,
    tenant_id: str | None = None,
) -> Tuple[bool, int, int]:
    """
    Incrementa falhas consecutivas; ao atingir o máximo, aplica bloqueio temporal.

    Devolve (bloqueado_após_esta_tentativa, segundos_restantes_do_bloqueio,
    falhas_consecutivas_registadas_após_esta_tentativa — útil para mensagens).
    """
    with use_connection(conn) as c:
        return _record_failed_attempt_impl(c, username_norm, tenant_id)


def _clear_for_user_impl(
    c: DbConnection, username_norm: str, tenant_id: str | None = None
) -> None:
    if not username_norm:
        return
    tid = resolve_tenant_id(tenant_id)
    db_execute(
        c,
        "DELETE FROM login_user_throttle WHERE tenant_id = ? AND username_norm = ?",
        (tid, username_norm),
    )


def clear_for_user(
    conn: DbConnection | None,
    username_norm: str,
    tenant_id: str | None = None,
) -> None:
    with use_connection(conn) as c:
        _clear_for_user_impl(c, username_norm, tenant_id)


def _log_attempt_impl(
    c: DbConnection,
    username_norm: str,
    success: bool,
    client_hint: Optional[str] = None,
    tenant_id: str | None = None,
) -> None:
    if not username_norm:
        return
    tid = resolve_tenant_id(tenant_id)
    db_execute(
        c,
        """
        INSERT INTO login_attempt_audit (tenant_id, username_norm, success, created_at, client_hint)
        VALUES (?, ?, ?, ?, ?)
        """,
        (tid, username_norm, 1 if success else 0, _utc_iso_now(), client_hint),
    )


def log_attempt(
    conn: DbConnection | None,
    username_norm: str,
    success: bool,
    client_hint: Optional[str] = None,
    tenant_id: str | None = None,
) -> None:
    with use_connection(conn) as c:
        _log_attempt_impl(c, username_norm, success, client_hint, tenant_id)


def record_failure_and_audit_log(
    username_norm: str,
    *,
    client_hint: Optional[str] = None,
    tenant_id: str | None = None,
) -> Tuple[bool, int, int]:
    """Uma ligação: falha + linha em ``login_attempt_audit`` (falha)."""
    with use_connection(None) as c:
        locked, rem, consecutive = _record_failed_attempt_impl(
            c, username_norm, tenant_id
        )
        try:
            _log_attempt_impl(c, username_norm, False, client_hint, tenant_id)
        except Exception:
            pass
        return locked, rem, consecutive


def clear_for_user_and_log_success(
    username_norm: str,
    *,
    client_hint: Optional[str] = None,
    tenant_id: str | None = None,
) -> None:
    """Uma ligação: limpar throttle + auditoria de sucesso."""
    with use_connection(None) as c:
        _clear_for_user_impl(c, username_norm, tenant_id)
        try:
            _log_attempt_impl(c, username_norm, True, client_hint, tenant_id)
        except Exception:
            pass
