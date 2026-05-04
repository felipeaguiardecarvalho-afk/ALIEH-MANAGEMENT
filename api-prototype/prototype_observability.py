"""Logging estruturado (JSON) e ID de correlação por pedido (api-prototype)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from prototype_metrics import inc_error, inc_request, snapshot
from request_context import clear_actor_for_log, get_actor_for_log

_logger = logging.getLogger("alieh.prototype.http")


class CorrelationAndAccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        clear_actor_for_log()
        rid = (request.headers.get("X-Request-Id") or "").strip() or uuid.uuid4().hex
        t0 = time.perf_counter()
        path = request.url.path
        method = request.method
        inc_request()
        try:
            response = await call_next(request)
        except Exception:
            ms = (time.perf_counter() - t0) * 1000.0
            inc_error()
            actor = get_actor_for_log()
            _logger.exception(
                json.dumps(
                    {
                        "event": "request_failed",
                        "request_id": rid,
                        "endpoint": path,
                        "method": method,
                        "actor_id": actor[0] if actor else None,
                        "tenant_id": actor[1] if actor else None,
                        "role": actor[2] if actor else None,
                        "duration_ms": round(ms, 2),
                        "success": False,
                        **snapshot(),
                    },
                    ensure_ascii=False,
                )
            )
            raise
        ms = (time.perf_counter() - t0) * 1000.0
        response.headers["X-Request-Id"] = rid
        actor = get_actor_for_log()
        status = response.status_code
        if status >= 500:
            inc_error()
        payload = {
            "event": "request_complete",
            "request_id": rid,
            "endpoint": path,
            "method": method,
            "actor_id": actor[0] if actor else None,
            "tenant_id": actor[1] if actor else None,
            "role": actor[2] if actor else None,
            "duration_ms": round(ms, 2),
            "status_code": status,
            "success": status < 400,
            **snapshot(),
        }
        _logger.info(json.dumps(payload, ensure_ascii=False))
        return response
