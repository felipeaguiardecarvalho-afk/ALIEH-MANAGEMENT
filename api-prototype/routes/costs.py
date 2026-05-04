"""Custos — leituras e pré-visualização alinhadas ao Streamlit (app.py Custos)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from deps import Actor, get_actor, get_actor_read

router = APIRouter(prefix="/costs", tags=["costs"])


def _serialize_master_row(r) -> dict[str, Any]:
    ts = float(r.get("total_stock") or 0)
    cmp_ = float(r.get("avg_unit_cost") or 0)
    return {
        "sku": r.get("sku"),
        "total_stock": ts,
        "avg_unit_cost": cmp_,
        "selling_price": float(r.get("selling_price") or 0),
        "structured_cost_total": float(r.get("structured_cost_total") or 0),
        "valuation_cmp": round(ts * cmp_, 2),
        "updated_at": str(r["updated_at"]) if r.get("updated_at") is not None else None,
    }


@router.get("/sku-masters")
def get_sku_masters(actor: Actor = Depends(get_actor)):
    from database.repositories import query_repository as qr

    rows = qr.fetch_sku_master_rows(actor.tenant_id)
    return {"items": [_serialize_master_row(r) for r in rows]}


@router.get("/sku-options")
def get_sku_cost_picker_options(actor: Actor = Depends(get_actor)):
    """SKU list + labels «nome — armação — lente» para modo «Por nome» (paridade Streamlit)."""
    from database.repositories import query_repository as qr

    sku_rows = qr.fetch_sku_master_rows(actor.tenant_id)
    sku_list = [str(r["sku"]).strip() for r in sku_rows if r.get("sku")]
    if not sku_list:
        return {"skus": [], "pick_by_name": []}

    name_map = qr.fetch_product_triple_label_by_sku(actor.tenant_id)
    dup_count: dict[str, int] = {}
    base_labels: list[tuple[str, str]] = []
    for s in sku_list:
        bl = name_map.get(s, "— — —")
        base_labels.append((bl, s))
    for bl, _ in base_labels:
        dup_count[bl] = dup_count.get(bl, 0) + 1
    name_pairs: list[tuple[str, str]] = []
    for bl, s in base_labels:
        disp = f"{bl} — [{s}]" if dup_count.get(bl, 0) > 1 else bl
        name_pairs.append((disp, s))
    name_pairs.sort(key=lambda t: (t[0].lower(), t[1]))
    return {
        "skus": sku_list,
        "pick_by_name": [{"label": disp, "sku": s} for disp, s in name_pairs],
    }


@router.get("/composition")
def get_composition_state(sku: str = Query(..., min_length=1), actor: Actor = Depends(get_actor)):
    from database.repositories import query_repository as qr
    from utils.formatters import format_qty_display_4

    s = sku.strip()
    rows = qr.fetch_sku_cost_components_for_sku(s, actor.tenant_id)
    master_rows = qr.fetch_sku_master_rows(actor.tenant_id)
    saved_total = 0.0
    for r in master_rows:
        if str(r.get("sku") or "").strip() == s:
            saved_total = float(r.get("structured_cost_total") or 0)
            break
    out_lines = []
    for row in rows:
        q = float(row.get("quantity") or 0)
        out_lines.append(
            {
                **row,
                "quantity_text": format_qty_display_4(q) if q else "",
            }
        )
    return {
        "sku": s,
        "components": out_lines,
        "last_saved_structured_total": saved_total,
    }


class PreviewLineIn(BaseModel):
    component_key: str
    quantity_text: str = ""
    unit_price: float = 0.0


class PreviewCompositionBody(BaseModel):
    lines: list[PreviewLineIn] = Field(default_factory=list)


@router.post("/preview-composition")
def post_preview_composition(
    body: PreviewCompositionBody,
    _actor: Actor = Depends(get_actor),
):
    """Totais por linha e total ao vivo — parsing no servidor (paridade Streamlit)."""
    from services.domain_constants import SKU_COST_COMPONENT_DEFINITIONS
    from utils.validators import parse_cost_quantity_text, parse_cost_unit_price_value
    by_key = {ln.component_key: ln for ln in body.lines}
    line_out: list[dict[str, Any]] = []
    err_msgs: list[str] = []
    live_total = 0.0

    for key, label in SKU_COST_COMPONENT_DEFINITIONS:
        ln = by_key.get(key)
        raw_q = (ln.quantity_text if ln else "") or ""
        raw_p = float(ln.unit_price) if ln else 0.0
        qv, qe = parse_cost_quantity_text(str(raw_q))
        pv, pe = parse_cost_unit_price_value(raw_p)
        line_total: Optional[float] = None
        if qe:
            err_msgs.append(f"{label} — quantidade: {qe}")
        if pe:
            err_msgs.append(f"{label} — preço unit.: {pe}")
        if not qe and not pe:
            line_total = round(qv * pv, 2)
            live_total += line_total
        line_out.append(
            {
                "component_key": key,
                "label": label,
                "quantity_parsed": qv if not qe else None,
                "unit_price_parsed": pv if not pe else None,
                "line_total": line_total,
                "quantity_error": qe,
                "price_error": pe,
            }
        )

    return {
        "lines": line_out,
        "live_total": round(live_total, 2),
        "errors": err_msgs,
        "has_errors": bool(err_msgs),
    }


@router.get("/stock-cost-history")
def get_stock_cost_history(
    limit: int = Query(75, ge=1, le=200),
    actor: Actor = Depends(get_actor),
):
    from database.repositories import query_repository as qr

    rows = qr.fetch_recent_stock_cost_entries(limit, actor.tenant_id)
    out: list[dict[str, Any]] = []
    for r in rows:
        q = float(r.get("quantity") or 0)
        uc = float(r.get("unit_cost") or 0)
        te = r.get("total_entry_cost")
        if te is None:
            te = round(q * uc, 2)
        else:
            te = float(te)
        out.append(
            {
                "id": int(r["id"]) if r.get("id") is not None else None,
                "product_id": int(r["product_id"]) if r.get("product_id") is not None else None,
                "created_at": str(r.get("created_at") or ""),
                "sku": str(r.get("sku") or ""),
                "quantity": q,
                "unit_cost": uc,
                "total_cost": te,
                "stock_before": float(r.get("stock_before") or 0),
                "stock_after": float(r.get("stock_after") or 0),
                "cmp_before": float(r.get("avg_cost_before") or 0),
                "cmp_after": float(r.get("avg_cost_after") or 0),
            }
        )
    return {"items": out}


class ParseQuantityBody(BaseModel):
    quantity_text: str = ""


@router.post("/parse-quantity-text")
def post_parse_quantity_text(
    body: ParseQuantityBody,
    _actor: Actor = Depends(get_actor_read),
):
    """Validação ao vivo da quantidade de entrada (paridade Streamlit Custos)."""
    from utils.validators import parse_cost_quantity_text

    raw = str(body.quantity_text or "")
    trimmed = raw.strip()
    if trimmed == "":
        return {"error": None, "parsed": None, "positive_ok": False}
    qv, qe = parse_cost_quantity_text(raw)
    if qe:
        return {"error": qe, "parsed": None, "positive_ok": False}
    if qv <= 0:
        return {
            "error": "A quantidade deve ser maior que zero.",
            "parsed": qv,
            "positive_ok": False,
        }
    return {"error": None, "parsed": qv, "positive_ok": True}


@router.get("/stock-entry")
def get_stock_entry_context(sku: str = Query(..., min_length=1), actor: Actor = Depends(get_actor)):
    """Custo unitário estruturado (read-only) + lotes + componentes (read-only)."""
    from database.repositories import query_repository as qr
    from utils.formatters import format_qty_display_4

    s = sku.strip()
    try:
        unit_cost = float(qr.get_persisted_structured_unit_cost(s, actor.tenant_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    batches_raw = qr.fetch_product_batches_for_sku(s, actor.tenant_id)
    batches: list[dict[str, Any]] = []
    for p in batches_raw:
        attrs = " · ".join(
            x
            for x in (
                p.get("frame_color") or "",
                p.get("lens_color") or "",
                p.get("style") or "",
                p.get("palette") or "",
                p.get("gender") or "",
            )
            if x
        )
        extra = f" ({attrs})" if attrs else ""
        batches.append(
            {
                "id": int(p["id"]),
                "sku": str(p.get("sku") or "").strip(),
                "name": str(p.get("name") or ""),
                "product_enter_code": p.get("product_enter_code"),
                "stock": float(p.get("stock") or 0),
                "label": (
                    f"{p.get('name') or ''}{extra} | Cód.: {p.get('product_enter_code') or '—'} | "
                    f"Estoque: {format_qty_display_4(float(p.get('stock') or 0))}"
                ),
            }
        )

    components = qr.fetch_sku_cost_components_for_sku(s, actor.tenant_id)
    comp_view = [
        {
            "componente": r.get("label"),
            "preço_unit": float(r.get("unit_price") or 0),
            "qtd": float(r.get("quantity") or 0),
            "linha": float(r.get("line_total") or 0),
        }
        for r in components
    ]

    return {
        "sku": s,
        "structured_unit_cost": unit_cost,
        "batches": batches,
        "components_readonly": comp_view,
    }
