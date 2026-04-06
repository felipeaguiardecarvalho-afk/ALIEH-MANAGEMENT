"""Contexto de inquilino para a UI — delega a database sem expor a app a database.tenancy."""

from __future__ import annotations

from database.tenancy import effective_tenant_id_for_request

__all__ = ["effective_tenant_id_for_request"]
