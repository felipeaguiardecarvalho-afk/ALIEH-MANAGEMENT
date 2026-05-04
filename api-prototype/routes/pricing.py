from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from deps import Actor, get_actor

router = APIRouter(prefix="/pricing", tags=["pricing"])


def _active_flag(v) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    try:
        return int(v) != 0
    except (TypeError, ValueError):
        return False


def _jsonable_cell(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _serialize_sku_master(row) -> dict:
    return {
        "sku": str(row.get("sku") or "").strip(),
        "total_stock": float(row.get("total_stock") or 0),
        "avg_unit_cost": float(row.get("avg_unit_cost") or 0),
        "selling_price": float(row.get("selling_price") or 0),
        "structured_cost_total": float(row.get("structured_cost_total") or 0),
        "updated_at": _jsonable_cell(row.get("updated_at")),
    }


def _serialize_pricing_record(row) -> dict:
    return {
        "id": int(row["id"]),
        "sku": str(row.get("sku") or "").strip(),
        "avg_cost_snapshot": float(row.get("avg_cost_snapshot") or 0),
        "markup_pct": float(row.get("markup_pct") or 0),
        "taxes_pct": float(row.get("taxes_pct") or 0),
        "interest_pct": float(row.get("interest_pct") or 0),
        "markup_kind": int(row.get("markup_kind") or 0),
        "taxes_kind": int(row.get("taxes_kind") or 0),
        "interest_kind": int(row.get("interest_kind") or 0),
        "price_before_taxes": float(row.get("price_before_taxes") or 0),
        "price_with_taxes": float(row.get("price_with_taxes") or 0),
        "target_price": float(row.get("target_price") or 0),
        "is_active": _active_flag(row.get("is_active")),
        "created_at": _jsonable_cell(row.get("created_at")),
    }


def _serialize_price_history_row(row) -> dict:
    return {
        "id": int(row["id"]),
        "sku": str(row.get("sku") or "").strip(),
        "old_price": None if row.get("old_price") is None else float(row["old_price"]),
        "new_price": float(row.get("new_price") or 0),
        "created_at": _jsonable_cell(row.get("created_at")),
        "note": row.get("note"),
    }


@router.get("/sku-master")
def get_sku_master_list(actor: Actor = Depends(get_actor)):
    from database.repositories import query_repository as qr

    rows = qr.fetch_sku_master_rows(actor.tenant_id)
    return {"items": [_serialize_sku_master(r) for r in rows]}


@router.get("/sku/{sku}/snapshot")
def get_pricing_snapshot(sku: str, actor: Actor = Depends(get_actor)):
    from database.repositories import query_repository as qr
    from pricing_read import fetch_sku_master_one

    s = (sku or "").strip()
    master = fetch_sku_master_one(s, tenant_id=actor.tenant_id)
    if master is None:
        raise HTTPException(status_code=404, detail="SKU não encontrado no mestre.")
    active = qr.fetch_active_sku_pricing_record(s, actor.tenant_id)
    return {
        "sku_master": _serialize_sku_master(master),
        "active_pricing": _serialize_pricing_record(active) if active else None,
    }


@router.get("/sku/{sku}/pricing-records")
def get_sku_pricing_records(
    sku: str,
    limit: int = Query(100, ge=1, le=500),
    actor: Actor = Depends(get_actor),
):
    from database.repositories import query_repository as qr

    rows = qr.fetch_sku_pricing_records_for_sku(
        sku, limit=int(limit), tenant_id=actor.tenant_id
    )
    return {"items": [_serialize_pricing_record(r) for r in rows]}


@router.get("/sku/{sku}/price-history")
def get_sku_price_history(
    sku: str,
    limit: int = Query(50, ge=1, le=500),
    actor: Actor = Depends(get_actor),
):
    from database.repositories import query_repository as qr

    rows = qr.fetch_price_history_for_sku(
        sku, limit=int(limit), tenant_id=actor.tenant_id
    )
    return {"items": [_serialize_price_history_row(r) for r in rows]}


class SkuSellingPriceBody(BaseModel):
    sku: str = Field(..., min_length=1)
    new_price: float
    note: str = ""


@router.post("/sku/selling-price")
def post_sku_selling_price(body: SkuSellingPriceBody, actor: Actor = Depends(get_actor)):
    from services import product_service

    try:
        product_service.update_sku_selling_price(
            body.sku,
            body.new_price,
            body.note,
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


class ComputeTargetsBody(BaseModel):
    avg_cost: float
    markup_val: float
    taxes_val: float
    interest_val: float
    markup_absolute: bool = False
    taxes_absolute: bool = False
    interest_absolute: bool = False


@router.post("/sku/compute-targets")
def post_compute_targets(body: ComputeTargetsBody, actor: Actor = Depends(get_actor)):
    from services import product_service

    pb, pwt, target = product_service.compute_sku_pricing_targets(
        body.avg_cost,
        body.markup_val,
        body.taxes_val,
        body.interest_val,
        markup_absolute=body.markup_absolute,
        taxes_absolute=body.taxes_absolute,
        interest_absolute=body.interest_absolute,
    )
    return {"price_before": pb, "price_with_taxes": pwt, "target": target}


class SkuPricingWorkflowBody(BaseModel):
    sku: str = Field(..., min_length=1)
    markup_pct: float
    taxes_pct: float
    interest_pct: float
    markup_kind: int = 0
    taxes_kind: int = 0
    interest_kind: int = 0


@router.post("/sku/workflow")
def post_sku_pricing_workflow(
    body: SkuPricingWorkflowBody,
    actor: Actor = Depends(get_actor),
):
    from pricing_read import fetch_sku_master_one
    from services import product_service
    from utils.error_messages import MSG_CMP_NOT_AVAILABLE, MSG_TARGET_PRICE_MUST_BE_POSITIVE

    sku = (body.sku or "").strip()
    if not sku:
        raise HTTPException(status_code=400, detail="SKU inválido.")
    master = fetch_sku_master_one(sku, tenant_id=actor.tenant_id)
    if master is None:
        raise HTTPException(status_code=404, detail="SKU não encontrado no mestre.")
    avg_cost = float(master.get("avg_unit_cost") or 0.0)
    if avg_cost <= 0:
        raise HTTPException(status_code=400, detail=MSG_CMP_NOT_AVAILABLE)
    mk = 1 if int(body.markup_kind or 0) else 0
    tk = 1 if int(body.taxes_kind or 0) else 0
    ik = 1 if int(body.interest_kind or 0) else 0
    _pb, _pwt, target = product_service.compute_sku_pricing_targets(
        avg_cost,
        body.markup_pct,
        body.taxes_pct,
        body.interest_pct,
        markup_absolute=bool(mk),
        taxes_absolute=bool(tk),
        interest_absolute=bool(ik),
    )
    if target <= 0:
        raise HTTPException(status_code=400, detail=MSG_TARGET_PRICE_MUST_BE_POSITIVE)

    try:
        new_id = product_service.save_sku_pricing_workflow(
            body.sku,
            body.markup_pct,
            body.taxes_pct,
            body.interest_pct,
            markup_kind=body.markup_kind,
            taxes_kind=body.taxes_kind,
            interest_kind=body.interest_kind,
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"pricing_record_id": new_id}


class ProductRowPricingBody(BaseModel):
    product_id: int
    cost: float
    price: float


@router.post("/product/row")
def post_product_row_pricing(
    body: ProductRowPricingBody,
    actor: Actor = Depends(get_actor),
):
    from services import product_service

    try:
        product_service.set_product_pricing(
            body.product_id,
            body.cost,
            body.price,
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


class BatchLockBody(BaseModel):
    product_name: str = Field(..., min_length=1)
    sku: str = Field(..., min_length=1)
    registered_date_text: str = Field(..., min_length=1)
    cost: float
    price: float


@router.post("/product/batch-lock")
def post_batch_lock(body: BatchLockBody, actor: Actor = Depends(get_actor)):
    from services import product_service

    try:
        n = product_service.set_product_pricing_for_batch(
            body.product_name,
            body.sku,
            body.registered_date_text,
            body.cost,
            body.price,
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"rows_updated": n}


class EnterCodeBody(BaseModel):
    product_enter_code: str = Field(..., min_length=1)


@router.post("/batch/reset")
def post_batch_reset(body: EnterCodeBody, actor: Actor = Depends(get_actor)):
    from services import product_service

    try:
        n = product_service.reset_batch_pricing_and_exclude(
            body.product_enter_code,
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"rows_updated": n}


@router.post("/batch/clear")
def post_batch_clear(body: EnterCodeBody, actor: Actor = Depends(get_actor)):
    from services import product_service

    try:
        n = product_service.clear_batch_pricing_only(
            body.product_enter_code,
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"rows_cleared": n}
