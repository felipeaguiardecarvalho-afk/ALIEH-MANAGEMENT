"""Read-only inventory lot listing for api-prototype (in-stock product rows)."""

from __future__ import annotations

from typing import Any

from database.repositories.support import use_connection
from database.sql_compat import db_execute, sql_order_ci
from database.tenancy import effective_tenant_id_for_request


def _sort_clause(sort: str) -> str:
    s = (sort or "name").strip().lower()
    if s == "sku":
        return f"{sql_order_ci('p.sku')} ASC, p.id ASC"
    # Streamlit: int(stock_qty) para ordenação por stock.
    if s == "stock_desc":
        return (
            "CAST(COALESCE(p.stock, 0) AS INTEGER) DESC, "
            f"{sql_order_ci('p.name')} ASC"
        )
    if s == "stock_asc":
        return (
            "CAST(COALESCE(p.stock, 0) AS INTEGER) ASC, "
            f"{sql_order_ci('p.name')} ASC"
        )
    # Paridade Streamlit: str(registered_date or "") na chave de ordenação.
    _reg_text = "COALESCE(CAST(p.registered_date AS TEXT), '')"
    return (
        f"{sql_order_ci('p.name')} ASC, "
        f"{_reg_text} ASC, p.id ASC"
    )


def _split_csv_str(s: str | None) -> list[str]:
    if not s or not str(s).strip():
        return []
    return [x.strip() for x in str(s).split(",") if x.strip()]


def _split_csv_float(s: str | None) -> list[float]:
    out: list[float] = []
    for x in _split_csv_str(s):
        try:
            out.append(round(float(x.replace(",", ".")), 4))
        except ValueError:
            continue
    return out


def _append_in_text(
    col_sql: str, values: list[str], wheres: list[str], params: list[Any]
) -> None:
    if not values:
        return
    ph = ",".join(["%s"] * len(values))
    wheres.append(f"TRIM(COALESCE({col_sql}, '')) IN ({ph})")
    params.extend(values)


def _append_in_float(expr_sql: str, values: list[float], wheres: list[str], params: list[Any]) -> None:
    if not values:
        return
    ph = ",".join(["%s"] * len(values))
    wheres.append(f"ROUND(({expr_sql})::numeric, 4) IN ({ph})")
    params.extend(values)


def _split_csv_stock_int(s: str | None) -> list[int]:
    """Valores de filtro de stock como int(stock) em Python (truncagem para zero)."""
    out: list[int] = []
    for x in _split_csv_str(s):
        try:
            out.append(int(float(x.replace(",", "."))))
        except ValueError:
            continue
    return out


def _append_in_int_stock(expr_sql: str, values: list[int], wheres: list[str], params: list[Any]) -> None:
    if not values:
        return
    ph = ",".join(["%s"] * len(values))
    wheres.append(f"({expr_sql}) IN ({ph})")
    params.extend(values)


def _base_where(
    *,
    tenant_id: str | None,
    names: list[str] | None = None,
    skus: list[str] | None = None,
    frame_colors: list[str] | None = None,
    lens_colors: list[str] | None = None,
    genders: list[str] | None = None,
    styles: list[str] | None = None,
    palettes: list[str] | None = None,
    costs: list[float] | None = None,
    prices: list[float] | None = None,
    markups: list[float] | None = None,
    stocks: list[int] | None = None,
    legacy_sku: str = "",
    legacy_frame_color: str = "",
    legacy_lens_color: str = "",
    legacy_gender: str = "",
    legacy_style: str = "",
    legacy_palette: str = "",
) -> tuple[str, list[Any]]:
    tid = effective_tenant_id_for_request(tenant_id)
    wheres = [
        "p.tenant_id = %s",
        "p.deleted_at IS NULL",
        "COALESCE(p.stock, 0) > 0",
    ]
    params: list[Any] = [tid]

    skus_f = list(skus or [])
    if not skus_f and (legacy_sku or "").strip():
        skus_f = [legacy_sku.strip()]
    _append_in_text("p.sku", skus_f, wheres, params)

    fc = list(frame_colors or [])
    if not fc and (legacy_frame_color or "").strip():
        fc = [legacy_frame_color.strip()]
    _append_in_text("p.frame_color", fc, wheres, params)

    lc = list(lens_colors or [])
    if not lc and (legacy_lens_color or "").strip():
        lc = [legacy_lens_color.strip()]
    _append_in_text("p.lens_color", lc, wheres, params)

    ge = list(genders or [])
    if not ge and (legacy_gender or "").strip():
        ge = [legacy_gender.strip()]
    _append_in_text("p.gender", ge, wheres, params)

    st = list(styles or [])
    if not st and (legacy_style or "").strip():
        st = [legacy_style.strip()]
    _append_in_text("p.style", st, wheres, params)

    pa = list(palettes or [])
    if not pa and (legacy_palette or "").strip():
        pa = [legacy_palette.strip()]
    _append_in_text("p.palette", pa, wheres, params)

    _append_in_text("p.name", list(names or []), wheres, params)

    _append_in_float("COALESCE(p.cost, 0)", list(costs or []), wheres, params)
    _append_in_float("COALESCE(p.price, 0)", list(prices or []), wheres, params)
    _append_in_float(
        "(COALESCE(p.price, 0) - COALESCE(p.cost, 0))",
        list(markups or []),
        wheres,
        params,
    )
    _stock_int_expr = "CAST(COALESCE(p.stock, 0) AS INTEGER)"
    _append_in_int_stock(_stock_int_expr, list(stocks or []), wheres, params)

    return " AND ".join(wheres), params


def search_inventory_lots(
    *,
    tenant_id: str | None,
    names_csv: str = "",
    skus_csv: str = "",
    frame_colors_csv: str = "",
    lens_colors_csv: str = "",
    genders_csv: str = "",
    styles_csv: str = "",
    palettes_csv: str = "",
    costs_csv: str = "",
    prices_csv: str = "",
    markups_csv: str = "",
    stocks_csv: str = "",
    sku: str = "",
    frame_color: str = "",
    lens_color: str = "",
    gender: str = "",
    style: str = "",
    palette: str = "",
    sort: str = "name",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list, int, dict[str, float]]:
    where_sql, params = _base_where(
        tenant_id=tenant_id,
        names=_split_csv_str(names_csv),
        skus=_split_csv_str(skus_csv),
        frame_colors=_split_csv_str(frame_colors_csv),
        lens_colors=_split_csv_str(lens_colors_csv),
        genders=_split_csv_str(genders_csv),
        styles=_split_csv_str(styles_csv),
        palettes=_split_csv_str(palettes_csv),
        costs=_split_csv_float(costs_csv),
        prices=_split_csv_float(prices_csv),
        markups=_split_csv_float(markups_csv),
        stocks=_split_csv_stock_int(stocks_csv),
        legacy_sku=sku,
        legacy_frame_color=frame_color,
        legacy_lens_color=lens_color,
        legacy_gender=gender,
        legacy_style=style,
        legacy_palette=palette,
    )
    order_sql = _sort_clause(sort)
    lim = max(1, min(int(limit), 50_000))
    off = max(0, int(offset))

    base = f"""
        FROM products p
        WHERE {where_sql}
    """
    count_sql = "SELECT COUNT(*) AS cnt " + base
    data_sql = f"""
        SELECT
            p.id AS product_id,
            p.sku,
            p.name,
            p.stock,
            p.product_enter_code,
            p.registered_date,
            p.frame_color,
            p.lens_color,
            p.style,
            p.palette,
            p.gender,
            COALESCE(p.cost, 0) AS cost,
            COALESCE(p.price, 0) AS price,
            (COALESCE(p.price, 0) - COALESCE(p.cost, 0)) AS markup
        {base}
        ORDER BY {order_sql}
        LIMIT %s OFFSET %s
    """
    # Paridade com Streamlit: totais usam int(stock) por linha antes de multiplicar.
    _stock_int = "CAST(COALESCE(p.stock, 0) AS INTEGER)"
    totals_sql = f"""
        SELECT
            COALESCE(SUM({_stock_int}), 0) AS total_stock,
            COALESCE(SUM({_stock_int} * COALESCE(p.cost, 0)), 0) AS total_cost_value,
            COALESCE(SUM({_stock_int} * COALESCE(p.price, 0)), 0) AS total_revenue_value,
            COALESCE(SUM({_stock_int} * (COALESCE(p.price, 0) - COALESCE(p.cost, 0))), 0) AS total_margin_value
        {base}
    """

    with use_connection(None) as conn:
        total = int(db_execute(conn, count_sql, params).fetchone()["cnt"])
        rows = db_execute(conn, data_sql, params + [lim, off]).fetchall()
        tr = db_execute(conn, totals_sql, params).fetchone()
    totals = {
        "total_stock": float(tr["total_stock"] or 0),
        "total_cost_value": float(tr["total_cost_value"] or 0),
        "total_revenue_value": float(tr["total_revenue_value"] or 0),
        "total_margin_value": float(tr["total_margin_value"] or 0),
    }
    return rows, total, totals


def fetch_inventory_lot_filter_options(*, tenant_id: str | None = None) -> dict:
    """Distinct values among in-stock lots (stock > 0) for multiselect filters."""
    tid = effective_tenant_id_for_request(tenant_id)
    out: dict = {
        "names": [],
        "skus": [],
        "frame_color": [],
        "lens_color": [],
        "gender": [],
        "palette": [],
        "style": [],
        "costs": [],
        "prices": [],
        "markups": [],
        "stocks": [],
    }
    with use_connection(None) as conn:
        for key, sql_expr in [
            ("names", "TRIM(p.name)"),
            ("skus", "TRIM(p.sku)"),
            ("frame_color", "p.frame_color"),
            ("lens_color", "p.lens_color"),
            ("gender", "p.gender"),
            ("palette", "p.palette"),
            ("style", "p.style"),
        ]:
            rows = db_execute(
                conn,
                f"""
                SELECT v FROM (
                    SELECT DISTINCT TRIM({sql_expr}) AS v
                    FROM products p
                    WHERE p.tenant_id = %s AND p.deleted_at IS NULL
                      AND COALESCE(p.stock, 0) > 0
                      AND {sql_expr} IS NOT NULL AND TRIM({sql_expr}) != ''
                ) t
                ORDER BY {sql_order_ci('v')};
                """,
                (tid,),
            ).fetchall()
            out[key] = [str(r["v"]) for r in rows if r.get("v")]

        for key, expr in [
            ("costs", "ROUND(COALESCE(p.cost, 0)::numeric, 2)"),
            ("prices", "ROUND(COALESCE(p.price, 0)::numeric, 2)"),
            ("markups", "ROUND((COALESCE(p.price, 0) - COALESCE(p.cost, 0))::numeric, 2)"),
            ("stocks", "CAST(COALESCE(p.stock, 0) AS INTEGER)"),
        ]:
            rows = db_execute(
                conn,
                f"""
                SELECT v FROM (
                    SELECT DISTINCT {expr} AS v
                    FROM products p
                    WHERE p.tenant_id = %s AND p.deleted_at IS NULL
                      AND COALESCE(p.stock, 0) > 0
                ) t
                ORDER BY v;
                """,
                (tid,),
            ).fetchall()
            out[key] = [str(int(r["v"])) for r in rows if r.get("v") is not None]
    return out
