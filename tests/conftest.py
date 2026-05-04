"""Hooks globais de pytest — endurecimento de CI."""

from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Gate Docker (`ALIEH_QA_GATE=1`) e CI (`live_api`)."""
    if (os.environ.get("ALIEH_QA_GATE") or "").strip() == "1":
        if not (os.environ.get("DATABASE_URL") or "").strip():
            pytest.exit("ALIEH_QA_GATE=1: defina DATABASE_URL (Postgres do gate).", returncode=2)
        if (os.environ.get("ALIEH_PG_INTEGRATION") or "").strip().lower() not in ("1", "true", "yes"):
            pytest.exit("ALIEH_QA_GATE=1: defina ALIEH_PG_INTEGRATION=1.", returncode=2)
        if not (os.environ.get("ALIEH_API_TEST_URL") or "").strip():
            pytest.exit("ALIEH_QA_GATE=1: defina ALIEH_API_TEST_URL (URL da api-prototype).", returncode=2)

    if (os.environ.get("CI") or "").strip().lower() not in ("1", "true", "yes"):
        return
    if (os.environ.get("ALIEH_REQUIRE_API_URL_IN_CI") or "1").strip().lower() in ("0", "false", "no"):
        return
    if not (os.environ.get("ALIEH_API_TEST_URL") or "").strip():
        # Não falhamos na recolha global (permite jobs só unitários). Falha ao executar live_api.
        return


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Node) -> None:
    if not item.get_closest_marker("live_api"):
        return
    if (os.environ.get("CI") or "").strip().lower() not in ("1", "true", "yes"):
        return
    if (os.environ.get("ALIEH_REQUIRE_API_URL_IN_CI") or "1").strip().lower() in ("0", "false", "no"):
        return
    if not (os.environ.get("ALIEH_API_TEST_URL") or "").strip():
        pytest.fail(
            "CI: defina ALIEH_API_TEST_URL (URL da api-prototype) para que os testes live_api não saltem."
        )
