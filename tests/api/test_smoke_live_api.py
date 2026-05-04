"""Smoke: API acessível e /health coerente."""

from __future__ import annotations

import os

import pytest

from tests.api.conftest import _api_base, api_http_get, is_alieh_prototype_health_payload

pytestmark = pytest.mark.live_api

skip_no_url = pytest.mark.skipif(not _api_base(), reason="Defina ALIEH_API_TEST_URL (ex. http://127.0.0.1:8000)")


@skip_no_url
def test_health_returns_json_with_status():
    status, body = api_http_get("/health")
    assert status == 200
    assert isinstance(body, dict)
    if not is_alieh_prototype_health_payload(body):
        pytest.skip(
            "ALIEH_API_TEST_URL não aponta para a api-prototype ALIEH (falta sales_paths/dependencies no /health)."
        )
    assert "status" in body
    raw = str(body.get("status") or "").upper()
    assert raw in ("OK", "DEGRADED", "FAIL")
    assert body.get("prototype") is True
    assert isinstance(body["sales_paths"], list)


@skip_no_url
def test_health_includes_database_block():
    status, body = api_http_get("/health")
    assert status == 200
    assert isinstance(body, dict)
    if not is_alieh_prototype_health_payload(body):
        pytest.skip("ALIEH_API_TEST_URL não é a api-prototype ALIEH.")
    deps = body.get("dependencies") or {}
    assert "database" in deps
    assert "core_tables" in deps
