from __future__ import annotations

import base64
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from deps import Actor, get_actor, get_admin_actor, get_actor_read
from routes.storage import validate_supabase_public_object_url

router = APIRouter(prefix="/products", tags=["products"])


def _jsonable_cell(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _serialize_list_row(row) -> dict:
    return {
        "id": int(row["id"]),
        "sku": row.get("sku"),
        "name": row.get("name") or "",
        "frame_color": row.get("frame_color"),
        "lens_color": row.get("lens_color"),
        "gender": row.get("gender"),
        "palette": row.get("palette"),
        "style": row.get("style"),
        "stock": float(row["stock"] or 0),
        "created_at": _jsonable_cell(row.get("created_at")),
        "avg_cost": float(row.get("avg_cost") or 0),
        "sell_price": float(row.get("sell_price") or 0),
    }


def _serialize_detail_row(row, *, tenant_id: str | None) -> dict:
    from database.repositories.product_edit_repository import product_lot_edit_block_reason
    from database.sku_corrections import sku_correction_block_reason

    pid = int(row["id"])
    sku = (row.get("sku") or "").strip()
    lot_block = product_lot_edit_block_reason(pid)
    sku_del = sku_correction_block_reason(sku, tenant_id=tenant_id) if sku else "SKU inválido."
    return {
        "id": pid,
        "sku": row.get("sku"),
        "name": row.get("name") or "",
        "frame_color": row.get("frame_color"),
        "lens_color": row.get("lens_color"),
        "gender": row.get("gender"),
        "palette": row.get("palette"),
        "style": row.get("style"),
        "stock": float(row["stock"] or 0),
        "registered_date": _jsonable_cell(row.get("registered_date")),
        "product_enter_code": row.get("product_enter_code"),
        "created_at": _jsonable_cell(row.get("created_at")),
        "product_image_path": row.get("product_image_path"),
        "avg_cost": float(row.get("avg_cost") or 0),
        "sell_price": float(row.get("sell_price") or 0),
        "lot_edit_block_reason": lot_block,
        "sku_delete_block_reason": sku_del,
    }


@router.get("/attribute-options")
def get_product_attribute_options(actor: Actor = Depends(get_actor)):
    from database.repositories import query_repository as qr

    return qr.fetch_product_search_attribute_options(actor.tenant_id)


@router.get("")
def get_products_list(
    q: str = "",
    frame_color: str = "",
    lens_color: str = "",
    gender: str = "",
    palette: str = "",
    style: str = "",
    sort: str = "sku",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    actor: Actor = Depends(get_actor),
):
    from database.repositories import query_repository as qr

    rows, total = qr.search_products_filtered(
        q.strip(),
        frame_color.strip(),
        lens_color.strip(),
        gender.strip(),
        palette.strip(),
        style.strip(),
        sort.strip() or "sku",
        page_size,
        (page - 1) * page_size,
        tenant_id=actor.tenant_id,
    )
    return {
        "items": [_serialize_list_row(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/sku-body-preview")
def get_sku_body_preview(
    name: str = Query(""),
    frame_color: str = Query(""),
    lens_color: str = Query(""),
    gender: str = Query(""),
    palette: str = Query(""),
    style: str = Query(""),
    _actor: Actor = Depends(get_actor),
):
    """Pré-visualização read-only do corpo de SKU (paridade Streamlit: ``XXX-{corpo}``)."""
    from database.repositories.sku_codec_repository import build_product_sku_body

    n = (name or "").strip()
    fc = (frame_color or "").strip()
    lc = (lens_color or "").strip()
    g = (gender or "").strip()
    p = (palette or "").strip()
    st = (style or "").strip()
    if not n or not (fc and lc and g and p and st):
        return {"preview": None}
    body = build_product_sku_body(
        n,
        frame_color=fc,
        lens_color=lc,
        gender=g,
        palette=p,
        style=st,
    )
    return {"preview": f"XXX-{body}"}


@router.get("/{product_id}/image")
def get_product_image_file(product_id: int, actor: Actor = Depends(get_actor_read)):
    """Ficheiro em disco (`product_images/…`) ou ignora URLs absolutas (cliente usa href directo)."""
    from database.product_images import product_image_abs_path
    from database.repositories import query_repository as qr

    row = qr.fetch_product_by_id(product_id, actor.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    rel = row.get("product_image_path")
    abs_p = product_image_abs_path(rel)
    if abs_p is None:
        raise HTTPException(status_code=404, detail="No image on disk for this product")
    return FileResponse(
        path=str(abs_p),
        filename=abs_p.name,
        media_type=None,
    )


@router.get("/{product_id}")
def get_product_by_id(product_id: int, actor: Actor = Depends(get_actor)):
    from database.repositories import query_repository as qr

    row = qr.fetch_product_by_id(product_id, actor.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _serialize_detail_row(row, tenant_id=actor.tenant_id)


@router.delete("/sku")
def delete_product_sku(
    sku: str = Query(..., min_length=1),
    note: str = Query(""),
    actor: Actor = Depends(get_admin_actor),
):
    from database.sku_corrections import hard_delete_sku_catalog

    try:
        n = hard_delete_sku_catalog(
            sku.strip(),
            note=note or "",
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"deleted_products": n}


class GenerateSkuBody(BaseModel):
    product_name: str = Field(..., min_length=1)
    frame_color: str = ""
    lens_color: str = ""
    gender: str = ""
    palette: str = ""
    style: str = ""
    exclude_product_id: Optional[int] = None


@router.post("/sku/generate")
def post_generate_sku(body: GenerateSkuBody, actor: Actor = Depends(get_actor)):
    from services import product_service

    try:
        sku = product_service.generate_product_sku(
            body.product_name,
            body.frame_color,
            body.lens_color,
            body.gender,
            body.palette,
            body.style,
            exclude_product_id=body.exclude_product_id,
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"sku": sku}


class UpdateAttributesBody(BaseModel):
    """Paridade com Streamlit: nome, data de registo e atributos (``update_product_lot_attributes``)."""

    name: str = Field(..., min_length=1)
    registered_date: str = Field(
        ...,
        description="ISO date YYYY-MM-DD",
    )
    frame_color: str = ""
    lens_color: str = ""
    style: str = ""
    palette: str = ""
    gender: str = ""


@router.put("/{product_id}/attributes")
def put_product_attributes(
    product_id: int,
    body: UpdateAttributesBody,
    actor: Actor = Depends(get_admin_actor),
):
    from database.repositories import product_edit_repository

    rd = _parse_registered_date(body.registered_date)
    try:
        product_edit_repository.update_product_lot_attributes(
            product_id,
            name=body.name.strip(),
            registered_date=rd,
            frame_color=body.frame_color,
            lens_color=body.lens_color,
            style=body.style,
            palette=body.palette,
            gender=body.gender,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


class ProductImageBytesBody(BaseModel):
    product_image_base64: str = Field(..., min_length=8)
    product_image_filename: str = "foto.jpg"


@router.patch("/{product_id}/image-bytes")
def patch_product_image_bytes(
    product_id: int,
    body: ProductImageBytesBody,
    actor: Actor = Depends(get_admin_actor),
):
    """Grava foto em disco (paridade com Streamlit / ``update_product_lot_photo``)."""
    from database.repositories import product_edit_repository

    try:
        raw = base64.b64decode(body.product_image_base64, validate=True)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail="Invalid product_image_base64"
        ) from e
    try:
        product_edit_repository.update_product_lot_photo(
            product_id,
            raw,
            body.product_image_filename or "foto.jpg",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


class CostComponentLine(BaseModel):
    component_key: str
    unit_price: float
    quantity: float = 0.0
    quantity_text: Optional[str] = None


class CostStructureBody(BaseModel):
    sku: str = Field(..., min_length=1)
    components: list[CostComponentLine]


@router.post("/sku/cost-structure")
def post_cost_structure(body: CostStructureBody, actor: Actor = Depends(get_actor)):
    from services import product_service
    from utils.validators import parse_cost_quantity_text, parse_cost_unit_price_value

    tuples_in: list[tuple[str, float, float]] = []
    for c in body.components:
        raw_txt = c.quantity_text
        if raw_txt is not None and str(raw_txt).strip() != "":
            qv, qe = parse_cost_quantity_text(str(raw_txt))
            if qe:
                raise HTTPException(
                    status_code=400,
                    detail=f"{c.component_key}: {qe}",
                )
        else:
            qv = float(c.quantity or 0)
        pv, pe = parse_cost_unit_price_value(float(c.unit_price or 0))
        if pe:
            raise HTTPException(
                status_code=400,
                detail=f"{c.component_key}: {pe}",
            )
        tuples_in.append((c.component_key, pv, qv))
    try:
        total = product_service.save_sku_cost_structure(
            body.sku,
            tuples_in,
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"structured_total": total}


class AddProductBody(BaseModel):
    name: str = Field(..., min_length=1)
    stock: float
    registered_date: str = Field(
        ...,
        description="ISO date YYYY-MM-DD",
    )
    frame_color: str = ""
    lens_color: str = ""
    style: str = ""
    palette: str = ""
    gender: str = ""
    unit_cost: float
    product_image_base64: Optional[str] = None
    product_image_filename: str = ""
    product_image_storage_url: Optional[str] = Field(
        default=None,
        description="Public HTTPS URL after direct client upload to Supabase Storage.",
    )


class ProductImagePublicUrlBody(BaseModel):
    public_url: str = Field(..., min_length=12, max_length=2048)


def _latest_product_id_for_enter_code(enter_code: str, tenant_id: str | None) -> int | None:
    from database.repositories.support import use_connection
    from database.sql_compat import db_execute
    from database.tenancy import effective_tenant_id_for_request

    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        row = db_execute(
            conn,
            """
            SELECT id FROM products
            WHERE tenant_id = %s AND product_enter_code = %s AND deleted_at IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (tid, enter_code.strip()),
        ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def _parse_registered_date(s: str) -> date:
    try:
        return date.fromisoformat(s.strip()[:10])
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail="registered_date must be YYYY-MM-DD"
        ) from e


@router.post("")
def post_add_product(body: AddProductBody, actor: Actor = Depends(get_admin_actor)):
    from database.repositories import product_repository as pr
    from database.repositories.session import write_transaction
    from services import product_service

    rd = _parse_registered_date(body.registered_date)
    storage_url = validate_supabase_public_object_url(
        body.product_image_storage_url or ""
    )
    img_bytes: Optional[bytes] = None
    if body.product_image_base64 and not storage_url:
        try:
            img_bytes = base64.b64decode(body.product_image_base64, validate=True)
        except Exception as e:
            raise HTTPException(
                status_code=400, detail="Invalid product_image_base64"
            ) from e
    try:
        code = product_service.add_product(
            body.name,
            body.stock,
            rd,
            body.frame_color,
            body.lens_color,
            body.style,
            body.palette,
            body.gender,
            body.unit_cost,
            product_image_bytes=img_bytes,
            product_image_filename=body.product_image_filename or "",
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if storage_url:
        pid = _latest_product_id_for_enter_code(code, actor.tenant_id)
        if pid is None:
            raise HTTPException(
                status_code=500,
                detail="Product created but id lookup failed; set image URL manually.",
            )
        with write_transaction(immediate=True) as conn:
            pr.update_product_image_path(
                conn, storage_url, pid, tenant_id=actor.tenant_id
            )

    return {"product_enter_code": code}


@router.patch("/{product_id}/image-public-url")
def patch_product_image_public_url(
    product_id: int,
    body: ProductImagePublicUrlBody,
    actor: Actor = Depends(get_admin_actor),
):
    from database.repositories import product_repository as pr
    from database.repositories import query_repository as qr
    from database.repositories.session import write_transaction

    url = validate_supabase_public_object_url(body.public_url)
    if not url:
        raise HTTPException(
            status_code=400,
            detail="public_url must be a Supabase public object URL for the configured bucket.",
        )
    row = qr.fetch_product_by_id(product_id, actor.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    with write_transaction(immediate=True) as conn:
        pr.update_product_image_path(
            conn, url, product_id, tenant_id=actor.tenant_id
        )
    return {"ok": True, "product_image_path": url}
