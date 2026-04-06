"""Produtos / preços / lotes — apenas persistência (padrão get/create/update).

``conn`` pode ser ``None`` para abrir ligação com :func:`~database.connection.get_db_conn`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from database.connection import DbConnection
from database.repositories.support import use_connection
from database.sku_master_repo import sync_sku_master_totals
from database.sql_compat import db_execute, run_insert_returning_id
from database.tenancy import effective_tenant_id_for_request

_STOCK_DEC_EPS = 1e-9

__all__ = [
    "get_sku_master_selling_price_row",
    "create_price_history_entry",
    "update_sku_master_selling_price",
    "update_products_price_by_sku",
    "get_sku_master_selling_and_avg_cost",
    "update_sku_pricing_records_deactivate",
    "create_sku_pricing_record_active",
    "update_selling_price_apply_target",
    "get_product_name_sku_by_id",
    "get_product_stock_name_sku_by_id",
    "get_other_product_with_sku",
    "update_product_attributes_and_sku",
    "get_sku_master_exists_row",
    "get_same_batch_product_row",
    "get_product_id_by_sku",
    "create_product_zero_stock",
    "update_product_image_path",
    "update_product_cost_price",
    "get_instock_locked_batch_count",
    "update_instock_batch_pricing_lock",
    "get_distinct_skus_for_enter_code",
    "update_products_reset_stock_by_enter_code",
    "update_products_clear_cost_by_enter_code",
    "decrement_product_stock_manual",
]


def get_sku_master_selling_price_row(
    conn: DbConnection | None,
    sku: str,
    tenant_id: str | None = None,
):
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return db_execute(
            c,
            "SELECT selling_price FROM sku_master WHERE tenant_id = ? AND sku = ?;",
            (tid, sku),
        ).fetchone()


def create_price_history_entry(
    conn: DbConnection | None,
    sku: str,
    old_price: float,
    new_price: float,
    created_at: str,
    note: str,
    tenant_id: str | None = None,
) -> None:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        db_execute(
            c,
            """
            INSERT INTO price_history (tenant_id, sku, old_price, new_price, created_at, note)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (tid, sku, old_price, new_price, created_at, note),
        )


def update_sku_master_selling_price(
    conn: DbConnection | None,
    selling_price: float,
    updated_at: str,
    sku: str,
    tenant_id: str | None = None,
) -> None:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        db_execute(
            c,
            """
            UPDATE sku_master SET selling_price = ?, updated_at = ?
            WHERE tenant_id = ? AND sku = ?;
            """,
            (selling_price, updated_at, tid, sku),
        )


def update_products_price_by_sku(
    conn: DbConnection | None,
    price: float,
    sku: str,
    tenant_id: str | None = None,
) -> None:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        db_execute(
            c,
            """
            UPDATE products SET price = ? WHERE tenant_id = ? AND sku = ?;
            """,
            (price, tid, sku),
        )


def get_sku_master_selling_and_avg_cost(
    conn: DbConnection | None,
    sku: str,
    tenant_id: str | None = None,
):
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return db_execute(
            c,
            "SELECT selling_price, avg_unit_cost FROM sku_master WHERE tenant_id = ? AND sku = ?;",
            (tid, sku),
        ).fetchone()


def update_sku_pricing_records_deactivate(
    conn: DbConnection | None,
    sku: str,
    tenant_id: str | None = None,
) -> None:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        db_execute(
            c,
            "UPDATE sku_pricing_records SET is_active = 0 WHERE tenant_id = ? AND sku = ?;",
            (tid, sku),
        )


def create_sku_pricing_record_active(
    conn: DbConnection | None,
    *,
    sku: str,
    avg_cost: float,
    markup_pct: float,
    taxes_pct: float,
    interest_pct: float,
    mk: int,
    tk: int,
    ik: int,
    pb: float,
    pwt: float,
    target: float,
    now: str,
    tenant_id: str | None = None,
) -> int:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return run_insert_returning_id(
            c,
            """
            INSERT INTO sku_pricing_records (
                tenant_id, sku, avg_cost_snapshot, markup_pct, taxes_pct, interest_pct,
                markup_kind, taxes_kind, interest_kind,
                price_before_taxes, price_with_taxes, target_price, created_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
            """,
            (
                tid,
                sku,
                avg_cost,
                markup_pct,
                taxes_pct,
                interest_pct,
                mk,
                tk,
                ik,
                pb,
                pwt,
                target,
                now,
            ),
        )


def update_selling_price_apply_target(
    conn: DbConnection | None,
    *,
    sku: str,
    target: float,
    old_sell: float,
    now: str,
    history_note: str,
    tenant_id: str | None = None,
) -> None:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        db_execute(
            c,
            """
            UPDATE sku_master SET selling_price = ?, updated_at = ?
            WHERE tenant_id = ? AND sku = ?;
            """,
            (target, now, tid, sku),
        )
        db_execute(
            c,
            """
            UPDATE products SET price = ? WHERE tenant_id = ? AND sku = ?;
            """,
            (target, tid, sku),
        )
        db_execute(
            c,
            """
            INSERT INTO price_history (tenant_id, sku, old_price, new_price, created_at, note)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (tid, sku, old_sell, target, now, history_note),
        )


def get_product_name_sku_by_id(
    conn: DbConnection | None,
    product_id: int,
    tenant_id: str | None = None,
):
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return db_execute(
            c,
            "SELECT name, sku FROM products WHERE tenant_id = ? AND id = ?;",
            (tid, int(product_id)),
        ).fetchone()


def get_product_stock_name_sku_by_id(
    conn: DbConnection | None,
    product_id: int,
    tenant_id: str | None = None,
):
    """``stock``, ``name``, ``sku`` do lote (sem filtro ``deleted_at`` — paridade com UI de vendas)."""
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return db_execute(
            c,
            """
            SELECT stock, name, sku FROM products
            WHERE tenant_id = ? AND id = ?;
            """,
            (tid, int(product_id)),
        ).fetchone()


def get_other_product_with_sku(
    conn: DbConnection | None,
    new_sku: str,
    exclude_product_id: int,
    tenant_id: str | None = None,
):
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return db_execute(
            c,
            """
            SELECT id FROM products
            WHERE tenant_id = ? AND sku = ? AND id != ?;
            """,
            (tid, new_sku, int(exclude_product_id)),
        ).fetchone()


def update_product_attributes_and_sku(
    conn: DbConnection | None,
    *,
    frame_color: str,
    lens_color: str,
    style: str,
    palette: str,
    gender: str,
    new_sku: str,
    product_id: int,
    tenant_id: str | None = None,
) -> None:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        db_execute(
            c,
            """
            UPDATE products
            SET frame_color = ?, lens_color = ?, style = ?, palette = ?, gender = ?, sku = ?
            WHERE tenant_id = ? AND id = ?;
            """,
            (
                frame_color,
                lens_color,
                style,
                palette,
                gender,
                new_sku,
                tid,
                int(product_id),
            ),
        )


def get_sku_master_exists_row(
    conn: DbConnection | None,
    sku: str,
    tenant_id: str | None = None,
):
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return db_execute(
            c,
            "SELECT 1 FROM sku_master WHERE tenant_id = ? AND sku = ?;",
            (tid, sku),
        ).fetchone()


def get_same_batch_product_row(
    conn: DbConnection | None,
    name: str,
    registered_date_text: str,
    frame_color: str,
    lens_color: str,
    style: str,
    palette: str,
    gender: str,
    tenant_id: str | None = None,
):
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return db_execute(
            c,
            """
            SELECT id
            FROM products
            WHERE tenant_id = ? AND name = ? AND registered_date = ?
              AND COALESCE(frame_color, '') = ?
              AND COALESCE(lens_color, '') = ?
              AND COALESCE(style, '') = ?
              AND COALESCE(palette, '') = ?
              AND COALESCE(gender, '') = ?;
            """,
            (
                tid,
                name,
                registered_date_text,
                frame_color,
                lens_color,
                style,
                palette,
                gender,
            ),
        ).fetchone()


def get_product_id_by_sku(
    conn: DbConnection | None,
    sku: str,
    tenant_id: str | None = None,
):
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return db_execute(
            c,
            "SELECT id FROM products WHERE tenant_id = ? AND sku = ?;",
            (tid, sku),
        ).fetchone()


def create_product_zero_stock(
    conn: DbConnection | None,
    *,
    name: str,
    sku: str,
    registered_date_text: str,
    product_enter_code: str,
    frame_color: str,
    lens_color: str,
    style: str,
    palette: str,
    gender: str,
    created_at: str,
    tenant_id: str | None = None,
) -> int:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return run_insert_returning_id(
            c,
            """
            INSERT INTO products (
                tenant_id, name, sku, registered_date, product_enter_code, cost, price, stock,
                frame_color, lens_color, style, palette, gender, created_at
            )
            VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?, ?, ?);
            """,
            (
                tid,
                name,
                sku,
                registered_date_text,
                product_enter_code,
                frame_color,
                lens_color,
                style,
                palette,
                gender,
                created_at,
            ),
        )


def update_product_image_path(
    conn: DbConnection | None,
    relative_path: str,
    product_id: int,
    tenant_id: str | None = None,
) -> None:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        db_execute(
            c,
            """
            UPDATE products SET product_image_path = ? WHERE tenant_id = ? AND id = ?;
            """,
            (relative_path, tid, product_id),
        )


def update_product_cost_price(
    conn: DbConnection | None,
    cost: float,
    price: float,
    product_id: int,
    tenant_id: str | None = None,
) -> None:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        db_execute(
            c,
            """
            UPDATE products
            SET cost = ?, price = ?
            WHERE tenant_id = ? AND id = ?;
            """,
            (cost, price, tid, product_id),
        )


def get_instock_locked_batch_count(
    conn: DbConnection | None,
    product_name: str,
    sku: str,
    registered_date_text: str,
    tenant_id: str | None = None,
) -> int:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        locked = db_execute(
            c,
            """
            SELECT COUNT(*) AS cnt
            FROM products
            WHERE tenant_id = ?
              AND name = ?
              AND sku = ?
              AND registered_date = ?
              AND stock > 0
              AND pricing_locked = 1;
            """,
            (tid, product_name, sku, registered_date_text),
        ).fetchone()["cnt"]
        return int(locked)


def update_instock_batch_pricing_lock(
    conn: DbConnection | None,
    cost: float,
    price: float,
    product_name: str,
    sku: str,
    registered_date_text: str,
    tenant_id: str | None = None,
) -> int:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        cur = db_execute(
            c,
            """
            UPDATE products
            SET cost = ?,
                price = ?,
                pricing_locked = 1
            WHERE tenant_id = ?
              AND name = ?
              AND sku = ?
              AND registered_date = ?
              AND stock > 0;
            """,
            (cost, price, tid, product_name, sku, registered_date_text),
        )
        return int(cur.rowcount or 0)


def get_distinct_skus_for_enter_code(
    conn: DbConnection | None,
    product_enter_code: str,
    tenant_id: str | None = None,
) -> list[Mapping[str, Any]]:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        return db_execute(
            c,
            """
            SELECT DISTINCT sku FROM products
            WHERE tenant_id = ? AND product_enter_code = ? AND sku IS NOT NULL AND TRIM(sku) != '';
            """,
            (tid, product_enter_code),
        ).fetchall()


def update_products_reset_stock_by_enter_code(
    conn: DbConnection | None,
    product_enter_code: str,
    tenant_id: str | None = None,
) -> int:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        cur = db_execute(
            c,
            """
            UPDATE products
            SET stock = 0,
                cost = 0,
                price = 0,
                pricing_locked = 0
            WHERE tenant_id = ? AND product_enter_code = ?;
            """,
            (tid, product_enter_code),
        )
        return int(cur.rowcount or 0)


def update_products_clear_cost_by_enter_code(
    conn: DbConnection | None,
    product_enter_code: str,
    tenant_id: str | None = None,
) -> int:
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        cur = db_execute(
            c,
            """
            UPDATE products
            SET cost = 0,
                price = 0,
                pricing_locked = 0
            WHERE tenant_id = ? AND product_enter_code = ?;
            """,
            (tid, product_enter_code),
        )
        return int(cur.rowcount or 0)


def decrement_product_stock_manual(
    conn: DbConnection | None,
    product_id: int,
    quantity: float,
    tenant_id: str | None = None,
) -> float:
    """Reduz apenas ``products.stock`` do lote; mantém custo e preço. Actualiza ``sku_master``."""
    q = float(quantity)
    if q <= 0:
        raise ValueError("A quantidade de baixa deve ser maior que zero.")
    with use_connection(conn) as c:
        tid = effective_tenant_id_for_request(tenant_id)
        row = db_execute(
            c,
            """
            SELECT stock, sku, deleted_at FROM products
            WHERE tenant_id = ? AND id = ?;
            """,
            (tid, int(product_id)),
        ).fetchone()
        if not row:
            raise ValueError("Produto/lote não encontrado.")
        if row["deleted_at"]:
            raise ValueError("Este lote está inativo; não é possível dar baixa.")
        stock = float(row["stock"] or 0)
        sku = (row["sku"] or "").strip()
        if stock + _STOCK_DEC_EPS < q:
            raise ValueError(
                f"Stock insuficiente (disponível: {stock:g}; solicitado: {q:g})."
            )
        cur = db_execute(
            c,
            "UPDATE products SET stock = stock - ? WHERE tenant_id = ? AND id = ?;",
            (q, tid, int(product_id)),
        )
        if int(cur.rowcount or 0) != 1:
            raise ValueError("Falha ao atualizar o stock.")
        sync_sku_master_totals(c, sku, tenant_id=tid)
        new = db_execute(
            c,
            "SELECT stock FROM products WHERE tenant_id = ? AND id = ?;",
            (tid, int(product_id)),
        ).fetchone()
        return float(new["stock"] if new else 0.0)


# --- Compatibilidade (nomes legados) ---
fetch_sku_master_selling_price_row = get_sku_master_selling_price_row
insert_price_history_entry = create_price_history_entry
update_sku_master_selling_price_updated_at = update_sku_master_selling_price
update_products_price_where_sku = update_products_price_by_sku
fetch_sku_master_selling_and_avg_cost = get_sku_master_selling_and_avg_cost
deactivate_sku_pricing_records = update_sku_pricing_records_deactivate
insert_sku_pricing_record_active = create_sku_pricing_record_active
apply_target_selling_price_to_master_products_history = update_selling_price_apply_target
fetch_product_name_sku_by_id = get_product_name_sku_by_id
fetch_other_product_with_sku = get_other_product_with_sku
sku_master_exists = get_sku_master_exists_row
fetch_same_batch_product_row = get_same_batch_product_row
fetch_product_id_by_sku = get_product_id_by_sku
insert_product_zero_stock_row = create_product_zero_stock
update_product_image_path_by_id = update_product_image_path
update_product_cost_price_by_id = update_product_cost_price
count_instock_locked_batch_rows = get_instock_locked_batch_count
fetch_distinct_skus_for_enter_code = get_distinct_skus_for_enter_code
reset_stock_cost_price_unlock_by_enter_code = update_products_reset_stock_by_enter_code
clear_cost_price_unlock_by_enter_code = update_products_clear_cost_by_enter_code

__all__ += [
    "fetch_sku_master_selling_price_row",
    "insert_price_history_entry",
    "update_sku_master_selling_price_updated_at",
    "update_products_price_where_sku",
    "fetch_sku_master_selling_and_avg_cost",
    "deactivate_sku_pricing_records",
    "insert_sku_pricing_record_active",
    "apply_target_selling_price_to_master_products_history",
    "fetch_product_name_sku_by_id",
    "fetch_other_product_with_sku",
    "sku_master_exists",
    "fetch_same_batch_product_row",
    "fetch_product_id_by_sku",
    "insert_product_zero_stock_row",
    "update_product_image_path_by_id",
    "update_product_cost_price_by_id",
    "count_instock_locked_batch_rows",
    "update_instock_batch_pricing_lock",
    "fetch_distinct_skus_for_enter_code",
    "reset_stock_cost_price_unlock_by_enter_code",
    "clear_cost_price_unlock_by_enter_code",
]
