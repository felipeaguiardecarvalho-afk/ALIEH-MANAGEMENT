from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from deps import Actor, get_actor, get_actor_read, get_admin_actor

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _rate_inv_write_or_raise(actor: Actor) -> None:
    from rate_limit import allow_request, write_mutation_limit

    if not allow_request(actor.user_id, "inv_write", max_events=write_mutation_limit()):
        raise HTTPException(
            status_code=429,
            detail="Limite de operações de inventário por minuto excedido. Aguarde e tente novamente.",
        )


def _invalidate_inventory_reads(actor: Actor) -> None:
    try:
        from safe_read_cache import invalidate_tenant_sale_reads

        invalidate_tenant_sale_reads(actor.tenant_id)
    except Exception:
        pass


@router.get("/batches")
def get_batches_in_stock_for_sku(
    sku: str = Query("", description="SKU para listar lotes com stock > 0."),
    actor: Actor = Depends(get_actor_read),
):
    """Paridade com ``fetch_product_batches_in_stock_for_sku`` (fluxo Vendas / Streamlit)."""
    from database.repositories import query_repository as qr

    from safe_read_cache import cached_call

    s = sku.strip()
    tid = (actor.tenant_id or "default").strip() or "default"

    def _load():
        rows = qr.fetch_product_batches_in_stock_for_sku(s, tenant_id=actor.tenant_id)
        items = []
        for r in rows:
            d = _serialize_row(r)
            items.append(
                {
                    "id": int(d["id"]),
                    "name": str(d.get("name") or ""),
                    "stock": float(d.get("stock") or 0),
                    "product_enter_code": d.get("product_enter_code"),
                    "frame_color": d.get("frame_color"),
                    "lens_color": d.get("lens_color"),
                    "style": d.get("style"),
                    "palette": d.get("palette"),
                    "gender": d.get("gender"),
                }
            )
        return {"items": items}

    return cached_call(f"inv_batches:{tid}:{s}", _load)


def _jsonable_cell(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _serialize_lot_row(row) -> dict:
    return {
        "product_id": int(row["product_id"]),
        "sku": row.get("sku"),
        "name": row.get("name") or "",
        "stock": float(row["stock"] or 0),
        "product_enter_code": row.get("product_enter_code"),
        "registered_date": _jsonable_cell(row.get("registered_date")),
        "frame_color": row.get("frame_color"),
        "lens_color": row.get("lens_color"),
        "style": row.get("style"),
        "palette": row.get("palette"),
        "gender": row.get("gender"),
        "cost": float(row.get("cost") or 0),
        "price": float(row.get("price") or 0),
        "markup": float(row.get("markup") or 0),
    }


@router.get("/lots/filter-options")
def get_inventory_lot_filter_options(actor: Actor = Depends(get_actor)):
    from inventory_lots_read import fetch_inventory_lot_filter_options

    return fetch_inventory_lot_filter_options(tenant_id=actor.tenant_id)


@router.get("/lots")
def get_inventory_lots(
    names: str = "",
    skus: str = "",
    frame_colors: str = "",
    lens_colors: str = "",
    genders: str = "",
    styles: str = "",
    palettes: str = "",
    costs: str = "",
    prices: str = "",
    markups: str = "",
    stocks: str = "",
    sku: str = "",
    frame_color: str = "",
    lens_color: str = "",
    gender: str = "",
    style: str = "",
    palette: str = "",
    sort: str = "name",
    page: int = Query(1, ge=1),
    page_size: int = Query(50_000, ge=1, le=50_000),
    actor: Actor = Depends(get_actor),
):
    from inventory_lots_read import search_inventory_lots

    rows, total, totals = search_inventory_lots(
        tenant_id=actor.tenant_id,
        names_csv=names.strip(),
        skus_csv=skus.strip(),
        frame_colors_csv=frame_colors.strip(),
        lens_colors_csv=lens_colors.strip(),
        genders_csv=genders.strip(),
        styles_csv=styles.strip(),
        palettes_csv=palettes.strip(),
        costs_csv=costs.strip(),
        prices_csv=prices.strip(),
        markups_csv=markups.strip(),
        stocks_csv=stocks.strip(),
        sku=sku.strip(),
        frame_color=frame_color.strip(),
        lens_color=lens_color.strip(),
        gender=gender.strip(),
        style=style.strip(),
        palette=palette.strip(),
        sort=sort.strip() or "name",
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return {
        "items": [_serialize_lot_row(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "totals": totals,
    }


class BatchExcludeBody(BaseModel):
    product_enter_codes: list[str] = Field(
        ...,
        min_length=1,
        description="Códigos de entrada de lote a excluir do estoque (reset + stock 0).",
    )


@router.post("/batches/exclude")
def post_batches_exclude(body: BatchExcludeBody, actor: Actor = Depends(get_admin_actor)):
    from services import product_service

    _rate_inv_write_or_raise(actor)
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in body.product_enter_codes:
        code = (raw or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        cleaned.append(code)
    if len(cleaned) > 1:
        raise HTTPException(
            status_code=400,
            detail="Apenas um código de lote por pedido (paridade com o Streamlit).",
        )
    if not cleaned:
        raise HTTPException(status_code=400, detail="Nenhum código de lote válido.")
    code = cleaned[0]
    try:
        n = product_service.reset_batch_pricing_and_exclude(
            code,
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"{code}: {e}") from e
    _invalidate_inventory_reads(actor)
    return {"rows_updated": int(n), "codes_processed": [code]}


class StockReceiptBody(BaseModel):
    sku: str = Field(..., min_length=1)
    product_id: int
    quantity_text: str = ""
    quantity: float = 0.0
    confirm_receipt: bool = False


@router.post("/stock-receipt")
def post_stock_receipt(body: StockReceiptBody, actor: Actor = Depends(get_actor)):
    from database.repositories import query_repository as qr
    from services import product_service
    from utils.validators import parse_cost_quantity_text

    _rate_inv_write_or_raise(actor)
    if not body.confirm_receipt:
        raise HTTPException(
            status_code=400,
            detail="Confirme a entrada de stock antes de finalizar.",
        )

    raw_q = (body.quantity_text or "").strip()
    if raw_q:
        qv, qe = parse_cost_quantity_text(raw_q)
        if qe:
            raise HTTPException(status_code=400, detail=qe)
    else:
        qv = float(body.quantity or 0)
    if qv <= 0:
        raise HTTPException(
            status_code=400,
            detail="A quantidade da entrada deve ser maior que zero (até 4 decimais).",
        )

    try:
        unit_cost = float(
            qr.get_persisted_structured_unit_cost(body.sku.strip(), actor.tenant_id)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if unit_cost <= 0:
        raise HTTPException(
            status_code=400,
            detail="Custo unitário estruturado está zero ou ausente. Salve a composição de custo antes.",
        )

    row = qr.fetch_product_by_id(int(body.product_id), actor.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Lote/produto não encontrado.")
    psku = str(row.get("sku") or "").strip()
    if psku != body.sku.strip():
        raise HTTPException(
            status_code=400,
            detail="O lote seleccionado não corresponde ao SKU indicado.",
        )

    try:
        product_service.add_stock_receipt(
            body.sku.strip(),
            body.product_id,
            float(qv),
            float(unit_cost),
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _invalidate_inventory_reads(actor)
    return {"ok": True, "unit_cost_applied": unit_cost, "quantity": float(qv)}


class ManualWriteDownBody(BaseModel):
    product_id: int
    quantity: float


@router.post("/manual-write-down")
def post_manual_write_down(
    body: ManualWriteDownBody,
    actor: Actor = Depends(get_admin_actor),
):
    from database.repositories import query_repository as qr
    from services import product_service

    _rate_inv_write_or_raise(actor)
    if body.quantity <= 0:
        raise HTTPException(
            status_code=400, detail="A quantidade de baixa deve ser maior que zero."
        )

    row = qr.fetch_product_by_id(int(body.product_id), actor.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Lote/produto não encontrado.")

    stock = float(row["stock"] or 0)
    _eps = 1e-9
    if stock + _eps < float(body.quantity):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Stock insuficiente (disponível: {stock:g}; solicitado: {float(body.quantity):g}). "
                "Não é permitido stock negativo."
            ),
        )

    try:
        new_stock = product_service.apply_manual_stock_write_down(
            body.product_id,
            body.quantity,
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _invalidate_inventory_reads(actor)
    return {"stock_after": new_stock}


def _serialize_row(row):
    if row is None:
        return None
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return row


@router.get("/product/{product_id}/stock-name-sku")
def get_product_stock_name_sku(
    product_id: int,
    actor: Actor = Depends(get_actor),
):
    from services import product_service

    try:
        row = product_service.fetch_product_stock_name_sku(
            product_id, tenant_id=actor.tenant_id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"row": _serialize_row(row)}
