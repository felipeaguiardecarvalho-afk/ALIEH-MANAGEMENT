"""Fixtures partilhadas para testes da API (protótipo FastAPI)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from tests.factories.headers import actor_headers


def _api_base() -> str | None:
    raw = (os.environ.get("ALIEH_API_TEST_URL") or "").strip().rstrip("/")
    return raw or None


def api_http_get(path: str, headers: dict[str, str] | None = None, timeout: float = 15.0) -> tuple[int, Any]:
    """GET JSON; path começa com /. Erros HTTP devolvem (status, corpo JSON ou texto)."""
    base = _api_base()
    if not base:
        raise RuntimeError("ALIEH_API_TEST_URL não definido")
    url = f"{base}{path if path.startswith('/') else '/' + path}"
    req = urllib.request.Request(url, method="GET")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            if not body.strip():
                return resp.status, None
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, {"_non_json": body[:800]}
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text) if text else None
        except json.JSONDecodeError:
            parsed = text
        return e.code, parsed


def api_http_post_json(
    path: str, payload: dict[str, Any], headers: dict[str, str], timeout: float = 30.0
) -> tuple[int, Any]:
    base = _api_base()
    if not base:
        raise RuntimeError("ALIEH_API_TEST_URL não definido")
    url = f"{base}{path if path.startswith('/') else '/' + path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            if not body.strip():
                return resp.status, None
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, {"_non_json": body[:800]}
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text) if text else None
        except json.JSONDecodeError:
            parsed = text
        return e.code, parsed


def is_alieh_prototype_health_payload(body: Any) -> bool:
    """``/health`` da api-prototype inclui ``sales_paths`` e bloco ``dependencies``."""
    return isinstance(body, dict) and "sales_paths" in body and "dependencies" in body


__all__ = [
    "_api_base",
    "api_http_get",
    "api_http_post_json",
    "actor_headers",
    "is_alieh_prototype_health_payload",
]
