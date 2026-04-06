"""
Métricas de negócio de alto nível (encapsulam SQL agregado + pandas).

Todas respeitam ``effective_tenant_id_for_request`` via :mod:`services.read_queries`
e :mod:`analytics.queries`.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from analytics.queries import (
    fetch_customer_cohort_by_first_purchase,
    fetch_margin_by_sku,
    fetch_sku_stock_aging,
    fetch_stock_turnover_by_sku,
)
from services.read_queries import (
    fetch_daily_revenue_profit,
    fetch_dashboard_kpis_period,
    fetch_low_stock_products_dashboard,
    fetch_top_skus_by_metric,
)


def get_total_revenue(
    date_start: str,
    date_end: str,
    *,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    tenant_id: str | None = None,
) -> float:
    """Receita líquida no período (soma de ``sales.total``)."""
    return float(
        fetch_dashboard_kpis_period(
            date_start,
            date_end,
            tenant_id=tenant_id,
            sku=sku,
            customer_id=customer_id,
            product_id=product_id,
        )["revenue"]
    )


def get_total_sales(
    date_start: str,
    date_end: str,
    *,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    tenant_id: str | None = None,
) -> int:
    """Número de linhas de venda no período."""
    return int(
        fetch_dashboard_kpis_period(
            date_start,
            date_end,
            tenant_id=tenant_id,
            sku=sku,
            customer_id=customer_id,
            product_id=product_id,
        )["sales_count"]
    )


def get_average_ticket(
    date_start: str,
    date_end: str,
    *,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    tenant_id: str | None = None,
) -> float:
    """Ticket médio (receita / nº de vendas)."""
    return float(
        fetch_dashboard_kpis_period(
            date_start,
            date_end,
            tenant_id=tenant_id,
            sku=sku,
            customer_id=customer_id,
            product_id=product_id,
        )["ticket_avg"]
    )


def get_sales_over_time(
    date_start: str,
    date_end: str,
    *,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    tenant_id: str | None = None,
) -> pd.DataFrame:
    """Série diária receita / custo / lucro."""
    return fetch_daily_revenue_profit(
        date_start,
        date_end,
        tenant_id=tenant_id,
        sku=sku,
        customer_id=customer_id,
        product_id=product_id,
    )


def get_top_products(
    date_start: str,
    date_end: str,
    *,
    limit: int = 12,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    tenant_id: str | None = None,
) -> pd.DataFrame:
    """Top SKUs por receita."""
    return fetch_top_skus_by_metric(
        date_start,
        date_end,
        tenant_id=tenant_id,
        sku=sku,
        customer_id=customer_id,
        product_id=product_id,
        limit=limit,
    )


def get_stock_turnover(
    date_start: str,
    date_end: str,
    *,
    limit: int = 20,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    tenant_id: str | None = None,
) -> pd.DataFrame:
    """Proxy de rotação: unidades vendidas / stock no mestre."""
    return fetch_stock_turnover_by_sku(
        date_start,
        date_end,
        tenant_id=tenant_id,
        sku=sku,
        customer_id=customer_id,
        product_id=product_id,
        limit=limit,
    )


def get_low_stock_alerts(
    threshold: float = 5.0,
    limit: int = 50,
    tenant_id: str | None = None,
) -> pd.DataFrame:
    """Tabela de produtos abaixo do limiar de stock."""
    return fetch_low_stock_products_dashboard(
        tenant_id=tenant_id, threshold=threshold, limit=limit
    )


def get_margin_per_sku(
    date_start: str,
    date_end: str,
    *,
    limit: int = 40,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    tenant_id: str | None = None,
) -> pd.DataFrame:
    """Margem % e lucro por SKU."""
    return fetch_margin_by_sku(
        date_start,
        date_end,
        tenant_id=tenant_id,
        sku=sku,
        customer_id=customer_id,
        product_id=product_id,
        limit=limit,
    )


def get_kpi_pack(
    date_start: str,
    date_end: str,
    prev_start: str,
    prev_end: str,
    *,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Período actual e anterior para deltas nos cartões KPI."""
    return {
        "current": fetch_dashboard_kpis_period(
            date_start,
            date_end,
            tenant_id=tenant_id,
            sku=sku,
            customer_id=customer_id,
            product_id=product_id,
        ),
        "previous": fetch_dashboard_kpis_period(
            prev_start,
            prev_end,
            tenant_id=tenant_id,
            sku=sku,
            customer_id=customer_id,
            product_id=product_id,
        ),
    }


def get_cohort_summary(tenant_id: str | None = None) -> pd.DataFrame:
    """Clientes novos por mês da primeira compra."""
    return fetch_customer_cohort_by_first_purchase(tenant_id=tenant_id)


def get_stock_aging(
    min_days: int = 45,
    limit: int = 40,
    tenant_id: str | None = None,
) -> pd.DataFrame:
    """Inventário parado ou sem histórico de venda recente."""
    return fetch_sku_stock_aging(
        tenant_id=tenant_id, min_days_no_sale=min_days, limit=limit
    )
