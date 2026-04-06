"""
Criação e migração incremental do schema SQLite (ficheiro em ``database.connection.DB_PATH``,
por defeito ``/data/business.db``).

Chamado no arranque do Streamlit (`main()` do app). Usa ``CREATE TABLE IF NOT EXISTS`` e
alterações condicionais — **não** remove nem sobrescreve dados existentes.

**Paridade PostgreSQL / Supabase:** ver ``schema.sql`` na raiz do repositório. Mapeamento de tipos
SQLite → Postgres alinhado ao requisito portátil (TEXT / NUMERIC / BIGINT):

- ``TEXT`` → TEXT (datas ISO como texto).
- ``INTEGER`` PK / FK substituta / contadores → BIGSERIAL ou BIGINT.
- ``INTEGER`` flags 0/1 (ex.: ``pricing_locked``, ``is_active``) → BIGINT + CHECK no Postgres.
- ``REAL`` (preço, stock, percentagens, ``locked_until``) → NUMERIC.

O SQLite não distingue BIGINT; valores devem caber no intervalo escolhido em Postgres.
``tenant_id`` em todas as tabelas de negócio; FKs compostas ``(tenant_id, sku)`` → ``sku_master``
espelham ``database/migrate_sku_master_fks.py``.
"""

from __future__ import annotations

import re
from datetime import datetime

from database.config import get_db_provider
from database.connection import get_db_conn
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
from database.migrate_sku_master_composite import migrate_sku_master_composite_pk
from database.migrate_sku_master_fks import migrate_sku_master_referencing_foreign_keys
from database.tenant_migrate import migrate_multitenant_prepare
from database.tenancy import DEFAULT_TENANT_ID, iter_distinct_tenant_ids


def init_db() -> None:
    # Schema abaixo é SQLite-only; no Postgres aplique migrations fora (ex.: Supabase SQL).
    if get_db_provider() != "sqlite":
        return
    with get_db_conn() as conn:
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
                tenant_id TEXT NOT NULL DEFAULT 'default',
                sku TEXT NOT NULL,
                total_stock REAL NOT NULL DEFAULT 0,
                avg_unit_cost REAL NOT NULL DEFAULT 0,
                selling_price REAL NOT NULL DEFAULT 0,
                updated_at TEXT,
                PRIMARY KEY (tenant_id, sku)
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
                tenant_id TEXT NOT NULL DEFAULT 'default',
                id INTEGER NOT NULL CHECK (id = 1),
                last_value INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (tenant_id, id)
            );
            """
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
                tenant_id TEXT NOT NULL DEFAULT 'default',
                sku TEXT NOT NULL,
                component_key TEXT NOT NULL,
                label TEXT NOT NULL,
                unit_price REAL NOT NULL DEFAULT 0 CHECK(unit_price >= 0),
                quantity REAL NOT NULL DEFAULT 0 CHECK(quantity >= 0),
                line_total REAL NOT NULL DEFAULT 0 CHECK(line_total >= 0),
                updated_at TEXT,
                PRIMARY KEY (tenant_id, sku, component_key)
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
                tenant_id TEXT NOT NULL DEFAULT 'default',
                id INTEGER NOT NULL CHECK (id = 1),
                last_value INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (tenant_id, id)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sale_sequence_counter (
                tenant_id TEXT NOT NULL DEFAULT 'default',
                id INTEGER NOT NULL CHECK (id = 1),
                last_value INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (tenant_id, id)
            );
            """
        )

        # Antes de índices/colunas que assumem tenant_id em customers/users/etc.
        # Bases legadas: CREATE IF NOT EXISTS não altera tabelas antigas.
        migrate_multitenant_prepare(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO sku_sequence_counter (tenant_id, id, last_value)
            VALUES ('default', 1, 0);
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO customer_sequence_counter (tenant_id, id, last_value)
            VALUES ('default', 1, 0);
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO sale_sequence_counter (tenant_id, id, last_value)
            VALUES ('default', 1, 0);
            """
        )

        migrate_sku_master_composite_pk(conn)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                customer_code TEXT NOT NULL,
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
                updated_at TEXT,
                UNIQUE(tenant_id, customer_code)
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_customers_tenant_code ON customers(tenant_id, customer_code);"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                username TEXT NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'operator',
                UNIQUE(tenant_id, username)
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_tenant_username ON users(tenant_id, username);"
        )
        users_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(users);").fetchall()
        }
        if users_cols and "role" not in users_cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'operator';"
            )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS login_user_throttle (
                tenant_id TEXT NOT NULL DEFAULT 'default',
                username_norm TEXT NOT NULL,
                failure_count INTEGER NOT NULL DEFAULT 0,
                locked_until REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, username_norm)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS login_attempt_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                username_norm TEXT NOT NULL,
                success INTEGER NOT NULL CHECK(success IN (0, 1)),
                created_at TEXT NOT NULL,
                client_hint TEXT
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_login_audit_username ON login_attempt_audit(username_norm);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_login_audit_created ON login_attempt_audit(created_at);"
        )

        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS tr_login_attempt_audit_no_delete
            BEFORE DELETE ON login_attempt_audit
            BEGIN
                SELECT RAISE(ABORT, 'login_attempt_audit: DELETE não permitido (auditoria).');
            END;
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS tr_login_attempt_audit_no_update
            BEFORE UPDATE ON login_attempt_audit
            BEGIN
                SELECT RAISE(ABORT, 'login_attempt_audit: UPDATE não permitido (auditoria).');
            END;
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS tr_sku_deletion_audit_no_delete
            BEFORE DELETE ON sku_deletion_audit
            BEGIN
                SELECT RAISE(ABORT, 'sku_deletion_audit: DELETE não permitido (auditoria).');
            END;
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS tr_sku_deletion_audit_no_update
            BEFORE UPDATE ON sku_deletion_audit
            BEGIN
                SELECT RAISE(ABORT, 'sku_deletion_audit: UPDATE não permitido (auditoria).');
            END;
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uat_manual_checklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                test_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'pass', 'fail', 'blocked', 'na')),
                notes TEXT,
                result_recorded_at TEXT,
                recorded_by_username TEXT,
                recorded_by_user_id TEXT,
                recorded_by_role TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(tenant_id, test_id)
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_uat_checklist_tenant "
            "ON uat_manual_checklist(tenant_id);"
        )

        sales_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sales);").fetchall()}
        if "cogs_total" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN cogs_total REAL NOT NULL DEFAULT 0;")
        if "sku" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN sku TEXT;")

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
        if "payment_method" not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN payment_method TEXT;")

        for tid in iter_distinct_tenant_ids(conn):
            max_n = 0
            for row in conn.execute(
                """
                SELECT sale_code FROM sales
                WHERE tenant_id = ?
                  AND sale_code IS NOT NULL AND TRIM(sale_code) != '';
                """,
                (tid,),
            ):
                s = str(row["sale_code"] or "").strip().upper()
                m = re.match(r"^(\d{5})V$", s)
                if m:
                    max_n = max(max_n, int(m.group(1)))
            next_n = max_n + 1
            for row in conn.execute(
                """
                SELECT id FROM sales
                WHERE tenant_id = ?
                  AND (sale_code IS NULL OR TRIM(sale_code) = '')
                ORDER BY id ASC;
                """,
                (tid,),
            ):
                conn.execute(
                    "UPDATE sales SET sale_code = ? WHERE id = ?;",
                    (format_sale_code(next_n), int(row["id"])),
                )
                next_n += 1
            sync_sale_sequence_counter_from_sales(conn, tid)

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
        product_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(products);").fetchall()
        }
        if "product_image_path" not in product_cols:
            conn.execute("ALTER TABLE products ADD COLUMN product_image_path TEXT;")
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
        for tid in iter_distinct_tenant_ids(conn):
            sync_sku_sequence_counter_from_skus(conn, tid)
            sync_customer_sequence_counter_from_customers(conn, tid)
        backfill_sales_cogs(conn)
        backfill_sku_master_from_products(conn)
        migrate_sku_cost_component_rows(conn)

        pricing_rec_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(sku_pricing_records);").fetchall()
        }
        if pricing_rec_cols and "markup_kind" not in pricing_rec_cols:
            conn.execute(
                "ALTER TABLE sku_pricing_records ADD COLUMN markup_kind INTEGER NOT NULL DEFAULT 0;"
            )
            conn.execute(
                "ALTER TABLE sku_pricing_records ADD COLUMN taxes_kind INTEGER NOT NULL DEFAULT 0;"
            )
            conn.execute(
                "ALTER TABLE sku_pricing_records ADD COLUMN interest_kind INTEGER NOT NULL DEFAULT 0;"
            )

        migrate_sku_master_referencing_foreign_keys(conn)

        for tid in iter_distinct_tenant_ids(conn):
            conn.execute(
                """
                INSERT OR IGNORE INTO sku_sequence_counter (tenant_id, id, last_value)
                VALUES (?, 1, 0);
                """,
                (tid,),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO customer_sequence_counter (tenant_id, id, last_value)
                VALUES (?, 1, 0);
                """,
                (tid,),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO sale_sequence_counter (tenant_id, id, last_value)
                VALUES (?, 1, 0);
                """,
                (tid,),
            )
