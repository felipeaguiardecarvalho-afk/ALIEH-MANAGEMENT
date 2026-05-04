"""Prototype API: auth context from headers; role gate before service calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, Header, HTTPException, status


ALLOWED_ROLES: frozenset[str] = frozenset({"admin", "operator"})
READ_ROLES: frozenset[str] = frozenset({"admin", "operator", "viewer"})


@dataclass(frozen=True)
class Actor:
    user_id: str
    tenant_id: str | None
    role: Literal["admin", "operator", "viewer"]
    username: str | None = None


def _parse_actor(
    x_user_id: str,
    x_tenant_id: str | None,
    x_role: str,
    x_username: str | None,
    allowed: frozenset[str],
    allowed_label: str,
) -> Actor:
    role = (x_role or "").strip().lower()
    if role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid role; allowed: {allowed_label}",
        )
    uid = (x_user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id is required",
        )
    tid = (x_tenant_id or "").strip() or None
    uname = (x_username or "").strip() or None
    actor = Actor(user_id=uid, tenant_id=tid, role=role, username=uname)  # type: ignore[arg-type]
    try:
        from request_context import set_actor_for_log

        set_actor_for_log(actor.user_id, actor.tenant_id, actor.role)
    except Exception:
        pass
    return actor


def get_actor(
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_role: str = Header(..., alias="X-Role"),
    x_username: str | None = Header(None, alias="X-Username"),
) -> Actor:
    return _parse_actor(
        x_user_id,
        x_tenant_id,
        x_role,
        x_username,
        ALLOWED_ROLES,
        "admin, operator",
    )


def get_actor_read(
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_role: str = Header(..., alias="X-Role"),
    x_username: str | None = Header(None, alias="X-Username"),
) -> Actor:
    """Same as get_actor but allows viewer (read-only UAT list, etc.)."""
    return _parse_actor(
        x_user_id,
        x_tenant_id,
        x_role,
        x_username,
        READ_ROLES,
        "admin, operator, viewer",
    )


def get_admin_actor(actor: Actor = Depends(get_actor)) -> Actor:
    if actor.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return actor
