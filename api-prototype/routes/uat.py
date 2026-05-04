from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import Actor, get_actor, get_actor_read

router = APIRouter(prefix="/uat", tags=["uat"])


class UatUpsertBody(BaseModel):
    test_id: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    notes: str = ""


def _serialize_uat_row(test_id: str, row: dict) -> dict:
    return {
        "test_id": test_id,
        "status": str(row.get("status") or "pending"),
        "notes": row.get("notes"),
        "result_recorded_at": row.get("result_recorded_at"),
        "updated_at": row.get("updated_at"),
        "recorded_by_username": row.get("recorded_by_username"),
        "recorded_by_user_id": row.get("recorded_by_user_id"),
        "recorded_by_role": row.get("recorded_by_role"),
    }


@router.get("/records")
def get_uat_records(actor: Actor = Depends(get_actor_read)):
    from services import uat_checklist_service as ucs

    m = ucs.fetch_map_for_tenant(actor.tenant_id or "default")
    items = [_serialize_uat_row(tid, row) for tid, row in sorted(m.items(), key=lambda x: x[0])]
    return {"items": items}


@router.post("/upsert")
def post_uat_upsert(body: UatUpsertBody, actor: Actor = Depends(get_actor)):
    from services import uat_checklist_service

    display_name = (actor.username or "").strip() or actor.user_id
    try:
        uat_checklist_service.upsert_uat_record(
            actor.tenant_id or "default",
            body.test_id.strip(),
            body.status.strip(),
            body.notes or "",
            username=display_name,
            user_id=actor.user_id,
            role=actor.role,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}
