"""
Criação e migração do schema SQLite local (`business.db`).

Chamado no arranque do Streamlit (`main()` do app) para ambiente local / go-live.
"""

from __future__ import annotations

import re
from datetime import datetime

from database.connection import get_conn
from database.customer_sync import sync_customer_sequence_counter_from_customers
from database.migrations import (
    backfill_sales_cogs,
    backfill_sku_master_from_products,
    migrate_inventory_decimal_v1,
    migrate_product_skus_to_generated,
    migrate_sku_cost_component_rows,
)
from database.product_codes import make_product_enter_code
from database.sale_codes import format_sale_code, sync_sale_sequence_counter_from_sales
from database.sku_codec import sync_sku_sequence_counter_from_skus


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity >= 1),
                total REAL NOT NULL,
                sold_at TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products (id)
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sku_master (
                sku TEXT PRIMARY KEY,
                total_stock REAL NOT NULL DEFAULT 0,
                avg_unit_cost REAL NOT NULL DEFAULT 0,
                selling_price REAL NOT NULL DEFAULT 0,
                updated_at TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_cost_entries (
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                old_price REAL,
                new_price REAL NOT NULL,
                created_at TEXT NOT NULL,
                note TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sku_sequence_counter (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_value INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO sku_sequence_counter (id, last_value) VALUES (1, 0);"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sku_pricing_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                avg_cost_snapshot REAL NOT NULL,
                markup_pct REAL NOT NULL CHECK(markup_pct >= 0),
                taxes_pct REAL NOT NULL CHECK(taxes_pct >= 0),
                interest_pct REAL NOT NULL CHECK(interest_pct >= 0),
                price_before_taxes REAL NOT NULL,
                price_with_taxes REAL NOT NULL,
                target_price REAL NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0 CHECK(is_active IN (0, 1))
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sku_pricing_records_sku ON sku_pricing_records(sku);"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sku_cost_components (
                sku TEXT NOT NULL,
                component_key TEXT NOT NULL,
                label TEXT NOT NULL,
                unit_price REAL NOT NULL DEFAULT 0 CHECK(unit_price >= 0),
                quantity REAL NOT NULL DEFAULT 0 CHECK(quantity >= 0),
                line_total REAL NOT NULL DEFAULT 0 CHECK(line_total >= 0),
                updated_at TEXT,
                PRIMARY KEY (sku, component_key)
            );
            """
        )

        sku_master_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(sku_master);").fetchall()
        }
        if "structured_cost_total" not in sku_master_cols:
            conn.execute(
                "ALTER TABLE sku_master ADD COLUMN structured_cost_total REAL NOT NULL DEFAULT 0;"
            )

        sce_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(stock_cost_entries);").fetchall()
        }
        if sce_cols and "total_entry_cost" not in sce_cols:
            conn.execute(
                "ALTER TABLE stock_cost_entries ADD COLUMN total_entry_cost REAL NOT NULL DEFAULT 0;"
            )
            conn.execute(
                """
                UPDATE stock_cost_entries
                SET total_entry_cost = ROUND(CAST(quantity AS REAL) * unit_cost, 2);
                """
            )

        migrate_inventory_decimal_v1(conn)

        sku_master_cols2 = {
            row["name"] for row in conn.execute("PRAGMA table_info(sku_master);").fetchall()
        }
        if "deleted_at" not in sku_master_cols2:
            conn.execute("ALTER TABLE sku_master ADD COLUMN deleted_at TEXT;")
        product_cols2 = {
            row["name"] for row in conn.execute("PRAGMA table_info(products);").fetchall()
        }
        if "deleted_at" not in product_cols2:
            conn.execute("ALTER TABLE products ADD COLUMN deleted_at TEXT;")
        product_cols3 = {
            row["name"] for row in conn.execute("PRAGMA table_info(products);").fetchall()
        }
        if "created_at" not in product_cols3:
            conn.execute("ALTER TABLE products ADD COLUMN created_at TEXT;")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sku_deletion_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                deleted_at TEXT NOT NULL,
                deleted_by TEXT,
                note TEXT
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_sequence_counter (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_value INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO customer_sequence_counter (id, last_value) VALUES (1, 0);"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                cpf TEXT,
                rg TEXT,
                phone TEXT,
                email TEXT,
                instagram TEXT,
                zip_code TEXT,
                street TEXT,
                number TEXT,
                neighborhood TEXT,
                city TEXT,
                state TEXT,
                country TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);")

        sales_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sales);").fetchall()}
        if "cogs_total" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN cogs_total REAL NOT NULL DEFAULT 0;")
        if "sku" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN sku TEXT;")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sale_sequence_counter (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_value INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO sale_sequence_counter (id, last_value) VALUES (1, 0);"
        )

        sales_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sales);").fetchall()}
        if "sale_code" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN sale_code TEXT;")
        if "customer_id" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN customer_id INTEGER;")
        if "unit_price" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN unit_price REAL;")
        if "discount_amount" not in sales_cols:
            conn.execute(
                "ALTER TABLE sales ADD COLUMN discount_amount REAL NOT NULL DEFAULT 0;"
            )
        if "base_amount" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN base_amount REAL;")

        max_n = 0
        for row in conn.execute(
            """
            SELECT sale_code FROM sales
            WHERE sale_code IS NOT NULL AND TRIM(sale_code) != '';
            """
        ):
            s = str(row["sale_code"] or "").strip().upper()
            m = re.match(r"^(\d{5})V$", s)
            if m:
                max_n = max(max_n, int(m.group(1)))
        next_n = max_n + 1
        for row in conn.execute(
            """
            SELECT id FROM sales
            WHERE sale_code IS NULL OR TRIM(sale_code) = ''
            ORDER BY id ASC;
            """
        ):
            conn.execute(
                "UPDATE sales SET sale_code = ? WHERE id = ?;",
                (format_sale_code(next_n), int(row["id"])),
            )
            next_n += 1
        sync_sale_sequence_counter_from_sales(conn)

        conn.execute(
            """
            UPDATE sales
            SET unit_price = CASE
                    WHEN COALESCE(quantity, 0) >= 1 THEN total * 1.0 / quantity
                    ELSE total
                END,
                discount_amount = 0,
                base_amount = total
            WHERE unit_price IS NULL;
            """
        )

        product_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(products);").fetchall()
        }
        if "sku" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN sku TEXT;")
        if "registered_date" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN registered_date TEXT;")
        if "product_enter_code" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN product_enter_code TEXT;")
        if "pricing_locked" not in product_cols:
            conn.execute(
                "ALTER TABLE products ADD COLUMN pricing_locked INTEGER NOT NULL DEFAULT 0 CHECK(pricing_locked IN (0, 1));"
            )
        if "color" in product_cols and "frame_color" not in product_cols:
            conn.execute("ALTER TABLE products RENAME COLUMN color TO frame_color;")
        product_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(products);").fetchall()
        }
        if "frame_color" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN frame_color TEXT;")
        if "lens_color" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN lens_color TEXT;")
        if "style" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN style TEXT;")
        if "palette" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN palette TEXT;")
        if "gender" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN gender TEXT;")
        conn.execute(
            """
            UPDATE products
            SET lens_color = 'Transparente'
            WHERE lens_color IS NULL OR TRIM(COALESCE(lens_color, '')) = '';
            """
        )

        missing_rows = conn.execute(
            """
            SELECT id, name, sku, registered_date, product_enter_code
            FROM products
            WHERE product_enter_code IS NULL OR product_enter_code = ''
               OR registered_date IS NULL OR registered_date = '';
            """
        ).fetchall()

        if missing_rows:
            today_text = datetime.now().date().isoformat()
            for row in missing_rows:
                row_id = int(row["id"])
                sku = row["sku"] if row["sku"] else "N/A"
                registered_date_text = (
                    row["registered_date"] if row["registered_date"] else today_text
                )
                try:
                    registered_date = datetime.fromisoformat(registered_date_text).date()
                except ValueError:
                    registered_date = datetime.now().date()

                code = make_product_enter_code(
                    product_name=row["name"], registered_date=registered_date
                )
                conn.execute(
                    """
                    UPDATE products
                    SET sku = ?, registered_date = ?, product_enter_code = ?
                    WHERE id = ?;
                    """,
                    (sku, registered_date.isoformat(), code, row_id),
                )

        conn.execute(
            """
            UPDATE products
            SET pricing_locked = 1
            WHERE pricing_locked = 0
              AND stock > 0
              AND (COALESCE(cost, 0) != 0 OR COALESCE(price, 0) != 0);
            """
        )

        migrate_product_skus_to_generated(conn)
        sync_sku_sequence_counter_from_skus(conn)
        sync_customer_sequence_counter_from_customers(conn)
        backfill_sales_cogs(conn)
        backfill_sku_master_from_products(conn)
        migrate_sku_cost_component_rows(conn)
