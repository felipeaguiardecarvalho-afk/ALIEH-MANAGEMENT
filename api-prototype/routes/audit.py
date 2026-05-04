"""Append-only prototype activity log (Postgres table ``prototype_audit_events``)."""

from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from audit_db import insert_audit_event
from deps import Actor, get_actor

router = APIRouter(prefix="/audit", tags=["audit"])


def _ingest_secret_expected() -> str:
    return (os.environ.get("PROTOTYPE_AUDIT_INGEST_SECRET") or "").strip()


class AuditEventBody(BaseModel):
    domain: Literal["sales", "pricing", "stock", "login"]
    action: str = Field(..., min_length=1, max_length=200)
    detail: dict[str, Any] = Field(default_factory=dict)


@router.post("/events")
def post_audit_event(body: AuditEventBody, actor: Actor = Depends(get_actor)):
    tid = (actor.tenant_id or "default").strip() or "default"
    insert_audit_event(
        tenant_id=tid,
        domain=body.domain,
        action=body.action,
        user_id=actor.user_id,
        username=None,
        detail=body.detail,
    )
    return {"ok": True}


class LoginIngestBody(BaseModel):
    tenant_id: str = Field(default="default", max_length=120)
    username: str = Field(..., min_length=1, max_length=200)
    user_id: str = ""
    success: bool = False
    action: str = Field(default="session", max_length=200)
    detail: dict[str, Any] = Field(default_factory=dict)


@router.post("/login-ingest")
def post_login_audit_ingest(
    body: LoginIngestBody,
    x_prototype_audit_secret: str = Header(..., alias="X-Prototype-Audit-Secret"),
):
    """
    Pre-session login trail from Next.js (shared secret). Domain is always ``login``.
    """
    expected = _ingest_secret_expected()
    if not expected or x_prototype_audit_secret != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing audit ingest secret")

    tid = (body.tenant_id or "default").strip() or "default"
    uid = (body.user_id or "").strip() or None
    detail = {**body.detail, "auth_success": body.success}
    insert_audit_event(
        tenant_id=tid,
        domain="login",
        action=body.action.strip()[:200] or ("success" if body.success else "failure"),
        user_id=uid,
        username=body.username.strip(),
        detail=detail,
    )
    return {"ok": True}
