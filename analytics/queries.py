"""Consultas SQL agregadas para BI — implementação em :mod:`database.repositories.analytics_bi_repository`."""

from __future__ import annotations

from database.repositories.analytics_bi_repository import (  # noqa: F401
    fetch_customer_cohort_by_first_purchase,
    fetch_margin_by_sku,
    fetch_sku_stock_aging,
    fetch_stock_turnover_by_sku,
)
