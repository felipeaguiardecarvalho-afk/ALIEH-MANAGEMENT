"""RBAC via cabeçalhos: leitura vs mutação (sem alterar motor)."""

from __future__ import annotations

import pytest

from tests.api.conftest import _api_base, api_http_get, api_http_post_json, is_alieh_prototype_health_payload
from tests.factories.headers import actor_headers
from tests.factories.sale_payloads import minimal_preview_body

pytestmark = pytest.mark.live_api

skip_no_url = pytest.mark.skipif(not _api_base(), reason="Defina ALIEH_API_TEST_URL")


def _require_prototype_api() -> None:
    st, body = api_http_get("/health")
    if st != 200 or not is_alieh_prototype_health_payload(body):
        pytest.skip("ALIEH_API_TEST_URL deve ser a api-prototype ALIEH (uvicorn em api-prototype/).")


@skip_no_url
def test_saleable_skus_viewer_can_read():
    _require_prototype_api()
    status, body = api_http_get(
        "/sales/saleable-skus",
        headers=actor_headers(role="viewer"),
    )
    if status == 404:
        pytest.skip("GET /sales/saleable-skus → 404: confirme ALIEH_API_TEST_URL na api-prototype.")
    assert status == 200
    assert isinstance(body, dict)
    assert "items" in body


@skip_no_url
def test_saleable_skus_missing_user_id_rejected():
    _require_prototype_api()
    status, _ = api_http_get("/sales/saleable-skus", headers={"X-Role": "viewer", "X-Tenant-Id": "default"})
    assert status in (400, 422)


@skip_no_url
def test_preview_sale_viewer_forbidden():
    """POST /sales/preview exige admin|operator."""
    _require_prototype_api()
    status, _ = api_http_post_json(
        "/sales/preview",
        minimal_preview_body(),
        headers=actor_headers(role="viewer"),
    )
    assert status == 403
