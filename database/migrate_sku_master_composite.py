"""PK composta (tenant_id, sku) em sku_master e (tenant_id, sku, component_key) em sku_cost_components."""

from __future__ import annotations

import sqlite3

from database.tenancy import DEFAULT_TENANT_ID

_MIGRATION_ID = "sku_master_composite_pk_v1"


def _pk_column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    pk = sorted([(int(r[5] or 0), str(r[1])) for r in rows if int(r[5] or 0) > 0])
    return [name for _, name in pk]


def migrate_sku_master_composite_pk(conn: sqlite3.Connection) -> None:
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

    sm_info = conn.execute("PRAGMA table_info(sku_master);").fetchall()
    if not sm_info:
        conn.execute(
            "INSERT OR IGNORE INTO app_schema_migrations (id) VALUES (?);",
            (_MIGRATION_ID,),
        )
        return

    conn.execute("PRAGMA foreign_keys = OFF;")

    pk_sm = _pk_column_names(conn, "sku_master")
    if pk_sm != ["tenant_id", "sku"]:
        conn.execute("ALTER TABLE sku_master RENAME TO _sku_master_old;")
        conn.execute(
            """
            CREATE TABLE sku_master (
                tenant_id TEXT NOT NULL DEFAULT 'default',
                sku TEXT NOT NULL,
                total_stock REAL NOT NULL DEFAULT 0,
                avg_unit_cost REAL NOT NULL DEFAULT 0,
                selling_price REAL NOT NULL DEFAULT 0,
                structured_cost_total REAL NOT NULL DEFAULT 0,
                updated_at TEXT,
                deleted_at TEXT,
                PRIMARY KEY (tenant_id, sku)
            );
            """
        )
        n_old = conn.execute(
            "SELECT COUNT(*) AS c FROM _sku_master_old;"
        ).fetchone()["c"]
        conn.execute(
            f"""
            INSERT INTO sku_master (
                tenant_id, sku, total_stock, avg_unit_cost, selling_price,
                structured_cost_total, updated_at, deleted_at
            )
            SELECT
                COALESCE(tenant_id, '{DEFAULT_TENANT_ID}'), sku,
                total_stock, avg_unit_cost, selling_price,
                COALESCE(structured_cost_total, 0), updated_at, deleted_at
            FROM _sku_master_old;
            """
        )
        n_new = conn.execute("SELECT COUNT(*) AS c FROM sku_master;").fetchone()["c"]
        if int(n_old) != int(n_new):
            conn.execute("DROP TABLE sku_master;")
            conn.execute("ALTER TABLE _sku_master_old RENAME TO sku_master;")
            raise RuntimeError(
                f"sku_master: migração PK composta abortada — perda de linhas ({n_old} → {n_new})."
            )
        conn.execute("DROP TABLE _sku_master_old;")

    scc_info = conn.execute("PRAGMA table_info(sku_cost_components);").fetchall()
    if scc_info:
        pk_scc = _pk_column_names(conn, "sku_cost_components")
        if pk_scc != ["tenant_id", "sku", "component_key"]:
            conn.execute("ALTER TABLE sku_cost_components RENAME TO _scc_old;")
            conn.execute(
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
                    PRIMARY KEY (tenant_id, sku, component_key)
                );
                """
            )
            n_scc_old = conn.execute(
                "SELECT COUNT(*) AS c FROM _scc_old;"
            ).fetchone()["c"]
            conn.execute(
                f"""
                INSERT INTO sku_cost_components (
                    tenant_id, sku, component_key, label, unit_price, quantity,
                    line_total, updated_at
                )
                SELECT
                    COALESCE(tenant_id, '{DEFAULT_TENANT_ID}'), sku, component_key, label,
                    unit_price, quantity, line_total, updated_at
                FROM _scc_old;
                """
            )
            n_scc_new = conn.execute(
                "SELECT COUNT(*) AS c FROM sku_cost_components;"
            ).fetchone()["c"]
            if int(n_scc_old) != int(n_scc_new):
                conn.execute("DROP TABLE sku_cost_components;")
                conn.execute("ALTER TABLE _scc_old RENAME TO sku_cost_components;")
                raise RuntimeError(
                    f"sku_cost_components: migração PK abortada ({n_scc_old} → {n_scc_new})."
                )
            conn.execute("DROP TABLE _scc_old;")

    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(
        "INSERT OR IGNORE INTO app_schema_migrations (id) VALUES (?);",
        (_MIGRATION_ID,),
    )
