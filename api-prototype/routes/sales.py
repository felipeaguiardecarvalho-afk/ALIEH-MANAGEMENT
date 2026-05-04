from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator, model_validator

from deps import Actor, get_actor, get_actor_read
from utils.error_messages import (
    MSG_SALE_IDEMPOTENCY_PAYLOAD_MISMATCH,
    MSG_SALE_PREVIEW_MISMATCH,
)

router = APIRouter(prefix="/sales", tags=["sales"])
_logger = logging.getLogger("alieh.prototype.sales")


def _row_to_dict(row):
    if row is None:
        return None
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return row


def _round_money_preview_payload(d: dict) -> dict:
    """Respostas JSON com 2 casas — alinha preview e total devolvido após gravação."""
    out = dict(d)
    for k in ("base_price", "discount_amount", "final_total", "unit_price"):
        if k in out and isinstance(out[k], (int, float)):
            out[k] = round(float(out[k]) + 1e-12, 2)
    return out


def _invalidate_sale_reads(actor: Actor) -> None:
    try:
        from safe_read_cache import invalidate_tenant_sale_reads

        invalidate_tenant_sale_reads(actor.tenant_id)
    except Exception:
        _logger.exception("invalidate_tenant_sale_reads failed")


def _rate_sale_mutation_or_raise(actor: Actor) -> None:
    from rate_limit import allow_request, sale_mutation_limit

    if not allow_request(actor.user_id, "sale_mut", max_events=sale_mutation_limit()):
        raise HTTPException(
            status_code=429,
            detail="Limite de pedidos de venda por minuto excedido. Aguarde e tente novamente.",
        )


def _rate_sale_preview_or_raise(actor: Actor) -> None:
    from rate_limit import allow_request

    if not allow_request(actor.user_id, "sale_preview", max_events=120):
        raise HTTPException(
            status_code=429,
            detail="Limite de pré-visualizações por minuto excedido. Aguarde e tente novamente.",
        )


def _http_from_record_value_error(e: ValueError, body: RecordSaleBody) -> HTTPException:
    msg = str(e)
    code = "bad_request"
    status = 400
    if msg == MSG_SALE_IDEMPOTENCY_PAYLOAD_MISMATCH:
        code = "idempotency_conflict"
        status = 409
    elif msg == MSG_SALE_PREVIEW_MISMATCH:
        code = "preview_stale"
        status = 409
    return HTTPException(
        status_code=status,
        detail={
            "message": msg,
            "code": code,
            "context": {
                "product_id": body.product_id,
                "customer_id": body.customer_id,
            },
        },
    )


class RecordSaleBody(BaseModel):
    product_id: int
    quantity: int
    customer_id: int
    discount_amount: float = 0.0
    payment_method: str = Field(..., min_length=1)
    expected_unit_price: Optional[float] = None
    expected_final_total: Optional[float] = None
    expected_discount_amount: Optional[float] = None

    @field_validator("payment_method", mode="before")
    @classmethod
    def _strip_pm(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def _expected_all_or_none(self) -> "RecordSaleBody":
        ts = (
            self.expected_unit_price,
            self.expected_final_total,
            self.expected_discount_amount,
        )
        if any(x is not None for x in ts) and not all(x is not None for x in ts):
            raise ValueError(
                "Envie os três campos expected_* em conjunto (preço unitário, total final, desconto)."
            )
        return self


class PreviewSaleBody(BaseModel):
    product_id: int
    quantity: int
    customer_id: int
    discount_mode: str = "percent"
    discount_input: float = 0.0
    payment_method: str = Field(..., min_length=1)

    @field_validator("payment_method", "discount_mode", mode="before")
    @classmethod
    def _strip_strings(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


@router.get("/saleable-skus")
def get_saleable_skus(actor: Actor = Depends(get_actor_read)):
    from services import read_queries

    from safe_read_cache import cached_call

    tid = (actor.tenant_id or "default").strip() or "default"

    def _load():
        rows = read_queries.fetch_skus_available_for_sale(tenant_id=actor.tenant_id)
        items = []
        for r in rows:
            d = _row_to_dict(r)
            items.append(
                {
                    "sku": str(d.get("sku") or ""),
                    "selling_price": float(d.get("selling_price") or 0),
                    "total_stock": float(d.get("total_stock") or 0),
                    "sample_name": d.get("sample_name"),
                }
            )
        return {"items": items}

    return cached_call(f"sale_skus:{tid}", _load)


@router.post("/preview")
def post_preview_sale(body: PreviewSaleBody, actor: Actor = Depends(get_actor)):
    from services import sales_service

    _rate_sale_preview_or_raise(actor)
    try:
        preview = sales_service.preview_record_sale(
            product_id=body.product_id,
            quantity=body.quantity,
            customer_id=body.customer_id,
            discount_mode=body.discount_mode,
            discount_input=body.discount_input,
            payment_method=body.payment_method,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _round_money_preview_payload(preview)


@router.post("/submit")
def post_submit_sale(
    body: PreviewSaleBody,
    actor: Actor = Depends(get_actor),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """Orquestração única: preview → validação de totais → record (sem alterar ``sales_service``)."""
    from database.sale_idempotency import purge_expired_idempotency_rows
    from prototype_metrics import inc_sales_submit_ok
    from services import sales_service

    _rate_sale_mutation_or_raise(actor)
    key = (idempotency_key or "").strip()[:128] or None
    if not key:
        raise HTTPException(
            status_code=400,
            detail="Cabeçalho Idempotency-Key é obrigatório para concluir a venda.",
        )

    try:
        preview = sales_service.preview_record_sale(
            product_id=body.product_id,
            quantity=body.quantity,
            customer_id=body.customer_id,
            discount_mode=body.discount_mode,
            discount_input=body.discount_input,
            payment_method=body.payment_method,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    preview = _round_money_preview_payload(preview)
    disc = float(preview.get("discount_amount") or 0)
    pm = str(preview.get("payment_method") or body.payment_method)

    rb = RecordSaleBody(
        product_id=body.product_id,
        quantity=body.quantity,
        customer_id=body.customer_id,
        discount_amount=disc,
        payment_method=pm,
        expected_unit_price=float(preview["unit_price"]),
        expected_final_total=float(preview["final_total"]),
        expected_discount_amount=float(preview["discount_amount"]),
    )

    try:
        sale_code, final_total = sales_service.record_sale(
            rb.product_id,
            rb.quantity,
            rb.customer_id,
            rb.discount_amount,
            payment_method=rb.payment_method,
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
            idempotency_key=key,
            expected_unit_price=rb.expected_unit_price,
            expected_final_total=rb.expected_final_total,
            expected_discount_amount=rb.expected_discount_amount,
        )
    except ValueError as e:
        raise _http_from_record_value_error(e, rb) from e

    _invalidate_sale_reads(actor)
    try:
        purge_expired_idempotency_rows()
    except Exception:
        _logger.debug("purge_after_submit_skipped", exc_info=True)

    inc_sales_submit_ok()
    _logger.info(
        "sale_submit_ok",
        extra={
            "tenant_id": actor.tenant_id,
            "user_id": actor.user_id,
            "sale_code": sale_code,
            "product_id": body.product_id,
            "customer_id": body.customer_id,
            "quantity": body.quantity,
            "final_total": float(final_total),
        },
    )
    return {
        "sale_code": sale_code,
        "final_total": round(float(final_total) + 1e-12, 2),
    }


@router.post("/record")
def post_record_sale(
    body: RecordSaleBody,
    actor: Actor = Depends(get_actor),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    from database.sale_idempotency import purge_expired_idempotency_rows
    from services import sales_service

    _rate_sale_mutation_or_raise(actor)
    key = (idempotency_key or "").strip()[:128] or None
    try:
        sale_code, final_total = sales_service.record_sale(
            body.product_id,
            body.quantity,
            body.customer_id,
            body.discount_amount,
            payment_method=body.payment_method,
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
            idempotency_key=key,
            expected_unit_price=body.expected_unit_price,
            expected_final_total=body.expected_final_total,
            expected_discount_amount=body.expected_discount_amount,
        )
    except ValueError as e:
        raise _http_from_record_value_error(e, body) from e
    _invalidate_sale_reads(actor)
    try:
        purge_expired_idempotency_rows()
    except Exception:
        _logger.debug("purge_after_record_skipped", exc_info=True)
    _logger.info(
        "sale_record_ok",
        extra={
            "tenant_id": actor.tenant_id,
            "user_id": actor.user_id,
            "sale_code": sale_code,
            "product_id": body.product_id,
            "customer_id": body.customer_id,
            "quantity": body.quantity,
            "final_total": float(final_total),
        },
    )
    return {
        "sale_code": sale_code,
        "final_total": round(float(final_total) + 1e-12, 2),
    }


@router.get("/product-context/{product_id}")
def get_sale_product_context(
    product_id: int,
    response: Response,
    actor: Actor = Depends(get_actor),
):
    """Leitura para UI de vendas (estoque, SKU, preço ativo) — mesmo SQL que ``get_product_row_for_sale``.

    **Deprecado para o fluxo web-prototype:** o formulário de vendas usa ``POST /sales/preview``,
    que já inclui stock e preço na validação. Mantido para integrações ou ferramentas externas.
    """
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</sales/preview>; rel="alternate"'
    from database.repositories import sales_repository as sales_repository

    row = sales_repository.get_product_row_for_sale(
        None, int(product_id), tenant_id=actor.tenant_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    d = _row_to_dict(row)
    return {
        "stock": float(d.get("stock") or 0),
        "sku": str(d.get("sku") or ""),
        "selling_price": float(d.get("sp") or 0),
        "product_deleted": bool(d.get("p_del")),
        "sku_master_deleted": bool(d.get("sm_del")),
    }


@router.get("/recent")
def get_recent_sales(
    actor: Actor = Depends(get_actor_read),
    limit: int = Query(20, ge=1, le=500),
):
    from services import sales_service

    rows = sales_service.fetch_recent_sales_for_ui(
        limit=limit, tenant_id=actor.tenant_id
    )
    return {"items": [_row_to_dict(r) for r in (rows or [])]}
