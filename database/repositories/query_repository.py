"""Consultas somente leitura (SELECT); camada de repositório via use_connection / get_db_conn.

SQL portável via ``database.sql_compat`` (``db_execute``, ``sql_order_ci``,
``sql_numeric_sort_key_text``).
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from database.repositories.support import use_connection
from database.constants import FILTER_ANY, SKU_COST_COMPONENT_DEFINITIONS
from database.sql_compat import db_execute, sql_numeric_sort_key_text, sql_order_ci
from database.repositories.cost_components_repository import (
    ensure_sku_cost_component_rows,
)
from database.repositories.customer_sync_repository import format_customer_code
from database.tenancy import effective_tenant_id_for_request
from utils.validators import _sku_search_sanitize_text


def fetch_customers_ordered(tenant_id: str | None = None) -> list:
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        return db_execute(
            conn,
            f"""
            SELECT id, customer_code, name, cpf, rg, phone, email, instagram,
                   zip_code, street, number, neighborhood, city, state, country,
                   created_at, updated_at
            FROM customers
            WHERE tenant_id = %s
            ORDER BY {sql_numeric_sort_key_text("customer_code")};
            """,
            (tid,),
        ).fetchall()


def peek_next_customer_code_preview(tenant_id: str | None = None) -> str:
    """Read-only preview of the next code (does not consume sequence)."""
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        row = db_execute(
            conn,
            "SELECT last_value FROM customer_sequence_counter WHERE tenant_id = %s AND id = 1;",
            (tid,),
        ).fetchone()
        n = int(row["last_value"] or 0) + 1 if row else 1
        return format_customer_code(n)


def fetch_skus_available_for_sale(tenant_id: str | None = None) -> list:
    """SKUs with active price and positive aggregate stock (sku_master)."""
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        return db_execute(
            conn,
            f"""
            SELECT sm.sku,
                   COALESCE(sm.selling_price, 0) AS selling_price,
                   COALESCE(sm.total_stock, 0) AS total_stock,
                   (
                       SELECT p.name FROM products p
                       WHERE p.tenant_id = sm.tenant_id
                         AND p.sku = sm.sku AND p.deleted_at IS NULL
                       ORDER BY p.id LIMIT 1
                   ) AS sample_name
            FROM sku_master sm
            WHERE sm.tenant_id = %s
              AND sm.deleted_at IS NULL
              AND COALESCE(sm.selling_price, 0) > 0
              AND COALESCE(sm.total_stock, 0) > 0
            ORDER BY {sql_order_ci("sm.sku")};
            """,
            (tid,),
        ).fetchall()


def fetch_product_batches_in_stock_for_sku(
    sku: str, tenant_id: str | None = None
) -> list:
    """Lotes do SKU com estoque > 0 (fluxo de vendas)."""
    sku = (sku or "").strip()
    if not sku:
        return []
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        return db_execute(
            conn,
            """
            SELECT p.id, p.name, p.stock, p.product_enter_code,
                   p.frame_color, p.lens_color, p.style, p.palette, p.gender
            FROM products p
            WHERE p.tenant_id = %s AND p.sku = %s AND p.deleted_at IS NULL
              AND COALESCE(p.stock, 0) > 0
            ORDER BY p.id;
            """,
            (tid, sku),
        ).fetchall()


def fetch_sku_pricing_records_for_sku(
    sku: str, limit: int = 100, tenant_id: str | None = None
):
    """Workflow pricing history for one SKU (newest first)."""
    sku = sku.strip()
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        return db_execute(
            conn,
            """
            SELECT id, sku, avg_cost_snapshot, markup_pct, taxes_pct, interest_pct,
                   markup_kind, taxes_kind, interest_kind,
                   price_before_taxes, price_with_taxes, target_price, created_at, is_active
            FROM sku_pricing_records
            WHERE tenant_id = %s AND sku = %s
            ORDER BY id DESC
            LIMIT %s;
            """,
            (tid, sku, int(limit)),
        ).fetchall()


def fetch_active_sku_pricing_record(sku: str, tenant_id: str | None = None):
    """Most recent active workflow record for a SKU (if any)."""
    sku = sku.strip()
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        return db_execute(
            conn,
            """
            SELECT id, sku, avg_cost_snapshot, markup_pct, taxes_pct, interest_pct,
                   markup_kind, taxes_kind, interest_kind,
                   price_before_taxes, price_with_taxes, target_price, created_at, is_active
            FROM sku_pricing_records
            WHERE tenant_id = %s AND sku = %s AND is_active = 1
            ORDER BY id DESC
            LIMIT 1;
            """,
            (tid, sku),
        ).fetchone()


def fetch_sku_master_rows(tenant_id: str | None = None):
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        return db_execute(
            conn,
            """
            SELECT sku, total_stock, avg_unit_cost, selling_price, structured_cost_total, updated_at
            FROM sku_master
            WHERE tenant_id = %s AND deleted_at IS NULL
            ORDER BY sku;
            """,
            (tid,),
        ).fetchall()


def fetch_product_triple_label_by_sku(tenant_id: str | None = None) -> dict[str, str]:
    """Map SKU → «Nome — cor da armação — cor da lente» (agregado em `products`)."""
    tid = effective_tenant_id_for_request(tenant_id)
    out: dict[str, str] = {}
    with use_connection(None) as conn:
        for row in db_execute(
            conn,
            """
            SELECT sku,
                   MIN(TRIM(name)) AS n,
                   MIN(TRIM(COALESCE(frame_color, ''))) AS fc,
                   MIN(TRIM(COALESCE(lens_color, ''))) AS lc
            FROM products
            WHERE tenant_id = %s AND deleted_at IS NULL
              AND sku IS NOT NULL
              AND TRIM(COALESCE(sku, '')) != ''
            GROUP BY sku;
            """,
            (tid,),
        ):
            sku_key = str(row["sku"]).strip()
            parts = [
                (row["n"] or "").strip() or "—",
                (row["fc"] or "").strip() or "—",
                (row["lc"] or "").strip() or "—",
            ]
            out[sku_key] = " — ".join(parts)
    return out


def fetch_recent_stock_cost_entries(limit: int = 50, tenant_id: str | None = None):
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        return db_execute(
            conn,
            """
            SELECT id, sku, product_id, quantity, unit_cost, total_entry_cost, stock_before, stock_after,
                   avg_cost_before, avg_cost_after, created_at
            FROM stock_cost_entries
            WHERE tenant_id = %s
            ORDER BY id DESC
            LIMIT %s;
            """,
            (tid, int(limit)),
        ).fetchall()


def get_persisted_structured_unit_cost(sku: str, tenant_id: str | None = None) -> float:
    """
    Planned unit cost per SKU from saved cost components (sku_master.structured_cost_total).
    Does not recompute from form state — user must save the cost breakdown first.
    """
    sku = sku.strip()
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        row = db_execute(
            conn,
            """
            SELECT COALESCE(structured_cost_total, 0) AS t, deleted_at
            FROM sku_master WHERE tenant_id = %s AND sku = %s;
            """,
            (tid, sku),
        ).fetchone()
        if row is None:
            raise ValueError("SKU não cadastrado no mestre de estoque.")
        if row["deleted_at"]:
            raise ValueError("SKU inativo (excluído logicamente).")
        return float(row["t"] or 0.0)


def fetch_product_batches_for_sku(sku: str, tenant_id: str | None = None) -> list:
    """Product rows (batches) for a given SKU — stock receipts apply to one batch."""
    sku = sku.strip()
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        return db_execute(
            conn,
            """
            SELECT id, name, sku, registered_date, product_enter_code, cost, price, pricing_locked, stock,
                   frame_color, lens_color, style, palette, gender
            FROM products
            WHERE tenant_id = %s AND TRIM(COALESCE(sku, '')) = %s
              AND deleted_at IS NULL
            ORDER BY id DESC;
            """,
            (tid, sku),
        ).fetchall()


def fetch_price_history_for_sku(sku: str, limit: int = 40, tenant_id: str | None = None):
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        return db_execute(
            conn,
            """
            SELECT id, sku, old_price, new_price, created_at, note
            FROM price_history
            WHERE tenant_id = %s AND sku = %s
            ORDER BY id DESC
            LIMIT %s;
            """,
            (tid, sku.strip(), int(limit)),
        ).fetchall()


def fetch_sku_cost_components_for_sku(sku: str, tenant_id: str | None = None) -> list:
    """Rows ordered like SKU_COST_COMPONENT_DEFINITIONS."""
    sku = sku.strip()
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        ensure_sku_cost_component_rows(conn, sku, tenant_id=tid)
        by_key = {}
        rows = db_execute(
            conn,
            """
            SELECT component_key, label, unit_price, quantity, line_total, updated_at
            FROM sku_cost_components
            WHERE tenant_id = %s AND sku = %s;
            """,
            (tid, sku),
        ).fetchall()
        for r in rows:
            by_key[r["component_key"]] = r
    out = []
    for key, label in SKU_COST_COMPONENT_DEFINITIONS:
        r = by_key.get(key)
        if r is None:
            out.append(
                {
                    "component_key": key,
                    "label": label,
                    "unit_price": 0.0,
                    "quantity": 0.0,
                    "line_total": 0.0,
                    "updated_at": None,
                }
            )
        else:
            out.append(
                {
                    "component_key": key,
                    "label": r["label"],
                    "unit_price": float(r["unit_price"] or 0),
                    "quantity": float(r["quantity"] or 0),
                    "line_total": float(r["line_total"] or 0),
                    "updated_at": r["updated_at"],
                }
            )
    return out


def fetch_products(tenant_id: str | None = None):
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            """
            SELECT id, name, sku, registered_date, product_enter_code, cost, price, pricing_locked, stock,
                   frame_color, lens_color, style, palette, gender
            FROM products
            WHERE tenant_id = %s AND deleted_at IS NULL
            ORDER BY id DESC
            """,
            (tid,),
        ).fetchall()
    return rows


def fetch_product_search_attribute_options(tenant_id: str | None = None) -> dict:
    """Valores distintos para filtros da busca por SKU."""
    tid = effective_tenant_id_for_request(tenant_id)
    out: dict = {
        "frame_color": [],
        "lens_color": [],
        "gender": [],
        "palette": [],
        "style": [],
    }
    with use_connection(None) as conn:
        for key, col in [
            ("frame_color", "frame_color"),
            ("lens_color", "lens_color"),
            ("gender", "gender"),
            ("palette", "palette"),
            ("style", "style"),
        ]:
            # Distinct + ORDER BY: Postgres exige que o ORDER BY encaixe no DISTINCT;
            # LOWER(v) com alias interno falha ("column v does not exist"). Subquery
            # externa permite ORDER BY case-insensitive sobre a coluna projectada.
            rows = db_execute(
                conn,
                f"""
                SELECT v FROM (
                    SELECT DISTINCT TRIM({col}) AS v
                    FROM products
                    WHERE tenant_id = %s
                      AND {col} IS NOT NULL AND TRIM({col}) != ''
                      AND deleted_at IS NULL
                ) AS attribute_opts
                ORDER BY {sql_order_ci("v")};
                """,
                (tid,),
            ).fetchall()
            out[key] = [str(r["v"]) for r in rows if r["v"] is not None and str(r["v"]).strip()]
    return out


def search_products_filtered(
    text_q: str,
    frame_color_filter: str,
    lens_color_filter: str,
    gender_filter: str,
    palette_filter: str,
    style_filter: str,
    sort_by: str,
    limit: int,
    offset: int,
    tenant_id: str | None = None,
) -> tuple[list, int]:
    """
    Partial match on SKU and product name; optional exact-match attribute filters.
    Returns (rows as list of column→value mappings, total matching count).
    """
    tid = effective_tenant_id_for_request(tenant_id)
    sanitized_search = _sku_search_sanitize_text(text_q)
    wheres = ["p.tenant_id = %s", "p.deleted_at IS NULL"]
    params: list = [tid]
    if sanitized_search:
        like_pattern = f"%{sanitized_search}%"
        wheres.append(
            "(LOWER(COALESCE(p.sku, '')) LIKE %s OR LOWER(COALESCE(p.name, '')) LIKE %s)"
        )
        params.extend([like_pattern, like_pattern])

    for val, pcol in [
        (frame_color_filter, "p.frame_color"),
        (lens_color_filter, "p.lens_color"),
        (gender_filter, "p.gender"),
        (palette_filter, "p.palette"),
        (style_filter, "p.style"),
    ]:
        if val and str(val).strip() and str(val) != FILTER_ANY:
            wheres.append(f"TRIM(COALESCE({pcol}, '')) = %s")
            params.append(str(val).strip())

    where_sql = " AND ".join(wheres)
    order_map = {
        "sku": f"{sql_order_ci('p.sku')} ASC",
        "name": f"{sql_order_ci('p.name')} ASC",
        "stock_desc": "p.stock DESC",
        "stock_asc": "p.stock ASC",
    }
    order_sql = order_map.get(sort_by, f"{sql_order_ci('p.sku')} ASC")

    base_from = """
        FROM products p
        LEFT JOIN sku_master sm ON sm.sku = p.sku AND sm.tenant_id = p.tenant_id
    """
    count_sql = f"SELECT COUNT(*) AS cnt {base_from} WHERE {where_sql}"
    data_sql = f"""
        SELECT p.id, p.sku, p.name, p.frame_color, p.lens_color, p.gender, p.palette, p.style,
               p.stock, p.created_at,
               COALESCE(sm.avg_unit_cost, p.cost, 0) AS avg_cost,
               COALESCE(sm.selling_price, p.price, 0) AS sell_price
        {base_from}
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT %s OFFSET %s
    """
    lim = max(1, min(int(limit), 500))
    off = max(0, int(offset))
    with use_connection(None) as conn:
        total = int(db_execute(conn, count_sql, params).fetchone()["cnt"])
        rows = db_execute(conn, data_sql, params + [lim, off]).fetchall()
    return rows, total


def fetch_product_by_id(product_id: int, tenant_id: str | None = None):
    """Single product row joined with sku_master for display."""
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        return db_execute(
            conn,
            """
            SELECT p.id, p.sku, p.name, p.frame_color, p.lens_color, p.gender, p.palette, p.style,
                   p.stock, p.registered_date, p.product_enter_code, p.created_at,
                   p.product_image_path,
                   COALESCE(sm.avg_unit_cost, p.cost, 0) AS avg_cost,
                   COALESCE(sm.selling_price, p.price, 0) AS sell_price
            FROM products p
            LEFT JOIN sku_master sm ON sm.sku = p.sku AND sm.tenant_id = p.tenant_id
                AND sm.deleted_at IS NULL
            WHERE p.tenant_id = %s AND p.id = %s AND p.deleted_at IS NULL;
            """,
            (tid, int(product_id)),
        ).fetchone()


def compute_dashboard(tenant_id: str | None = None):
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        revenue = db_execute(
            conn,
            "SELECT COALESCE(SUM(total), 0) AS revenue FROM sales WHERE tenant_id = %s;",
            (tid,),
        ).fetchone()["revenue"]
        sales_count = db_execute(
            conn,
            "SELECT COUNT(*) AS cnt FROM sales WHERE tenant_id = %s;",
            (tid,),
        ).fetchone()["cnt"]
        total_stock_units = float(
            db_execute(
                conn,
                "SELECT COALESCE(SUM(stock), 0) AS cnt FROM products WHERE tenant_id = %s;",
                (tid,),
            ).fetchone()["cnt"]
        )
        low_stock = db_execute(
            conn,
            """
            SELECT COUNT(*) AS cnt
            FROM products
            WHERE tenant_id = %s AND stock <= 5
            """,
            (tid,),
        ).fetchone()["cnt"]

    return {
        "revenue": float(revenue),
        "sales_count": int(sales_count),
        "total_stock_units": total_stock_units,
        "low_stock": int(low_stock),
    }


def compute_sales_financials(tenant_id: str | None = None):
    """
    Financial summary based strictly on recorded sales:
    - revenue: SUM(sales.total)
    - cost: SUM(sales.cogs_total) — COGS at sale time (SKU weighted-average cost × qty)
    - profit/loss: revenue - cost
    """
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        row = db_execute(
            conn,
            """
            SELECT
                COALESCE(SUM(s.total), 0) AS revenue,
                COALESCE(SUM(s.cogs_total), 0) AS cost
            FROM sales s
            WHERE s.tenant_id = %s;
            """,
            (tid,),
        ).fetchone()

    revenue = float(row["revenue"])
    cost = float(row["cost"])
    profit_loss = revenue - cost
    return revenue, cost, profit_loss


def fetch_revenue_timeseries(tenant_id: str | None = None):
    """Revenue aggregated by day (for the dashboard chart)."""
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            """
            SELECT
                substr(sold_at, 1, 10) AS day,
                SUM(total) AS revenue
            FROM sales
            WHERE tenant_id = %s
            GROUP BY day
            ORDER BY day;
            """,
            (tid,),
        ).fetchall()

    if not rows:
        return pd.DataFrame(columns=["day", "revenue"])

    df = pd.DataFrame([{"day": r["day"], "revenue": r["revenue"]} for r in rows])
    df["revenue"] = df["revenue"].astype(float)
    return df


# --- Painel executivo (filtros por período / SKU / cliente; sem alterar regras de negócio) ---


def _painel_sales_where(
    tenant_id: str,
    date_start: str,
    date_end: str,
    sku: Optional[str],
    customer_id: Optional[int],
    product_id: Optional[int] = None,
) -> tuple[str, list[Any]]:
    clauses = [
        "s.tenant_id = %s",
        "substr(s.sold_at, 1, 10) >= %s",
        "substr(s.sold_at, 1, 10) <= %s",
    ]
    params: list[Any] = [tenant_id, date_start, date_end]
    if sku is not None and str(sku).strip():
        clauses.append("TRIM(COALESCE(s.sku, '')) = %s")
        params.append(str(sku).strip())
    if customer_id is not None:
        clauses.append("s.customer_id = %s")
        params.append(int(customer_id))
    if product_id is not None:
        clauses.append("s.product_id = %s")
        params.append(int(product_id))
    return " AND ".join(clauses), params


def fetch_sales_date_bounds(tenant_id: str | None = None) -> tuple[Optional[str], Optional[str]]:
    """Limites min/max (YYYY-MM-DD) das vendas do inquilino."""
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        row = db_execute(
            conn,
            """
            SELECT
                MIN(substr(sold_at, 1, 10)) AS d0,
                MAX(substr(sold_at, 1, 10)) AS d1
            FROM sales
            WHERE tenant_id = %s;
            """,
            (tid,),
        ).fetchone()
    if not row or row["d0"] is None:
        return None, None
    return str(row["d0"]), str(row["d1"])


def fetch_dashboard_kpis_period(
    date_start: str,
    date_end: str,
    tenant_id: str | None = None,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    KPIs agregados no período [date_start, date_end] (strings YYYY-MM-DD),
    respeitando filtros opcionais de SKU, produto e cliente.
    """
    tid = effective_tenant_id_for_request(tenant_id)
    where, params = _painel_sales_where(
        tid, date_start, date_end, sku, customer_id, product_id
    )
    with use_connection(None) as conn:
        row = db_execute(
            conn,
            f"""
            SELECT
                COALESCE(SUM(s.total), 0) AS revenue,
                COALESCE(SUM(s.cogs_total), 0) AS cost,
                COALESCE(SUM(s.total - COALESCE(s.cogs_total, 0)), 0) AS profit,
                COUNT(*) AS sales_count,
                COUNT(DISTINCT s.customer_id) AS unique_customers
            FROM sales s
            WHERE {where};
            """,
            params,
        ).fetchone()
    revenue = float(row["revenue"])
    profit = float(row["profit"])
    sales_count = int(row["sales_count"])
    unique_cust = int(row["unique_customers"])
    ticket = (revenue / sales_count) if sales_count else 0.0
    margin = (profit / revenue * 100.0) if revenue > 0 else 0.0
    return {
        "revenue": revenue,
        "cost": float(row["cost"]),
        "profit": profit,
        "sales_count": sales_count,
        "unique_customers": unique_cust,
        "ticket_avg": ticket,
        "margin_pct": margin,
    }


def fetch_daily_revenue_profit(
    date_start: str,
    date_end: str,
    tenant_id: str | None = None,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> pd.DataFrame:
    tid = effective_tenant_id_for_request(tenant_id)
    where, params = _painel_sales_where(
        tid, date_start, date_end, sku, customer_id, product_id
    )
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            f"""
            SELECT
                substr(s.sold_at, 1, 10) AS day,
                COALESCE(SUM(s.total), 0) AS revenue,
                COALESCE(SUM(s.cogs_total), 0) AS cost,
                COALESCE(SUM(s.total - COALESCE(s.cogs_total, 0)), 0) AS profit
            FROM sales s
            WHERE {where}
            GROUP BY day
            ORDER BY day;
            """,
            params,
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["day", "revenue", "cost", "profit"])
    df = pd.DataFrame(
        [
            {
                "day": r["day"],
                "revenue": float(r["revenue"]),
                "cost": float(r["cost"]),
                "profit": float(r["profit"]),
            }
            for r in rows
        ]
    )
    return df


def fetch_top_skus_by_qty(
    date_start: str,
    date_end: str,
    tenant_id: str | None = None,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    limit: int = 10,
) -> pd.DataFrame:
    """Top SKUs por quantidade vendida no período."""
    tid = effective_tenant_id_for_request(tenant_id)
    where, params = _painel_sales_where(
        tid, date_start, date_end, sku, customer_id, product_id
    )
    lim = max(1, min(int(limit), 50))
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            f"""
            SELECT
                TRIM(s.sku) AS sku,
                COALESCE(SUM(s.total), 0) AS revenue,
                COALESCE(SUM(s.total - COALESCE(s.cogs_total, 0)), 0) AS profit,
                COALESCE(SUM(s.quantity), 0) AS qty
            FROM sales s
            WHERE {where}
              AND s.sku IS NOT NULL AND TRIM(s.sku) != ''
            GROUP BY TRIM(s.sku)
            ORDER BY qty DESC
            LIMIT %s;
            """,
            params + [lim],
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["sku", "revenue", "profit", "qty"])
    return pd.DataFrame(
        [
            {
                "sku": r["sku"],
                "revenue": float(r["revenue"]),
                "profit": float(r["profit"]),
                "qty": float(r["qty"]),
            }
            for r in rows
        ]
    )


def fetch_top_skus_by_metric(
    date_start: str,
    date_end: str,
    tenant_id: str | None = None,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    limit: int = 10,
) -> pd.DataFrame:
    tid = effective_tenant_id_for_request(tenant_id)
    where, params = _painel_sales_where(
        tid, date_start, date_end, sku, customer_id, product_id
    )
    lim = max(1, min(int(limit), 50))
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            f"""
            SELECT
                TRIM(s.sku) AS sku,
                COALESCE(SUM(s.total), 0) AS revenue,
                COALESCE(SUM(s.total - COALESCE(s.cogs_total, 0)), 0) AS profit,
                COALESCE(SUM(s.quantity), 0) AS qty
            FROM sales s
            WHERE {where}
              AND s.sku IS NOT NULL AND TRIM(s.sku) != ''
            GROUP BY TRIM(s.sku)
            ORDER BY revenue DESC
            LIMIT %s;
            """,
            params + [lim],
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["sku", "revenue", "profit", "qty"])
    return pd.DataFrame(
        [
            {
                "sku": r["sku"],
                "revenue": float(r["revenue"]),
                "profit": float(r["profit"]),
                "qty": float(r["qty"]),
            }
            for r in rows
        ]
    )


def fetch_top_product_names_by_revenue(
    date_start: str,
    date_end: str,
    tenant_id: str | None = None,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    limit: int = 10,
) -> pd.DataFrame:
    tid = effective_tenant_id_for_request(tenant_id)
    where, params = _painel_sales_where(
        tid, date_start, date_end, sku, customer_id, product_id
    )
    lim = max(1, min(int(limit), 50))
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            f"""
            SELECT
                p.name AS product_name,
                COALESCE(SUM(s.total), 0) AS revenue,
                COALESCE(SUM(s.total - COALESCE(s.cogs_total, 0)), 0) AS profit,
                COALESCE(SUM(s.quantity), 0) AS qty
            FROM sales s
            JOIN products p ON p.tenant_id = s.tenant_id AND p.id = s.product_id
            WHERE {where}
            GROUP BY p.name
            ORDER BY revenue DESC
            LIMIT %s;
            """,
            params + [lim],
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["product_name", "revenue", "profit", "qty"])
    return pd.DataFrame(
        [
            {
                "product_name": r["product_name"],
                "revenue": float(r["revenue"]),
                "profit": float(r["profit"]),
                "qty": float(r["qty"]),
            }
            for r in rows
        ]
    )


def fetch_payment_method_breakdown(
    date_start: str,
    date_end: str,
    tenant_id: str | None = None,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> pd.DataFrame:
    tid = effective_tenant_id_for_request(tenant_id)
    where, params = _painel_sales_where(
        tid, date_start, date_end, sku, customer_id, product_id
    )
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            f"""
            SELECT
                CASE
                    WHEN s.payment_method IS NULL OR TRIM(s.payment_method) = ''
                    THEN '(não informado)'
                    ELSE TRIM(s.payment_method)
                END AS payment_method,
                COALESCE(SUM(s.total), 0) AS revenue,
                COUNT(*) AS n_sales
            FROM sales s
            WHERE {where}
            GROUP BY payment_method
            ORDER BY revenue DESC;
            """,
            params,
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["payment_method", "revenue", "n_sales"])
    return pd.DataFrame(
        [
            {
                "payment_method": r["payment_method"],
                "revenue": float(r["revenue"]),
                "n_sales": int(r["n_sales"]),
            }
            for r in rows
        ]
    )


def fetch_top_customers_by_revenue(
    date_start: str,
    date_end: str,
    tenant_id: str | None = None,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    limit: int = 10,
) -> pd.DataFrame:
    tid = effective_tenant_id_for_request(tenant_id)
    where, params = _painel_sales_where(
        tid, date_start, date_end, sku, customer_id, product_id
    )
    lim = max(1, min(int(limit), 50))
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            f"""
            SELECT
                s.customer_id,
                COALESCE(SUM(s.total), 0) AS revenue,
                COUNT(*) AS n_orders
            FROM sales s
            WHERE {where}
              AND s.customer_id IS NOT NULL
            GROUP BY s.customer_id
            ORDER BY revenue DESC
            LIMIT %s;
            """,
            params + [lim],
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["customer_id", "revenue", "n_orders"])
    return pd.DataFrame(
        [
            {
                "customer_id": int(r["customer_id"]),
                "revenue": float(r["revenue"]),
                "n_orders": int(r["n_orders"]),
            }
            for r in rows
        ]
    )


def fetch_customer_order_buckets(
    date_start: str,
    date_end: str,
    tenant_id: str | None = None,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> pd.DataFrame:
    """Distribuição: quantos clientes fizeram N pedidos no período."""
    tid = effective_tenant_id_for_request(tenant_id)
    where, params = _painel_sales_where(
        tid, date_start, date_end, sku, customer_id, product_id
    )
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            f"""
            SELECT orders AS n_pedidos, COUNT(*) AS n_clientes
            FROM (
                SELECT s.customer_id, COUNT(*) AS orders
                FROM sales s
                WHERE {where}
                  AND s.customer_id IS NOT NULL
                GROUP BY s.customer_id
            ) t
            GROUP BY orders
            ORDER BY orders;
            """,
            params,
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["n_pedidos", "n_clientes"])
    return pd.DataFrame(
        [{"n_pedidos": int(r["n_pedidos"]), "n_clientes": int(r["n_clientes"])} for r in rows]
    )


def count_customers_total(tenant_id: str | None = None) -> int:
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        row = db_execute(
            conn,
            "SELECT COUNT(*) AS c FROM customers WHERE tenant_id = %s;",
            (tid,),
        ).fetchone()
    return int(row["c"] or 0)


def fetch_low_stock_products_dashboard(
    tenant_id: str | None = None,
    threshold: float = 5.0,
    limit: int = 40,
) -> pd.DataFrame:
    tid = effective_tenant_id_for_request(tenant_id)
    lim = max(1, min(int(limit), 200))
    thr = float(threshold)
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            """
            SELECT
                p.id,
                p.sku,
                p.name,
                COALESCE(sm.avg_unit_cost, p.cost, 0) AS unit_cost,
                COALESCE(sm.selling_price, p.price, 0) AS sell_price,
                p.stock
            FROM products p
            LEFT JOIN sku_master sm
                ON sm.tenant_id = p.tenant_id AND sm.sku = p.sku AND sm.deleted_at IS NULL
            WHERE p.tenant_id = %s
              AND p.deleted_at IS NULL
              AND COALESCE(p.stock, 0) <= %s
            ORDER BY p.stock ASC, p.id DESC
            LIMIT %s;
            """,
            (tid, thr, lim),
        ).fetchall()
    if not rows:
        return pd.DataFrame(
            columns=["id", "sku", "name", "unit_cost", "sell_price", "stock"]
        )
    return pd.DataFrame(
        [
            {
                "id": r["id"],
                "sku": r["sku"],
                "name": r["name"],
                "unit_cost": float(r["unit_cost"] or 0),
                "sell_price": float(r["sell_price"] or 0),
                "stock": float(r["stock"] or 0),
            }
            for r in rows
        ]
    )


def fetch_inventory_stock_summary(
    tenant_id: str | None = None, *, critical_threshold: float = 5.0
) -> dict[str, Any]:
    """Unidades totais e valor a CMP (custo médio no lote × stock).

    ``critical_threshold``: produtos com ``stock <=`` este valor entram em ``n_critical_skus``.
    O painel web usa 1.0; o default 5.0 mantém paridade com o Streamlit.
    """
    tid = effective_tenant_id_for_request(tenant_id)
    thr = float(critical_threshold)
    with use_connection(None) as conn:
        row = db_execute(
            conn,
            """
            SELECT
                COALESCE(SUM(p.stock), 0) AS units,
                COALESCE(SUM(p.stock * COALESCE(sm.avg_unit_cost, p.cost, 0)), 0) AS value_cmp
            FROM products p
            LEFT JOIN sku_master sm
                ON sm.tenant_id = p.tenant_id AND sm.sku = p.sku AND sm.deleted_at IS NULL
            WHERE p.tenant_id = %s AND p.deleted_at IS NULL;
            """,
            (tid,),
        ).fetchone()
        crit = db_execute(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM products
            WHERE tenant_id = %s AND deleted_at IS NULL AND COALESCE(stock, 0) <= %s;
            """,
            (tid, thr),
        ).fetchone()
    return {
        "total_units": float(row["units"] or 0),
        "value_cmp": float(row["value_cmp"] or 0),
        "n_critical_skus": int(crit["c"] or 0),
    }


def fetch_stock_distribution_top_skus(
    tenant_id: str | None = None,
    limit: int = 25,
) -> pd.DataFrame:
    tid = effective_tenant_id_for_request(tenant_id)
    lim = max(1, min(int(limit), 100))
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            """
            SELECT sku, total_stock
            FROM sku_master
            WHERE tenant_id = %s AND deleted_at IS NULL
              AND COALESCE(total_stock, 0) > 0
            ORDER BY total_stock DESC
            LIMIT %s;
            """,
            (tid, lim),
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["sku", "total_stock"])
    return pd.DataFrame(
        [{"sku": r["sku"], "total_stock": float(r["total_stock"] or 0)} for r in rows]
    )


def fetch_skus_no_recent_sales(
    tenant_id: str | None = None,
    since_day: str = "2000-01-01",
    min_stock: float = 0.01,
    limit: int = 30,
    until_day: Optional[str] = None,
) -> pd.DataFrame:
    """
    SKUs com estoque no mestre mas sem venda em janela de datas.

    - Se ``until_day`` é informado (YYYY-MM-DD): sem venda com
      ``sold_at`` entre ``since_day`` e ``until_day`` (inclusive).
    - Caso contrário: sem venda com ``sold_at`` em ou após ``since_day``.
    """
    tid = effective_tenant_id_for_request(tenant_id)
    lim = max(1, min(int(limit), 100))
    with use_connection(None) as conn:
        if until_day:
            rows = db_execute(
                conn,
                """
                SELECT sm.sku, sm.total_stock
                FROM sku_master sm
                WHERE sm.tenant_id = %s
                  AND sm.deleted_at IS NULL
                  AND COALESCE(sm.total_stock, 0) >= %s
                  AND NOT EXISTS (
                      SELECT 1 FROM sales s
                      WHERE s.tenant_id = sm.tenant_id
                        AND TRIM(COALESCE(s.sku, '')) = TRIM(sm.sku)
                        AND substr(s.sold_at, 1, 10) >= %s
                        AND substr(s.sold_at, 1, 10) <= %s
                  )
                ORDER BY sm.total_stock DESC
                LIMIT %s;
                """,
                (tid, float(min_stock), since_day, until_day, lim),
            ).fetchall()
        else:
            rows = db_execute(
                conn,
                """
                SELECT sm.sku, sm.total_stock
                FROM sku_master sm
                WHERE sm.tenant_id = %s
                  AND sm.deleted_at IS NULL
                  AND COALESCE(sm.total_stock, 0) >= %s
                  AND NOT EXISTS (
                      SELECT 1 FROM sales s
                      WHERE s.tenant_id = sm.tenant_id
                        AND TRIM(COALESCE(s.sku, '')) = TRIM(sm.sku)
                        AND substr(s.sold_at, 1, 10) >= %s
                  )
                ORDER BY sm.total_stock DESC
                LIMIT %s;
                """,
                (tid, float(min_stock), since_day, lim),
            ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["sku", "total_stock"])
    return pd.DataFrame(
        [{"sku": r["sku"], "total_stock": float(r["total_stock"] or 0)} for r in rows]
    )


def fetch_ranked_skus_profit(
    date_start: str,
    date_end: str,
    tenant_id: str | None = None,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    limit: int = 10,
) -> pd.DataFrame:
    """Top SKUs por lucro (no período)."""
    tid = effective_tenant_id_for_request(tenant_id)
    where, params = _painel_sales_where(
        tid, date_start, date_end, sku, customer_id, product_id
    )
    lim = max(1, min(int(limit), 50))
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            f"""
            SELECT
                TRIM(s.sku) AS sku,
                COALESCE(SUM(s.total), 0) AS revenue,
                COALESCE(SUM(s.total - COALESCE(s.cogs_total, 0)), 0) AS profit,
                COALESCE(SUM(s.quantity), 0) AS qty
            FROM sales s
            WHERE {where}
              AND s.sku IS NOT NULL AND TRIM(s.sku) != ''
            GROUP BY TRIM(s.sku)
            ORDER BY profit DESC
            LIMIT %s;
            """,
            params + [lim],
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["sku", "revenue", "profit", "qty"])
    return pd.DataFrame(
        [
            {
                "sku": r["sku"],
                "revenue": float(r["revenue"]),
                "profit": float(r["profit"]),
                "qty": float(r["qty"]),
            }
            for r in rows
        ]
    )


def fetch_skus_lowest_qty_sales(
    date_start: str,
    date_end: str,
    tenant_id: str | None = None,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    limit: int = 5,
) -> pd.DataFrame:
    """SKUs com venda no período, ordenados pelo menor volume (qtd)."""
    tid = effective_tenant_id_for_request(tenant_id)
    where, params = _painel_sales_where(
        tid, date_start, date_end, sku, customer_id, product_id
    )
    lim = max(1, min(int(limit), 50))
    with use_connection(None) as conn:
        rows = db_execute(
            conn,
            f"""
            SELECT
                TRIM(s.sku) AS sku,
                COALESCE(SUM(s.total), 0) AS revenue,
                COALESCE(SUM(s.total - COALESCE(s.cogs_total, 0)), 0) AS profit,
                COALESCE(SUM(s.quantity), 0) AS qty
            FROM sales s
            WHERE {where}
              AND s.sku IS NOT NULL AND TRIM(s.sku) != ''
            GROUP BY TRIM(s.sku)
            HAVING COALESCE(SUM(s.quantity), 0) > 0
            ORDER BY qty ASC
            LIMIT %s;
            """,
            params + [lim],
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["sku", "revenue", "profit", "qty"])
    return pd.DataFrame(
        [
            {
                "sku": r["sku"],
                "revenue": float(r["revenue"]),
                "profit": float(r["profit"]),
                "qty": float(r["qty"]),
            }
            for r in rows
        ]
    )


def count_customers_with_sales_since(
    since_day: str,
    tenant_id: str | None = None,
) -> int:
    """Clientes distintos com pelo menos uma venda desde ``since_day`` (YYYY-MM-DD)."""
    tid = effective_tenant_id_for_request(tenant_id)
    with use_connection(None) as conn:
        row = db_execute(
            conn,
            """
            SELECT COUNT(DISTINCT customer_id) AS c
            FROM sales
            WHERE tenant_id = %s
              AND customer_id IS NOT NULL
              AND substr(sold_at, 1, 10) >= %s;
            """,
            (tid, since_day),
        ).fetchone()
    return int(row["c"] or 0)


def fetch_product_sales_rankings(
    date_start: str,
    date_end: str,
    tenant_id: str | None = None,
    sku: Optional[str] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    limit: int = 15,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(mais vendidos por qty, mais lucrativos por profit) ao nível de nome de produto."""
    tid = effective_tenant_id_for_request(tenant_id)
    where, params = _painel_sales_where(
        tid, date_start, date_end, sku, customer_id, product_id
    )
    lim = max(1, min(int(limit), 50))
    with use_connection(None) as conn:
        by_qty = db_execute(
            conn,
            f"""
            SELECT
                p.name AS product_name,
                COALESCE(SUM(s.quantity), 0) AS qty,
                COALESCE(SUM(s.total), 0) AS revenue,
                COALESCE(SUM(s.total - COALESCE(s.cogs_total, 0)), 0) AS profit
            FROM sales s
            JOIN products p ON p.tenant_id = s.tenant_id AND p.id = s.product_id
            WHERE {where}
            GROUP BY p.name
            ORDER BY qty DESC
            LIMIT %s;
            """,
            params + [lim],
        ).fetchall()
        by_profit = db_execute(
            conn,
            f"""
            SELECT
                p.name AS product_name,
                COALESCE(SUM(s.quantity), 0) AS qty,
                COALESCE(SUM(s.total), 0) AS revenue,
                COALESCE(SUM(s.total - COALESCE(s.cogs_total, 0)), 0) AS profit
            FROM sales s
            JOIN products p ON p.tenant_id = s.tenant_id AND p.id = s.product_id
            WHERE {where}
            GROUP BY p.name
            ORDER BY profit DESC
            LIMIT %s;
            """,
            params + [lim],
        ).fetchall()

    def _to_df(rows, cols):
        if not rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(rows)

    df_qty = _to_df(
        [
            {
                "product_name": r["product_name"],
                "qty": float(r["qty"]),
                "revenue": float(r["revenue"]),
                "profit": float(r["profit"]),
            }
            for r in by_qty
        ],
        ["product_name", "qty", "revenue", "profit"],
    )
    df_prof = _to_df(
        [
            {
                "product_name": r["product_name"],
                "qty": float(r["qty"]),
                "revenue": float(r["revenue"]),
                "profit": float(r["profit"]),
            }
            for r in by_profit
        ],
        ["product_name", "qty", "revenue", "profit"],
    )
    return df_qty, df_prof
