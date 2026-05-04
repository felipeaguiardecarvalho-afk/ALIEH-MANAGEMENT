from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from deps import Actor, get_actor, get_actor_read, get_admin_actor

router = APIRouter(prefix="/customers", tags=["customers"])


def _jsonable_cell(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _serialize_customer_row(row) -> dict:
    return {
        "id": int(row["id"]),
        "customer_code": str(row.get("customer_code") or ""),
        "name": str(row.get("name") or ""),
        "cpf": row.get("cpf"),
        "rg": row.get("rg"),
        "phone": row.get("phone"),
        "email": row.get("email"),
        "instagram": row.get("instagram"),
        "zip_code": row.get("zip_code"),
        "street": row.get("street"),
        "number": row.get("number"),
        "neighborhood": row.get("neighborhood"),
        "city": row.get("city"),
        "state": row.get("state"),
        "country": row.get("country"),
        "created_at": _jsonable_cell(row.get("created_at")),
        "updated_at": _jsonable_cell(row.get("updated_at")),
    }


@router.get("")
def get_customers_list(actor: Actor = Depends(get_actor_read)):
    from customers_read import list_customers

    from safe_read_cache import cached_call

    tid = (actor.tenant_id or "default").strip() or "default"

    def _load():
        rows = list_customers(tenant_id=actor.tenant_id)
        return {"items": [_serialize_customer_row(r) for r in rows]}

    return cached_call(f"cust_list:{tid}", _load)


@router.get("/{customer_id}")
def get_customer(customer_id: int, actor: Actor = Depends(get_actor_read)):
    from customers_read import fetch_customer_full

    row = fetch_customer_full(customer_id=customer_id, tenant_id=actor.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    return _serialize_customer_row(row)


class CustomerFields(BaseModel):
    name: str = Field(..., min_length=1)
    cpf: Optional[str] = None
    rg: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    instagram: Optional[str] = None
    zip_code: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None

    @field_validator("name", "email", "street", "neighborhood", "city", "state", "country", mode="before")
    @classmethod
    def _strip_optional_str(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v

    @field_validator("cpf", mode="before")
    @classmethod
    def _norm_cpf(cls, v: object) -> object:
        if v is None or v == "":
            return None
        from utils.validators import normalize_cpf_digits

        d = normalize_cpf_digits(str(v))
        return d or None

    @field_validator("phone", mode="before")
    @classmethod
    def _norm_phone(cls, v: object) -> object:
        if v is None or v == "":
            return None
        from utils.validators import normalize_phone_digits

        d = normalize_phone_digits(str(v))
        return d or None

    @field_validator("rg", "instagram", "zip_code", "number", mode="before")
    @classmethod
    def _strip_or_none(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v


@router.post("")
def post_customer(body: CustomerFields, actor: Actor = Depends(get_actor)):
    from services import customer_service

    try:
        code = customer_service.insert_customer_row(
            body.name,
            body.cpf,
            body.rg,
            body.phone,
            body.email,
            body.instagram,
            body.zip_code,
            body.street,
            body.number,
            body.neighborhood,
            body.city,
            body.state,
            body.country,
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        from safe_read_cache import invalidate_tenant_sale_reads

        invalidate_tenant_sale_reads(actor.tenant_id)
    except Exception:
        pass
    return {"customer_code": code}


@router.put("/{customer_id}")
def put_customer(
    customer_id: int,
    body: CustomerFields,
    actor: Actor = Depends(get_actor),
):
    from customers_validate import prepare_customer_write_fields
    from services import customer_service

    try:
        f = prepare_customer_write_fields(**body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        customer_service.update_customer_row(
            customer_id,
            f["name"],
            f["cpf"],
            f["rg"],
            f["phone"],
            f["email"],
            f["instagram"],
            f["zip_code"],
            f["street"],
            f["number"],
            f["neighborhood"],
            f["city"],
            f["state"],
            f["country"],
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        from safe_read_cache import invalidate_tenant_sale_reads

        invalidate_tenant_sale_reads(actor.tenant_id)
    except Exception:
        pass
    return {"ok": True}


@router.delete("/{customer_id}")
def delete_customer(customer_id: int, actor: Actor = Depends(get_admin_actor)):
    from services import customer_service

    try:
        customer_service.delete_customer_row(
            customer_id, user_id=actor.user_id, tenant_id=actor.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        from safe_read_cache import invalidate_tenant_sale_reads

        invalidate_tenant_sale_reads(actor.tenant_id)
    except Exception:
        pass
    return {"ok": True}
