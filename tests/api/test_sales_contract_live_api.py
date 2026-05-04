"""Contratos seguros em /sales/* (sem gravar venda válida sem ambiente descartável)."""

from __future__ import annotations

import pytest

from tests.api.conftest import _api_base, api_http_get, api_http_post_json, is_alieh_prototype_health_payload
from tests.factories.headers import actor_headers
from tests.factories.sale_payloads import minimal_preview_body

pytestmark = pytest.mark.live_api

skip_no_url = pytest.mark.skipif(not _api_base(), reason="Defina ALIEH_API_TEST_URL")


@skip_no_url
def test_submit_without_idempotency_key_rejected():
    """POST /sales/submit exige cabeçalho Idempotency-Key."""
    st, hb = api_http_get("/health")
    if st != 200 or not is_alieh_prototype_health_payload(hb):
        pytest.skip("ALIEH_API_TEST_URL não é a api-prototype ALIEH.")
    status, body = api_http_post_json(
        "/sales/submit",
        minimal_preview_body(),
        headers=actor_headers(role="admin"),
    )
    assert status == 400
    assert body is not None
    detail = body.get("detail") if isinstance(body, dict) else str(body)
    text = detail if isinstance(detail, str) else str(detail)
    assert "Idempotency" in text or "idempotency" in text.lower() or "obrigatório" in text.lower()
