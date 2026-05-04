"""Camada opcional: origem confiável e/ou segredo interno — reduz exposição pública directa da API."""

from __future__ import annotations

import os
from typing import Callable
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

def _is_public_path(path: str) -> bool:
    if path in ("/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"):
        return True
    return path.startswith("/docs/") or path.startswith("/static/")


class InternalGatewayMiddleware(BaseHTTPMiddleware):
    """
    Se ``API_PROTOTYPE_INTERNAL_SECRET`` estiver definido, exige cabeçalho
    ``X-Alieh-Internal`` com o mesmo valor em todos os pedidos excepto rotas públicas
    (``/health``, documentação OpenAPI, ``/metrics``).
    O Next deve enviar o segredo via ``API_PROTOTYPE_INTERNAL_SECRET`` (ver ``web-prototype/lib/api-prototype.ts``).
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        secret = (os.environ.get("API_PROTOTYPE_INTERNAL_SECRET") or "").strip()
        if not secret:
            return await call_next(request)
        path = request.url.path
        if path == "/metrics" or _is_public_path(path):
            return await call_next(request)
        if request.headers.get("X-Alieh-Internal", "").strip() != secret:
            return JSONResponse(
                {"detail": "API interna: cabeçalho X-Alieh-Internal em falta ou inválido."},
                status_code=403,
            )
        return await call_next(request)


class TrustedOriginMiddleware(BaseHTTPMiddleware):
    """
    Se ``API_PROTOTYPE_TRUSTED_ORIGINS`` for uma lista separada por vírgulas de origens
    (ex.: ``https://app.example.com``), rejeita pedidos **com** cabeçalho ``Origin`` que não
    estejam na lista. Pedidos sem ``Origin`` (ex.: ``fetch`` server-side do Next) passam.
    Em produção sem lista definida, regista aviso (não bloqueia).
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        raw = (os.environ.get("API_PROTOTYPE_TRUSTED_ORIGINS") or "").strip()
        if not raw:
            return await call_next(request)
        allowed = {x.strip().rstrip("/") for x in raw.split(",") if x.strip()}
        origin = (request.headers.get("origin") or "").strip().rstrip("/")
        if origin and origin not in allowed:
            return JSONResponse(
                {"detail": "Origin não autorizado para esta API."},
                status_code=403,
            )
        referer = (request.headers.get("referer") or "").strip()
        if referer and not origin:
            try:
                ref_origin = f"{urlparse(referer).scheme}://{urlparse(referer).netloc}".rstrip("/")
            except Exception:
                ref_origin = ""
            if ref_origin and ref_origin not in allowed:
                return JSONResponse(
                    {"detail": "Referer não corresponde a origens confiáveis."},
                    status_code=403,
                )
        return await call_next(request)
