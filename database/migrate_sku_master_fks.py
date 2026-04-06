"""
Foreign keys compostas para ``sku_master (tenant_id, sku)`` em tabelas filhas.

- Exige migração prévia ``sku_master_composite_pk_v1`` (PK composta no mestre).
- Garante linhas ``sku_master`` em falta (stubs) antes do rebuild — sem perda de dados
  em tabelas que referenciam SKUs ainda não agregados ao mestre.
- Idempotente: registo ``sku_master_referencing_fks_v1`` em ``app_schema_migrations``.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from database.tenancy import DEFAULT_TENANT_ID

_MIGRATION_ID = "sku_master_referencing_fks_v1"
_PREREQ = "sku_master_composite_pk_v1"


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(r[1]) for r in conn.execute(f"PRAGMA table_info({table});").fetchall()]


def _references_sku_master(conn: sqlite3.Connection, table: str) -> bool:
    """True se já existem FKs declaradas para a tabela ``sku_master``."""
    rows = conn.execute(f"PRAGMA foreign_key_list({table});").fetchall()
    for r in rows:
        if len(r) > 2 and str(r[2]) == "sku_master":
            return True
    return False


def _restore_autoincrement_seq(conn: sqlite3.Connection, table: str) -> None:
    pk_col = "id"
    info = conn.execute(f"PRAGMA table_info({table});").fetchall()
    if not info:
        return
    mx = conn.execute(f"SELECT MAX({pk_col}) AS m FROM {table};").fetchone()
    if not mx or mx["m"] is None:
        return
    seq = int(mx["m"])
    conn.execute("DELETE FROM sqlite_sequence WHERE name = ?;", (table,))
    conn.execute(
        "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?);",
        (table, seq),
    )


def _ensure_sku_master_stubs(conn: sqlite3.Connection, table: str) -> None:
    cols = set(_table_columns(conn, table))
    if "tenant_id" not in cols or "sku" not in cols:
        return
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        f"""
        INSERT OR IGNORE INTO sku_master (
            tenant_id, sku, total_stock, avg_unit_cost, selling_price,
            structured_cost_total, updated_at, deleted_at
        )
        SELECT DISTINCT
            COALESCE(t.tenant_id, ?),
            t.sku,
            0, 0, 0, 0, ?, NULL
        FROM {table} t
        WHERE t.sku IS NOT NULL AND TRIM(t.sku) != ''
          AND NOT EXISTS (
              SELECT 1 FROM sku_master m
              WHERE m.tenant_id = COALESCE(t.tenant_id, ?) AND m.sku = t.sku
          );
        """,
        (DEFAULT_TENANT_ID, now, DEFAULT_TENANT_ID),
    )


def _rebuild_table_copy(
    conn: sqlite3.Connection,
    table: str,
    create_sql: str,
) -> None:
    cols = _table_columns(conn, table)
    if not cols:
        return
    backup = f"_bk_{table}_fk_mig"
    conn.execute(f"ALTER TABLE {table} RENAME TO {backup};")
    conn.execute(create_sql)
    collist = ", ".join(cols)
    conn.execute(
        f"INSERT INTO {table} ({collist}) SELECT {collist} FROM {backup};"
    )
    c_old = conn.execute(f"SELECT COUNT(*) AS c FROM {backup};").fetchone()["c"]
    c_new = conn.execute(f"SELECT COUNT(*) AS c FROM {table};").fetchone()["c"]
    if int(c_old) != int(c_new):
        conn.execute(f"DROP TABLE {table};")
        conn.execute(f"ALTER TABLE {backup} RENAME TO {table};")
        raise RuntimeError(
            f"{table}: migração FK abortada — contagem de linhas não coincide "
            f"({c_old} → {c_new})."
        )
    conn.execute(f"DROP TABLE {backup};")
    if "id" in cols:
        _restore_autoincrement_seq(conn, table)


def migrate_sku_master_referencing_foreign_keys(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_schema_migrations (
            id TEXT PRIMARY KEY
        );
        """
    )
    if conn.execute(
        "SELECT 1 FROM app_schema_migrations WHERE id = ?;",
        (_MIGRATION_ID,),
    ).fetchone():
        return
    if not conn.execute(
        "SELECT 1 FROM app_schema_migrations WHERE id = ?;",
        (_PREREQ,),
    ).fetchone():
        # Mestre ainda com PK só em sku — composite deve correr primeiro no init_db.
        return

    conn.execute("PRAGMA foreign_keys = OFF;")

    for t in (
        "stock_cost_entries",
        "sales",
        "price_history",
        "sku_pricing_records",
        "sku_cost_components",
    ):
        if not _table_columns(conn, t):
            continue
        if _references_sku_master(conn, t):
            continue
        _ensure_sku_master_stubs(conn, t)

    if _table_columns(conn, "stock_cost_entries") and not _references_sku_master(
        conn, "stock_cost_entries"
    ):
        _rebuild_table_copy(
            conn,
            "stock_cost_entries",
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
                tenant_id TEXT NOT NULL DEFAULT 'default',
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (tenant_id, sku) REFERENCES sku_master(tenant_id, sku)
            );
            """,
        )

    if _table_columns(conn, "sales") and not _references_sku_master(conn, "sales"):
        _rebuild_table_copy(
            conn,
            "sales",
            """
            CREATE TABLE sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity >= 1),
                total REAL NOT NULL,
                sold_at TEXT NOT NULL,
                cogs_total REAL NOT NULL DEFAULT 0,
                sku TEXT,
                sale_code TEXT,
                customer_id INTEGER,
                unit_price REAL,
                discount_amount REAL NOT NULL DEFAULT 0,
                base_amount REAL,
                payment_method TEXT,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (tenant_id, sku) REFERENCES sku_master(tenant_id, sku)
            );
            """,
        )

    if _table_columns(conn, "price_history") and not _references_sku_master(
        conn, "price_history"
    ):
        _rebuild_table_copy(
            conn,
            "price_history",
            """
            CREATE TABLE price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                old_price REAL,
                new_price REAL NOT NULL,
                created_at TEXT NOT NULL,
                note TEXT,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                FOREIGN KEY (tenant_id, sku) REFERENCES sku_master(tenant_id, sku)
            );
            """,
        )

    if _table_columns(conn, "sku_pricing_records") and not _references_sku_master(
        conn, "sku_pricing_records"
    ):
        create_sql = """
            CREATE TABLE sku_pricing_records (
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
                is_active INTEGER NOT NULL DEFAULT 0 CHECK(is_active IN (0, 1)),
                tenant_id TEXT NOT NULL DEFAULT 'default',
                markup_kind INTEGER NOT NULL DEFAULT 0,
                taxes_kind INTEGER NOT NULL DEFAULT 0,
                interest_kind INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (tenant_id, sku) REFERENCES sku_master(tenant_id, sku)
            );
            """
        _rebuild_table_copy(conn, "sku_pricing_records", create_sql)

    if _table_columns(conn, "sku_cost_components") and not _references_sku_master(
        conn, "sku_cost_components"
    ):
        _rebuild_table_copy(
            conn,
            "sku_cost_components",
            """
            CREATE TABLE sku_cost_components (
                tenant_id TEXT NOT NULL DEFAULT 'default',
                sku TEXT NOT NULL,
                component_key TEXT NOT NULL,
                label TEXT NOT NULL,
                unit_price REAL NOT NULL DEFAULT 0 CHECK(unit_price >= 0),
                quantity REAL NOT NULL DEFAULT 0 CHECK(quantity >= 0),
                line_total REAL NOT NULL DEFAULT 0 CHECK(line_total >= 0),
                updated_at TEXT,
                PRIMARY KEY (tenant_id, sku, component_key),
                FOREIGN KEY (tenant_id, sku) REFERENCES sku_master(tenant_id, sku)
            );
            """,
        )

    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(
        "INSERT OR IGNORE INTO app_schema_migrations (id) VALUES (?);",
        (_MIGRATION_ID,),
    )
