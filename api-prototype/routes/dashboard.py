from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from analytics.transformations import add_rolling_mean, kpi_delta_pct
from database.repositories import analytics_bi_repository as bi_repo
from database.repositories.support import use_connection
from database.repositories import query_repository as qr
from database.sql_compat import db_execute
from database.tenancy import effective_tenant_id_for_request
from deps import Actor, get_actor

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _df_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    out: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        d: dict[str, Any] = {}
        for k in df.columns:
            v = row[k]
            d[k] = None if pd.isna(v) else v
        out.append(d)
    return out


def _prev_range(d0: date, d1: date) -> tuple[date, date]:
    n_days = (d1 - d0).days + 1
    p_end = d0 - timedelta(days=1)
    p_start = p_end - timedelta(days=n_days - 1)
    return p_start, p_end


def _clamp_int(raw: str, lo: int, hi: int, default: int) -> int:
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _fetch_stock_units(tenant_id: str | None) -> float:
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        row = db_execute(
            conn,
            """
            SELECT COALESCE(SUM(stock), 0) AS u
            FROM products
            WHERE tenant_id = %s AND deleted_at IS NULL;
            """,
            (tid,),
        ).fetchone()
    return float(row["u"] or 0) if row else 0.0


def _count_active_customers(
    tenant_id: str | None, window_end: date, window_days: int
) -> int:
    """Clientes distintos com venda no intervalo [window_end - (d-1), window_end]."""
    d = max(1, window_days)
    start = window_end - timedelta(days=d - 1)
    ds = start.isoformat()
    de = window_end.isoformat()
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        row = db_execute(
            conn,
            """
            SELECT COUNT(DISTINCT customer_id) AS c
            FROM sales
            WHERE tenant_id = %s
              AND customer_id IS NOT NULL
              AND substr(sold_at, 1, 10) >= %s
              AND substr(sold_at, 1, 10) <= %s;
            """,
            (tid, ds, de),
        ).fetchone()
    return int(row["c"] or 0) if row else 0


def _enrich_top_customers(
    df: pd.DataFrame, tenant_id: str | None
) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    tid = effective_tenant_id_for_request(tenant_id)
    ids = [int(x) for x in df["customer_id"].tolist()]
    placeholders = ",".join(["%s"] * len(ids))
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            f"""
            SELECT id, customer_code, name
            FROM customers
            WHERE tenant_id = %s AND id IN ({placeholders});
            """,
            [tid, *ids],
        ).fetchall()
    id_to = {int(r["id"]): r for r in rows}
    out: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        cid = int(r["customer_id"])
        meta = id_to.get(cid, {})
        out.append(
            {
                "customer_id": cid,
                "customer_code": str(meta.get("customer_code") or ""),
                "customer_name": str(meta.get("name") or ""),
                "revenue": float(r["revenue"]),
                "n_orders": int(r["n_orders"]),
            }
        )
    return out


def _low_stock_records(tenant_id: str | None, threshold: float, limit: int) -> list[dict[str, Any]]:
    df = qr.fetch_low_stock_products_dashboard(
        tenant_id=tenant_id, threshold=threshold, limit=limit
    )
    if df is None or df.empty:
        return []
    rows: list[dict[str, Any]] = []
    thr = float(threshold)
    for _, r in df.iterrows():
        stock = float(r["stock"] or 0)
        # Defesa em profundidade: só emitir linhas que cumprem o limiar (evita dados fora do SQL por versões antigas / cache).
        if stock > thr + 1e-9:
            continue
        rows.append(
            {
                "id": int(r["id"]),
                "sku": str(r.get("sku") or ""),
                "name": str(r.get("name") or ""),
                "unit_cost": float(r.get("unit_cost") or 0),
                "sell_price": float(r.get("sell_price") or 0),
                "stock": stock,
                # Tabela só inclui stock ≤ limiar: esgotado vs última unidade (quando limiar = 1)
                "priority": "critical" if stock <= 0 else "low",
            }
        )
    return rows


def _build_insights(
    kpis_cur: dict[str, Any],
    kpis_prev: dict[str, Any],
    top_skus_df: pd.DataFrame,
    top_cust_enriched: list[dict[str, Any]],
    inv_summary: dict[str, Any],
    *,
    critical_stock_threshold: float = 1.0,
) -> list[str]:
    lines: list[str] = []
    rev = float(kpis_cur.get("revenue") or 0)
    prev_rev = float(kpis_prev.get("revenue") or 0)

    if top_skus_df is not None and not top_skus_df.empty and rev > 0:
        row0 = top_skus_df.iloc[0]
        sku = str(row0.get("sku") or "").strip() or "—"
        top_rev = float(row0.get("revenue") or 0)
        pct = 100.0 * top_rev / rev
        lines.append(
            f"O SKU «{sku}» concentra {pct:.1f}% da receita do período seleccionado."
        )

    if prev_rev > 0:
        m_cur = float(kpis_cur.get("margin_pct") or 0)
        m_prev = float(kpis_prev.get("margin_pct") or 0)
        mpp_diff = m_cur - m_prev
        if abs(mpp_diff) >= 0.5:
            verb = "subiu" if mpp_diff > 0 else "desceu"
            lines.append(
                f"A margem bruta {verb} {abs(mpp_diff):.1f} p.p. face ao período anterior ({m_prev:.1f}% → {m_cur:.1f}%)."
            )

    n_crit = int(inv_summary.get("n_critical_skus") or 0)
    if n_crit > 0:
        thr = int(critical_stock_threshold) if critical_stock_threshold == int(critical_stock_threshold) else critical_stock_threshold
        lines.append(
            f"Há {n_crit} registo(s) de produto com stock ≤ {thr} unidade(s) — rever reposição ou precificação."
        )

    if top_cust_enriched and rev > 0:
        t0 = top_cust_enriched[0]
        nm = (t0.get("customer_name") or "").strip() or "—"
        code = (t0.get("customer_code") or "").strip() or "—"
        tr = float(t0.get("revenue") or 0)
        lines.append(
            f"Cliente em destaque: {nm} ({code}) com {tr:.2f} R$ de receita no período."
        )

    if not lines:
        lines.append(
            "Sem destaques adicionais para o filtro actual — ajuste o período ou as dimensões."
        )
    return lines


@router.get("/filters")
def get_dashboard_filters(actor: Actor = Depends(get_actor)):
    tid = effective_tenant_id_for_request(actor.tenant_id)
    with use_connection(None) as conn:
        sku_rows = db_execute(
            conn,
            """
            SELECT DISTINCT TRIM(sku) AS sku
            FROM sales
            WHERE tenant_id = %s AND sku IS NOT NULL AND TRIM(COALESCE(sku, '')) != ''
            ORDER BY sku
            LIMIT 500;
            """,
            (tid,),
        ).fetchall()
        prod_rows = db_execute(
            conn,
            """
            SELECT id, name
            FROM products
            WHERE tenant_id = %s AND deleted_at IS NULL
            ORDER BY id DESC
            LIMIT 400;
            """,
            (tid,),
        ).fetchall()
        cust_rows = db_execute(
            conn,
            """
            SELECT id, customer_code, name
            FROM customers
            WHERE tenant_id = %s
            ORDER BY customer_code
            LIMIT 500;
            """,
            (tid,),
        ).fetchall()
    return {
        "skus": [str(r["sku"]) for r in sku_rows if r.get("sku")],
        "products": [
            {"id": int(r["id"]), "name": str(r.get("name") or "")} for r in prod_rows
        ],
        "customers": [
            {
                "id": int(r["id"]),
                "customer_code": str(r.get("customer_code") or ""),
                "name": str(r.get("name") or ""),
            }
            for r in cust_rows
        ],
    }


def _opt_pos_int(raw: str) -> Optional[int]:
    s = (raw or "").strip()
    if not s.isdigit():
        return None
    n = int(s)
    return n if n > 0 else None


@router.get("/panel")
def get_dashboard_panel(
    date_start: str = Query("", description="YYYY-MM-DD"),
    date_end: str = Query("", description="YYYY-MM-DD"),
    sku: str = "",
    customer_id: str = Query(""),
    product_id: str = Query(""),
    aging_min_days: str = Query("45", description="15–180 for stock aging table"),
    active_customer_days: str = Query(
        "90", description="7–365 rolling window ending at date_end"
    ),
    actor: Actor = Depends(get_actor),
):
    try:
        end = (
            date.fromisoformat((date_end or "").strip()[:10])
            if (date_end or "").strip()
            else date.today()
        )
        start_raw = (date_start or "").strip()[:10]
        if start_raw:
            start = date.fromisoformat(start_raw)
        else:
            start = end - timedelta(days=30)
        if start > end:
            start, end = end, start
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail="Datas inválidas; use YYYY-MM-DD."
        ) from e

    aging_days = _clamp_int(aging_min_days, 15, 180, 45)
    active_days = _clamp_int(active_customer_days, 7, 365, 90)

    ds = start.isoformat()
    de = end.isoformat()
    sku_f = sku.strip() or None
    cust_f = _opt_pos_int(customer_id)
    prod_f = _opt_pos_int(product_id)

    p_start, p_end = _prev_range(start, end)
    p_ds = p_start.isoformat()
    p_de = p_end.isoformat()

    kpis = qr.fetch_dashboard_kpis_period(
        ds, de, actor.tenant_id, sku_f, cust_f, prod_f
    )
    kpis_prev = qr.fetch_dashboard_kpis_period(
        p_ds, p_de, actor.tenant_id, sku_f, cust_f, prod_f
    )
    stock_units = _fetch_stock_units(actor.tenant_id)

    daily_df = qr.fetch_daily_revenue_profit(
        ds, de, actor.tenant_id, sku_f, cust_f, prod_f
    )
    if daily_df is not None and not daily_df.empty:
        daily_df = add_rolling_mean(daily_df, "revenue", "day", 7, "revenue_ma7")

    top_skus_df = qr.fetch_top_skus_by_metric(
        ds, de, actor.tenant_id, sku_f, cust_f, prod_f, limit=12
    )
    top_products_df = qr.fetch_top_product_names_by_revenue(
        ds, de, actor.tenant_id, sku_f, cust_f, prod_f, limit=10
    )
    top_cust_df = qr.fetch_top_customers_by_revenue(
        ds, de, actor.tenant_id, sku_f, cust_f, prod_f, limit=10
    )
    pay_df = qr.fetch_payment_method_breakdown(
        ds, de, actor.tenant_id, sku_f, cust_f, prod_f
    )

    margin_df = bi_repo.fetch_margin_by_sku(
        ds, de, actor.tenant_id, sku_f, cust_f, prod_f, limit=25
    )
    if margin_df is not None and not margin_df.empty:
        margin_chart = margin_df.head(12).sort_values("margin_pct")
    else:
        margin_chart = pd.DataFrame(columns=["sku", "revenue", "profit", "qty", "margin_pct"])

    cohort_df = bi_repo.fetch_customer_cohort_by_first_purchase(actor.tenant_id)
    aging_df = bi_repo.fetch_sku_stock_aging(
        tenant_id=actor.tenant_id,
        min_days_no_sale=aging_days,
        limit=35,
    )
    _crit_thr = 1.0
    inv_summary = qr.fetch_inventory_stock_summary(actor.tenant_id, critical_threshold=_crit_thr)
    low_stock = _low_stock_records(actor.tenant_id, threshold=_crit_thr, limit=45)
    active_customers = _count_active_customers(actor.tenant_id, end, active_days)

    turnover_df = bi_repo.fetch_stock_turnover_by_sku(
        ds, de, actor.tenant_id, sku_f, cust_f, prod_f, limit=20
    )

    cust_enriched = _enrich_top_customers(top_cust_df, actor.tenant_id)
    total_cust_rev = sum(float(c.get("revenue") or 0) for c in cust_enriched)
    for c in cust_enriched:
        tr = float(c.get("revenue") or 0)
        c["revenue_share_pct"] = (100.0 * tr / total_cust_rev) if total_cust_rev > 0 else 0.0

    dr = kpi_delta_pct(float(kpis["revenue"]), float(kpis_prev["revenue"]))
    d_sales = kpi_delta_pct(
        float(kpis["sales_count"]), float(kpis_prev["sales_count"])
    )
    dt = kpi_delta_pct(float(kpis["ticket_avg"]), float(kpis_prev["ticket_avg"]))
    margin_pp = float(kpis["margin_pct"]) - float(kpis_prev["margin_pct"])

    insights = _build_insights(
        kpis,
        kpis_prev,
        top_skus_df,
        cust_enriched,
        inv_summary,
        critical_stock_threshold=_crit_thr,
    )

    return {
        "date_start": ds,
        "date_end": de,
        "prev_date_start": p_ds,
        "prev_date_end": p_de,
        "filters": {
            "sku": sku_f or "",
            "customer_id": cust_f,
            "product_id": prod_f,
            "aging_min_days": aging_days,
            "active_customer_days": active_days,
        },
        "kpis": {
            **kpis,
            "stock_units": stock_units,
        },
        "kpis_previous": {**kpis_prev, "stock_units": stock_units},
        "kpi_deltas": {
            "revenue_pct": dr,
            "sales_count_pct": d_sales,
            "ticket_avg_pct": dt,
            "margin_pp": margin_pp,
        },
        "active_customers_window": active_customers,
        "daily": _df_records(daily_df),
        "breakdown_skus": _df_records(top_skus_df),
        "breakdown_products": _df_records(top_products_df),
        "breakdown_customers": cust_enriched,
        "breakdown_payment": _df_records(pay_df),
        "margin_by_sku": _df_records(margin_chart),
        "cohort": _df_records(cohort_df),
        "stock_aging": _df_records(aging_df),
        "low_stock": low_stock,
        "inventory_summary": inv_summary,
        "insights": insights,
        "stock_turnover": _df_records(turnover_df),
    }
