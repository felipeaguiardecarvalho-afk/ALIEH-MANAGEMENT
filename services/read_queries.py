"""Consultas só de leitura usadas pela app e painéis — delega a database.queries (repositórios)."""

from __future__ import annotations

import streamlit as st

from database.queries import (
    fetch_active_sku_pricing_record,
    fetch_customers_ordered as _fetch_customers_ordered_uncached,
    fetch_daily_revenue_profit,
    fetch_dashboard_kpis_period,
    fetch_inventory_stock_summary,
    fetch_low_stock_products_dashboard,
    fetch_payment_method_breakdown,
    fetch_price_history_for_sku,
    fetch_product_batches_for_sku,
    fetch_product_batches_in_stock_for_sku,
    fetch_product_by_id,
    fetch_product_search_attribute_options,
    fetch_product_triple_label_by_sku,
    fetch_products as _fetch_products_uncached,
    fetch_recent_stock_cost_entries,
    fetch_sales_date_bounds,
    fetch_skus_available_for_sale as _fetch_skus_available_for_sale_uncached,
    fetch_sku_cost_components_for_sku,
    fetch_sku_master_rows as _fetch_sku_master_rows_uncached,
    fetch_sku_pricing_records_for_sku,
    fetch_top_customers_by_revenue,
    fetch_top_skus_by_metric,
    get_persisted_structured_unit_cost,
    peek_next_customer_code_preview,
    search_products_filtered,
)


@st.cache_data(ttl=10, show_spinner=False)
def fetch_customers_ordered(tenant_id: str | None = None) -> list:
    return _fetch_customers_ordered_uncached(tenant_id=tenant_id)


@st.cache_data(ttl=10, show_spinner=False)
def fetch_products(tenant_id: str | None = None):
    return _fetch_products_uncached(tenant_id=tenant_id)


@st.cache_data(ttl=10, show_spinner=False)
def fetch_sku_master_rows(tenant_id: str | None = None):
    return _fetch_sku_master_rows_uncached(tenant_id=tenant_id)


@st.cache_data(ttl=10, show_spinner=False)
def fetch_skus_available_for_sale(tenant_id: str | None = None):
    return _fetch_skus_available_for_sale_uncached(tenant_id=tenant_id)


__all__ = [
    "fetch_active_sku_pricing_record",
    "fetch_customers_ordered",
    "fetch_daily_revenue_profit",
    "fetch_dashboard_kpis_period",
    "fetch_inventory_stock_summary",
    "fetch_low_stock_products_dashboard",
    "fetch_payment_method_breakdown",
    "fetch_price_history_for_sku",
    "fetch_product_batches_for_sku",
    "fetch_product_batches_in_stock_for_sku",
    "fetch_product_by_id",
    "fetch_product_search_attribute_options",
    "fetch_product_triple_label_by_sku",
    "fetch_products",
    "fetch_recent_stock_cost_entries",
    "fetch_sales_date_bounds",
    "fetch_skus_available_for_sale",
    "fetch_sku_cost_components_for_sku",
    "fetch_sku_master_rows",
    "fetch_sku_pricing_records_for_sku",
    "fetch_top_customers_by_revenue",
    "fetch_top_skus_by_metric",
    "get_persisted_structured_unit_cost",
    "peek_next_customer_code_preview",
    "search_products_filtered",
]
