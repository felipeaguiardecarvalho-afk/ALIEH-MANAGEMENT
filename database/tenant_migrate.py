"""Migração one-shot: coluna ``tenant_id`` e chaves adequadas a vários inquilinos (idempotente)."""

from __future__ import annotations

import sqlite3

from database.tenancy import DEFAULT_TENANT_ID

_MIGRATION_ID = "tenant_multitenant_v1"


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table});").fetchall()}


def _ensure_tenant_text_column(conn: sqlite3.Connection, table: str) -> None:
    if not _cols(conn, table):
        return
    if "tenant_id" in _cols(conn, table):
        return
    conn.execute(
        f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}';"
    )


def _migrate_counter(conn: sqlite3.Connection, table: str) -> None:
    if not _cols(conn, table):
        return
    if "tenant_id" in _cols(conn, table):
        return
    conn.execute(f"ALTER TABLE {table} RENAME TO _{table}_old;")
    conn.execute(
        f"""
        CREATE TABLE {table} (
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            id INTEGER NOT NULL CHECK (id = 1),
            last_value INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (tenant_id, id)
        );
        """
    )
    conn.execute(
        f"""
        INSERT INTO {table} (tenant_id, id, last_value)
        SELECT '{DEFAULT_TENANT_ID}', id, last_value FROM _{table}_old;
        """
    )
    conn.execute(f"DROP TABLE _{table}_old;")
    conn.execute(
        f"""
        INSERT OR IGNORE INTO {table} (tenant_id, id, last_value)
        VALUES ('{DEFAULT_TENANT_ID}', 1, 0);
        """
    )


def _migrate_users(conn: sqlite3.Connection) -> None:
    if not _cols(conn, "users"):
        return
    if "tenant_id" in _cols(conn, "users"):
        return
    conn.execute("ALTER TABLE users RENAME TO _users_old;")
    conn.execute(
        f"""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            username TEXT NOT NULL COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'operator',
            UNIQUE(tenant_id, username)
        );
        """
    )
    conn.execute(
        """
        INSERT INTO users (id, tenant_id, username, password_hash, created_at, role)
        SELECT id, ?, username, password_hash, created_at, role
        FROM _users_old;
        """,
        (DEFAULT_TENANT_ID,),
    )
    conn.execute("DROP TABLE _users_old;")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_tenant_username ON users(tenant_id, username);"
    )


def _migrate_customers(conn: sqlite3.Connection) -> None:
    if not _cols(conn, "customers"):
        return
    if "tenant_id" in _cols(conn, "customers"):
        return
    conn.execute("ALTER TABLE customers RENAME TO _customers_old;")
    conn.execute(
        f"""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
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
        """
        INSERT INTO customers (
            id, tenant_id, customer_code, name, cpf, rg, phone, email, instagram,
            zip_code, street, number, neighborhood, city, state, country, created_at, updated_at
        )
        SELECT id, ?, customer_code, name, cpf, rg, phone, email, instagram,
               zip_code, street, number, neighborhood, city, state, country, created_at, updated_at
        FROM _customers_old;
        """,
        (DEFAULT_TENANT_ID,),
    )
    conn.execute("DROP TABLE _customers_old;")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_customers_tenant_code ON customers(tenant_id, customer_code);"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);")


def _migrate_login_user_throttle(conn: sqlite3.Connection) -> None:
    if not _cols(conn, "login_user_throttle"):
        return
    if "tenant_id" in _cols(conn, "login_user_throttle"):
        return
    conn.execute("ALTER TABLE login_user_throttle RENAME TO _lut_old;")
    conn.execute(
        f"""
        CREATE TABLE login_user_throttle (
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
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
        INSERT INTO login_user_throttle (
            tenant_id, username_norm, failure_count, locked_until, updated_at
        )
        SELECT ?, username_norm, failure_count, locked_until, updated_at
        FROM _lut_old;
        """,
        (DEFAULT_TENANT_ID,),
    )
    conn.execute("DROP TABLE _lut_old;")


def migrate_multitenant_prepare(conn: sqlite3.Connection) -> None:
    """
    Garante ``tenant_id`` nas tabelas principais e chaves (users, customers, throttle, contadores).

    Comportamento existente: todas as linhas ficam com ``tenant_id = 'default'``.
    """
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

    conn.execute("PRAGMA foreign_keys = OFF;")

    simple_tables = [
        "products",
        "sales",
        "stock_cost_entries",
        "price_history",
        "sku_master",
        "sku_pricing_records",
        "sku_cost_components",
        "sku_deletion_audit",
        "uat_manual_checklist",
    ]
    for t in simple_tables:
        if _cols(conn, t):
            _ensure_tenant_text_column(conn, t)

    if _cols(conn, "login_attempt_audit"):
        _ensure_tenant_text_column(conn, "login_attempt_audit")

    if _cols(conn, "sku_sequence_counter"):
        _migrate_counter(conn, "sku_sequence_counter")
    if _cols(conn, "sale_sequence_counter"):
        _migrate_counter(conn, "sale_sequence_counter")
    if _cols(conn, "customer_sequence_counter"):
        _migrate_counter(conn, "customer_sequence_counter")
    _migrate_users(conn)
    _migrate_customers(conn)
    _migrate_login_user_throttle(conn)

    conn.execute("PRAGMA foreign_keys = ON;")

    conn.execute(
        "INSERT OR IGNORE INTO app_schema_migrations (id) VALUES (?);",
        (_MIGRATION_ID,),
    )
