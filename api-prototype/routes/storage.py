"""Prototype: mint Supabase Storage signed upload URLs (no file bytes through this API)."""

from __future__ import annotations

import os
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import Actor, get_actor

router = APIRouter(prefix="/storage", tags=["storage"])

_ALLOWED_CT = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _supabase_client():
    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise HTTPException(
            status_code=503,
            detail="Supabase Storage is not configured (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY).",
        )
    import httpx
    from supabase import ClientOptions, create_client

    timeout_s = float((os.environ.get("SUPABASE_HTTP_TIMEOUT_SECONDS") or "15").strip() or "15")
    try:
        return create_client(
            url,
            key,
            options=ClientOptions(
                httpx_client=httpx.Client(timeout=timeout_s, limits=httpx.Limits(max_connections=20))
            ),
        )
    except TypeError:
        return create_client(url, key)


def _bucket() -> str:
    b = _env("SUPABASE_STORAGE_PRODUCT_IMAGES_BUCKET", "product-images")
    if not re.match(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", b):
        raise HTTPException(status_code=500, detail="Invalid storage bucket name in env.")
    return b


def _sanitize_filename(name: str) -> str:
    base = os.path.basename((name or "").strip())
    base = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    if not base or base in {".", ".."}:
        return "image.bin"
    return base[:180]


class SignedUploadBody(BaseModel):
    filename: str = Field(..., min_length=1, max_length=240)
    content_type: str = Field(default="image/jpeg", max_length=120)


@router.post("/signed-upload")
def post_signed_upload(body: SignedUploadBody, actor: Actor = Depends(get_actor)):
    ct = (body.content_type or "").strip().lower()
    if ct not in _ALLOWED_CT:
        raise HTTPException(
            status_code=400,
            detail=f"content_type must be one of: {', '.join(sorted(_ALLOWED_CT))}",
        )

    tid = (actor.tenant_id or "default").strip() or "default"
    safe = _sanitize_filename(body.filename)
    uid = uuid.uuid4().hex[:16]
    object_path = f"{tid}/prototype/{uid}_{safe}"

    bucket = _bucket()
    sb = _supabase_client()
    try:
        signed = sb.storage.from_(bucket).create_signed_upload_url(object_path)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase signed URL failed: {e!s}"[:500],
        ) from e

    token = signed.get("token")
    signed_url = signed.get("signed_url") or signed.get("signedUrl")
    if not token or not signed_url:
        raise HTTPException(status_code=502, detail="Unexpected Supabase response (missing token/url).")

    return {
        "bucket": bucket,
        "path": object_path,
        "token": token,
        "signed_url": signed_url,
        "content_type": ct,
    }


def validate_supabase_public_object_url(url: str) -> Optional[str]:
    """
    Returns normalized URL if it matches this project's public object URL pattern; else None.
    """
    raw = (url or "").strip()
    if not raw.startswith("https://"):
        return None
    base = _env("SUPABASE_URL").rstrip("/")
    bucket = _bucket()
    if not base:
        return None
    prefix = f"{base}/storage/v1/object/public/{bucket}/"
    if not raw.startswith(prefix):
        return None
    if len(raw) > 2048:
        return None
    return raw
