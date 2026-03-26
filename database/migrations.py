"""Migrações e backfills chamados na inicialização do SQLite local."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from database.cost_components_repo import (
    ensure_sku_cost_component_rows,
    recompute_sku_structured_cost_total,
)
from database.sku_codec import (
    build_product_sku_body,
    format_sku_sequence_int,
    _next_sku_sequence,
)
from database.sku_master_repo import sync_sku_master_totals


def migrate_product_skus_to_generated(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, name, frame_color, lens_color, gender, palette, style, sku
        FROM products
        ORDER BY id;
        """
    ).fetchall()
    for row in rows:
        body = build_product_sku_body(
            str(row["name"] or ""),
            row["frame_color"] or "",
            row["lens_color"] or "",
            row["gender"] or "",
            row["palette"] or "",
            row["style"] or "",
        )
        old_sku = str(row["sku"] or "").strip()
        oparts = old_sku.split("-")
        if oparts and oparts[0].isdigit():
            new_sku = f"{oparts[0]}-{body}"
        else:
            n = _next_sku_sequence(conn)
            new_sku = f"{format_sku_sequence_int(n)}-{body}"
        conn.execute(
            "UPDATE products SET sku = ? WHERE id = ?;",
            (new_sku, int(row["id"])),
        )


def backfill_sales_cogs(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT s.id, s.quantity, p.cost
        FROM sales s
        JOIN products p ON p.id = s.product_id
        WHERE COALESCE(s.cogs_total, 0) = 0;
        """
    ).fetchall()
    for row in rows:
        q = int(row["quantity"])
        c = float(row["cost"] or 0.0)
        conn.execute(
            "UPDATE sales SET cogs_total = ? WHERE id = ?;",
            (float(q) * c, int(row["id"])),
        )


def backfill_sku_master_from_products(conn: sqlite3.Connection) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    skus = conn.execute(
        """
        SELECT DISTINCT sku FROM products
        WHERE sku IS NOT NULL AND TRIM(sku) != ''
          AND deleted_at IS NULL;
        """
    ).fetchall()
    for row in skus:
        sku = str(row["sku"]).strip()
        agg = conn.execute(
            """
            SELECT
                COALESCE(SUM(stock), 0) AS total_st,
                COALESCE(SUM(stock * COALESCE(cost, 0)), 0) AS cost_sum,
                COALESCE(SUM(stock * COALESCE(price, 0)), 0) AS price_sum
            FROM products
            WHERE sku = ? AND deleted_at IS NULL;
            """,
            (sku,),
        ).fetchone()
        total_st = float(agg["total_st"] or 0)
        cost_sum = float(agg["cost_sum"] or 0.0)
        price_sum = float(agg["price_sum"] or 0.0)
        avg_cost = (cost_sum / total_st) if total_st > 0 else 0.0
        sell_p = (price_sum / total_st) if total_st > 0 else 0.0
        conn.execute(
            """
            INSERT INTO sku_master (sku, total_stock, avg_unit_cost, selling_price, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(sku) DO UPDATE SET
                total_stock = excluded.total_stock,
                avg_unit_cost = excluded.avg_unit_cost,
                selling_price = CASE
                    WHEN excluded.selling_price > 0 THEN excluded.selling_price
                    ELSE sku_master.selling_price
                END,
                updated_at = excluded.updated_at;
            """,
            (sku, total_st, avg_cost, sell_p, now),
        )


def migrate_sku_cost_component_rows(conn: sqlite3.Connection) -> None:
    skus = conn.execute("SELECT sku FROM sku_master;").fetchall()
    for row in skus:
        sku = str(row["sku"]).strip()
        if not sku:
            continue
        ensure_sku_cost_component_rows(conn, sku)
        recompute_sku_structured_cost_total(conn, sku)


def migrate_inventory_decimal_v1(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_schema_migrations (
            id TEXT PRIMARY KEY
        );
        """
    )
    if conn.execute(
        "SELECT 1 FROM app_schema_migrations WHERE id = 'inventory_decimal_v1';"
    ).fetchone():
        return

    info = conn.execute("PRAGMA table_info(products);").fetchall()
    stock_col = next((r for r in info if r[1] == "stock"), None)
    need = False
    if stock_col is not None:
        t = (stock_col[2] or "").upper()
        if "INT" in t and "REAL" not in t and "FLOA" not in t:
            need = True

    if not need:
        conn.execute(
            "INSERT OR IGNORE INTO app_schema_migrations (id) VALUES ('inventory_decimal_v1');"
        )
        return

    conn.execute("PRAGMA foreign_keys = OFF;")

    sce_rows = conn.execute("SELECT * FROM stock_cost_entries;").fetchall()
    conn.execute("DROP TABLE IF EXISTS stock_cost_entries;")

    sm_rows = conn.execute("SELECT * FROM sku_master;").fetchall()
    conn.execute("DROP TABLE IF EXISTS sku_master;")

    conn.execute(
        """
        CREATE TABLE products_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sku TEXT,
            registered_date TEXT,
            product_enter_code TEXT,
            cost REAL NOT NULL,
            price REAL NOT NULL,
            pricing_locked INTEGER NOT NULL DEFAULT 0 CHECK(pricing_locked IN (0, 1)),
            stock REAL NOT NULL CHECK(stock >= 0),
            frame_color TEXT,
            lens_color TEXT,
            style TEXT,
            palette TEXT,
            gender TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO products_new (
            id, name, sku, registered_date, product_enter_code, cost, price, pricing_locked,
            stock, frame_color, lens_color, style, palette, gender
        )
        SELECT
            id, name, sku, registered_date, product_enter_code, cost, price, pricing_locked,
            CAST(stock AS REAL),
            color,
            '',
            style, palette, gender
        FROM products;
        """
    )
    conn.execute("DROP TABLE products;")
    conn.execute("ALTER TABLE products_new RENAME TO products;")
    conn.execute("DELETE FROM sqlite_sequence WHERE name = 'products';")
    mx_prod = conn.execute("SELECT MAX(id) AS m FROM products;").fetchone()
    if mx_prod and mx_prod["m"] is not None and int(mx_prod["m"]) > 0:
        conn.execute(
            "INSERT INTO sqlite_sequence (name, seq) VALUES ('products', ?);",
            (int(mx_prod["m"]),),
        )

    conn.execute(
        """
        CREATE TABLE sku_master (
            sku TEXT PRIMARY KEY,
            total_stock REAL NOT NULL DEFAULT 0,
            avg_unit_cost REAL NOT NULL DEFAULT 0,
            selling_price REAL NOT NULL DEFAULT 0,
            structured_cost_total REAL NOT NULL DEFAULT 0,
            updated_at TEXT
        );
        """
    )
    for r in sm_rows:
        sm_dict = dict(r)
        sct = float(sm_dict.get("structured_cost_total") or 0)
        conn.execute(
            """
            INSERT INTO sku_master (
                sku, total_stock, avg_unit_cost, selling_price, structured_cost_total, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                r["sku"],
                float(r["total_stock"] or 0),
                float(r["avg_unit_cost"] or 0),
                float(r["selling_price"] or 0),
                sct,
                r["updated_at"],
            ),
        )

    conn.execute(
        """
        CREATE TABLE stock_cost_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            product_id INTEGER,
            quantity REAL NOT NULL CHECK(quantity > 0),
            unit_cost REAL NOT NULL,
            total_entry_cost REAL NOT NULL,
            stock_before REAL NOT NULL,
            stock_after REAL NOT NULL,
            avg_cost_before REAL NOT NULL,
            avg_cost_after REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (id)
        );
        """
    )
    for r in sce_rows:
        sce_dict = dict(r)
        q = float(r["quantity"] or 0)
        uc = float(r["unit_cost"] or 0)
        te = q * uc
        if sce_dict.get("total_entry_cost") is not None:
            try:
                te = float(sce_dict["total_entry_cost"])
            except (TypeError, ValueError):
                te = round(q * uc, 2)
        conn.execute(
            """
            INSERT INTO stock_cost_entries (
                id, sku, product_id, quantity, unit_cost, total_entry_cost,
                stock_before, stock_after, avg_cost_before, avg_cost_after, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                int(r["id"]),
                r["sku"],
                r["product_id"],
                q,
                uc,
                round(float(te), 2),
                float(r["stock_before"] or 0),
                float(r["stock_after"] or 0),
                float(r["avg_cost_before"] or 0),
                float(r["avg_cost_after"] or 0),
                r["created_at"],
            ),
        )
    conn.execute("DELETE FROM sqlite_sequence WHERE name = 'stock_cost_entries';")
    mx_row = conn.execute("SELECT MAX(id) AS m FROM stock_cost_entries;").fetchone()
    mx = int(mx_row["m"]) if mx_row and mx_row["m"] is not None else None
    if mx is not None and mx > 0:
        conn.execute(
            "INSERT INTO sqlite_sequence (name, seq) VALUES ('stock_cost_entries', ?);",
            (mx,),
        )

    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(
        "INSERT OR IGNORE INTO app_schema_migrations (id) VALUES ('inventory_decimal_v1');"
    )

    skus = conn.execute(
        """
        SELECT DISTINCT sku FROM products
        WHERE sku IS NOT NULL AND TRIM(sku) != '';
        """
    ).fetchall()
    for row in skus:
        sync_sku_master_totals(conn, str(row["sku"]).strip())
