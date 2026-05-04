"""Validação e normalização de clientes — paridade com app.py (Streamlit) antes de persistir.

Lógica espelhada de ``utils.validators`` sem importar esse módulo (evita ciclo
``database`` ↔ ``utils.validators`` ao carregar a API).
"""

from __future__ import annotations

import re
from typing import Any


def _sanitize_cep_digits(cep: str) -> str:
    return re.sub(r"\D", "", cep or "")


def _normalize_cpf_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _normalize_phone_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _validate_cpf_br(value: str) -> bool:
    cpf = _normalize_cpf_digits(value)
    if len(cpf) != 11:
        return False
    if cpf == cpf[0] * 11:
        return False

    def calc_digit(base: str, factor_start: int) -> int:
        total = 0
        for i, ch in enumerate(base):
            total += int(ch) * (factor_start - i)
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    d1 = calc_digit(cpf[:9], 10)
    if int(cpf[9]) != d1:
        return False
    d2 = calc_digit(cpf[:9] + str(d1), 11)
    return int(cpf[10]) == d2


def _validate_email_optional(email: str) -> bool:
    email_stripped = (email or "").strip()
    if not email_stripped:
        return True
    return bool(
        re.match(
            r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
            email_stripped,
        )
    )


def _strip_or_none(value: str | None) -> str | None:
    t = (value or "").strip()
    return t or None


def prepare_customer_write_fields(
    *,
    name: str,
    cpf: str | None = None,
    rg: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    instagram: str | None = None,
    zip_code: str | None = None,
    street: str | None = None,
    number: str | None = None,
    neighborhood: str | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
) -> dict[str, Any]:
    """
    Valida e normaliza campos como no Streamlit (nome, CEP 8 dígitos se houver,
    CPF dígitos + dígitos verificadores, e-mail opcional válido, telefone só dígitos).
    Levanta ValueError com mensagem em português (igual ao fluxo Streamlit).
    """
    name_s = (name or "").strip()
    if not name_s:
        raise ValueError("O nome é obrigatório.")

    cep_digits = _sanitize_cep_digits(zip_code or "")
    if cep_digits and len(cep_digits) != 8:
        raise ValueError("Se o CEP for preenchido, deve ter exatamente 8 dígitos.")

    cpf_norm = _normalize_cpf_digits(cpf or "")
    cpf_out: str | None = cpf_norm if cpf_norm else None
    if cpf_out and not _validate_cpf_br(cpf_out):
        raise ValueError("CPF inválido (verifique os dígitos).")

    email_raw = (email or "").strip()
    if not _validate_email_optional(email_raw):
        raise ValueError("E-mail com formato inválido.")
    email_out = email_raw or None

    phone_norm = _normalize_phone_digits(phone or "")
    phone_out: str | None = phone_norm if phone_norm else None

    return {
        "name": name_s,
        "cpf": cpf_out,
        "rg": _strip_or_none(rg),
        "phone": phone_out,
        "email": email_out,
        "instagram": _strip_or_none(instagram),
        "zip_code": cep_digits if cep_digits else None,
        "street": _strip_or_none(street),
        "number": _strip_or_none(number),
        "neighborhood": _strip_or_none(neighborhood),
        "city": _strip_or_none(city),
        "state": _strip_or_none(state),
        "country": _strip_or_none(country),
    }
