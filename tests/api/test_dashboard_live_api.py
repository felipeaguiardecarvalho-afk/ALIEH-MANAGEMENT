"""Painel: resposta mínima do GET /dashboard/panel."""

from __future__ import annotations

import pytest

from tests.api.conftest import _api_base, api_http_get, is_alieh_prototype_health_payload
from tests.factories.headers import actor_headers

pytestmark = pytest.mark.live_api

skip_no_url = pytest.mark.skipif(not _api_base(), reason="Defina ALIEH_API_TEST_URL")


@skip_no_url
def test_dashboard_panel_has_core_keys():
    st0, hb = api_http_get("/health")
    if st0 != 200 or not is_alieh_prototype_health_payload(hb):
        pytest.skip("ALIEH_API_TEST_URL não é a api-prototype ALIEH.")
    status, body = api_http_get(
        "/dashboard/panel?date_start=2025-01-01&date_end=2025-01-31",
        headers=actor_headers(role="admin"),
    )
    assert status == 200
    assert isinstance(body, dict)
    for key in (
        "kpis",
        "low_stock",
        "inventory_summary",
        "insights",
        "daily",
        "date_start",
        "date_end",
    ):
        assert key in body, f"missing {key}"
    assert isinstance(body["low_stock"], list)
    inv = body["inventory_summary"]
    assert "n_critical_skus" in inv
    assert "total_units" in inv
