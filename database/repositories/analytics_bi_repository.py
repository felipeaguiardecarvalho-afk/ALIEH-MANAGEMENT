"""Consultas SQL agregadas para BI (dual-mode via use_connection / get_db_conn)."""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from database.queries import _painel_sales_where
from database.repositories.support import use_connection
from database.sql_compat import db_execute
from database.tenancy import effective_tenant_id_for_request


def fetch_margin_by_sku(
    date_start: str,
    date_end: str,
    tenant_id: str | None = None,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    limit: int = 40,
) -> pd.DataFrame:
    """
    Receita, lucro e margem % por SKU no período (GROUP BY no SQL).
    """
    tid = effective_tenant_id_for_request(tenant_id)
    where, params = _painel_sales_where(
        tid, date_start, date_end, sku, customer_id, product_id
    )
    lim = max(1, min(int(limit), 200))
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            f"""
            SELECT
                TRIM(s.sku) AS sku,
                COALESCE(SUM(s.total), 0) AS revenue,
                COALESCE(SUM(s.total - COALESCE(s.cogs_total, 0)), 0) AS profit,
                COALESCE(SUM(s.quantity), 0) AS qty,
                CASE
                    WHEN COALESCE(SUM(s.total), 0) > 0
                    THEN 100.0 * SUM(s.total - COALESCE(s.cogs_total, 0)) / SUM(s.total)
                    ELSE 0.0
                END AS margin_pct
            FROM sales s
            WHERE {where}
              AND s.sku IS NOT NULL AND TRIM(s.sku) != ''
            GROUP BY TRIM(s.sku)
            ORDER BY revenue DESC
            LIMIT ?;
            """,
            params + [lim],
        ).fetchall()
    if not rows:
        return pd.DataFrame(
            columns=["sku", "revenue", "profit", "qty", "margin_pct"]
        )
    return pd.DataFrame(
        [
            {
                "sku": r["sku"],
                "revenue": float(r["revenue"]),
                "profit": float(r["profit"]),
                "qty": float(r["qty"]),
                "margin_pct": float(r["margin_pct"]),
            }
            for r in rows
        ]
    )


def fetch_stock_turnover_by_sku(
    date_start: str,
    date_end: str,
    tenant_id: str | None = None,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    limit: int = 30,
) -> pd.DataFrame:
    """
    Razão unidades vendidas / stock actual no mestre (proxy de rotação no período).
    Maior valor → maior giro relativo ao inventário declarado.
    """
    tid = effective_tenant_id_for_request(tenant_id)
    where, params = _painel_sales_where(
        tid, date_start, date_end, sku, customer_id, product_id
    )
    lim = max(1, min(int(limit), 100))
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            f"""
            SELECT
                TRIM(s.sku) AS sku,
                COALESCE(SUM(s.quantity), 0) AS units_sold,
                COALESCE(MAX(sm.total_stock), 0) AS stock_on_hand,
                CASE
                    WHEN COALESCE(MAX(sm.total_stock), 0) > 0
                    THEN 1.0 * SUM(s.quantity) / MAX(sm.total_stock)
                    ELSE NULL
                END AS turnover_ratio
            FROM sales s
            LEFT JOIN sku_master sm
              ON sm.tenant_id = s.tenant_id
             AND TRIM(COALESCE(sm.sku, '')) = TRIM(COALESCE(s.sku, ''))
             AND sm.deleted_at IS NULL
            WHERE {where}
              AND s.sku IS NOT NULL AND TRIM(s.sku) != ''
            GROUP BY TRIM(s.sku)
            HAVING COALESCE(SUM(s.quantity), 0) > 0
            ORDER BY units_sold DESC
            LIMIT ?;
            """,
            params + [lim],
        ).fetchall()
    if not rows:
        return pd.DataFrame(
            columns=["sku", "units_sold", "stock_on_hand", "turnover_ratio"]
        )
    return pd.DataFrame(
        [
            {
                "sku": r["sku"],
                "units_sold": float(r["units_sold"]),
                "stock_on_hand": float(r["stock_on_hand"] or 0),
                "turnover_ratio": float(r["turnover_ratio"])
                if r["turnover_ratio"] is not None
                else None,
            }
            for r in rows
        ]
    )


def fetch_customer_cohort_by_first_purchase(
    tenant_id: str | None = None,
) -> pd.DataFrame:
    """
    Agrupa clientes pelo mês da primeira compra (YYYY-MM).

    Cohort simples: contagens por ``cohort_month``.
    """
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            """
            WITH first_buy AS (
                SELECT
                    customer_id,
                    MIN(substr(sold_at, 1, 7)) AS cohort_month
                FROM sales
                WHERE tenant_id = ?
                  AND customer_id IS NOT NULL
                GROUP BY customer_id
            )
            SELECT cohort_month, COUNT(*) AS n_customers
            FROM first_buy
            GROUP BY cohort_month
            ORDER BY cohort_month;
            """,
            (tid,),
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["cohort_month", "n_customers"])
    return pd.DataFrame(
        [
            {"cohort_month": r["cohort_month"], "n_customers": int(r["n_customers"])}
            for r in rows
        ]
    )


def fetch_sku_stock_aging(
    tenant_id: str | None = None,
    min_days_no_sale: int = 30,
    limit: int = 50,
) -> pd.DataFrame:
    """
    SKUs com stock > 0 e última venda há mais de ``min_days_no_sale`` dias,
    ou nunca vendidos (last_sale_day ausente).
    """
    tid = effective_tenant_id_for_request(tenant_id)
    lim = max(1, min(int(limit), 200))
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            """
            SELECT
                sm.sku,
                COALESCE(sm.total_stock, 0) AS total_stock,
                MAX(substr(s.sold_at, 1, 10)) AS last_sale_day
            FROM sku_master sm
            LEFT JOIN sales s
              ON s.tenant_id = sm.tenant_id
             AND TRIM(COALESCE(s.sku, '')) = TRIM(COALESCE(sm.sku, ''))
            WHERE sm.tenant_id = ?
              AND sm.deleted_at IS NULL
              AND COALESCE(sm.total_stock, 0) > 0
            GROUP BY sm.sku, sm.total_stock
            ORDER BY sm.total_stock DESC;
            """,
            (tid,),
        ).fetchall()

    if not rows:
        return pd.DataFrame(
            columns=[
                "sku",
                "total_stock",
                "last_sale_day",
                "days_since_sale",
                "aging_flag",
            ]
        )

    records: list[dict[str, Any]] = []
    for r in rows:
        raw_last = r["last_sale_day"]
        records.append(
            {
                "sku": str(r["sku"]).strip(),
                "total_stock": float(r["total_stock"] or 0),
                "last_sale_day": str(raw_last).strip()
                if raw_last is not None and str(raw_last).strip()
                else None,
            }
        )

    df = pd.DataFrame(records)
    today = pd.Timestamp.now(tz=None).normalize()
    day_series = pd.to_datetime(df["last_sale_day"], errors="coerce")
    df["days_since_sale"] = (today - day_series).dt.days
    df["aging_flag"] = "com_venda"
    never = df["last_sale_day"].isna()
    df.loc[never, "days_since_sale"] = float(min_days_no_sale + 1)
    df.loc[never, "aging_flag"] = "nunca_vendido"

    df = df.loc[
        never | (df["days_since_sale"] >= float(min_days_no_sale))
    ].sort_values(
        ["days_since_sale", "total_stock"], ascending=[False, False]
    )
    return df.head(lim).reset_index(drop=True)
