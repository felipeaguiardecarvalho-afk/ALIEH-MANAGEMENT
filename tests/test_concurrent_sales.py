"""
Testes de concorrência em vendas: múltiplas threads com conexões SQLite distintas.

Valida:
  • Estoque final coerente com a soma das vendas bem-sucedidas (invariante).
  • Ausência de stock negativo (constraint + lógica de negócio).
  • Códigos``sale_code`` únicos sob contenção.
  • Comportamento esperado com sobre-subscrição (parte das vendas falha).

Nota: ``record_sale`` usa ``BEGIN IMMEDIATE``, o que serializa escritores SQLite e
evita a corrida clássica leitura-validação-escrita com transacção diferida.
"""

from __future__ import annotations

import random
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

import pytest

from database import connection as connection_mod


TENANT = "default"
SKU_CONC = "TCONC-001"
PAYMENT = "Dinheiro"


def _seed_catalog(conn: sqlite3.Connection, *, initial_stock: float) -> tuple[int, int]:
    """Insere cliente, produto e linha ``sku_master`` mínimos para ``record_sale``."""
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO customers (
            tenant_id, customer_code, name, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?);
        """,
        (TENANT, "C00001", "Comprador concorrência", now, now),
    )
    cust_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    conn.execute(
        """
        INSERT INTO products (
            tenant_id, name, sku, registered_date, product_enter_code,
            cost, price, pricing_locked, stock,
            frame_color, lens_color, style, palette, gender,
            created_at, deleted_at
        ) VALUES (?, ?, ?, date('now'), ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, NULL);
        """,
        (
            TENANT,
            "Produto concorrência",
            SKU_CONC,
            "ENT-TCONC",
            1.0,
            1.0,
            initial_stock,
            "Preto",
            "Transparente",
            "Redondo",
            "Inverno",
            "Unissex",
            now,
        ),
    )
    prod_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    conn.execute(
        """
        INSERT INTO sku_master (
            tenant_id, sku, total_stock, avg_unit_cost, selling_price,
            updated_at, deleted_at, structured_cost_total
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, 0);
        """,
        (TENANT, SKU_CONC, initial_stock, 1.0, 25.0, now),
    )
    return prod_id, cust_id


@pytest.fixture
def concurrent_db(tmp_path, monkeypatch):
    """Base SQLite isolada por teste (ficheiro temporário)."""
    monkeypatch.setenv("DB_PROVIDER", "sqlite")
    db_path = tmp_path / "concurrent_sales.db"
    monkeypatch.setattr(connection_mod, "DB_PATH", db_path)
    from database.init_db import init_db

    init_db()
    with connection_mod.get_db_conn() as conn:
        prod_id, cust_id = _seed_catalog(conn, initial_stock=100.0)
    yield db_path, prod_id, cust_id


def _read_stock_and_sold(product_id: int) -> tuple[float, int]:
    with connection_mod.get_db_conn() as c:
        st = float(
            c.execute(
                "SELECT stock FROM products WHERE tenant_id = ? AND id = ?;",
                (TENANT, product_id),
            ).fetchone()[0]
        )
        row = c.execute(
            """
            SELECT COALESCE(SUM(quantity), 0) FROM sales
            WHERE tenant_id = ? AND product_id = ?;
            """,
            (TENANT, product_id),
        ).fetchone()
        sold = int(row[0])
    return st, sold


def _read_sku_master_total() -> float:
    with connection_mod.get_db_conn() as c:
        v = c.execute(
            """
            SELECT total_stock FROM sku_master
            WHERE tenant_id = ? AND sku = ?;
            """,
            (TENANT, SKU_CONC),
        ).fetchone()[0]
    return float(v)


def _run_concurrent_sales(
    product_id: int,
    customer_id: int,
    *,
    n_tasks: int,
    qty_per_task: int,
    max_workers: int,
) -> list[dict[str, Any]]:
    from services.sales_service import record_sale

    def _one(_i: int) -> dict[str, Any]:
        try:
            code, total = record_sale(
                product_id,
                qty_per_task,
                customer_id,
                0.0,
                payment_method=PAYMENT,
                tenant_id=TENANT,
            )
            return {"kind": "ok", "code": code, "total": total}
        except ValueError as exc:
            return {"kind": "val", "msg": str(exc)}

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_one, i) for i in range(n_tasks)]
        for f in as_completed(futures):
            results.append(f.result())
    return results


def test_concurrent_sales_all_succeed_stock_zero(concurrent_db):
    """Várias vendas paralelas esgotam o stock sem inconsistência."""
    _, product_id, customer_id = concurrent_db
    initial = 20.0
    with connection_mod.get_db_conn() as c:
        c.execute(
            "UPDATE products SET stock = ? WHERE tenant_id = ? AND id = ?;",
            (initial, TENANT, product_id),
        )
        c.execute(
            """
            UPDATE sku_master SET total_stock = ?
            WHERE tenant_id = ? AND sku = ?;
            """,
            (initial, TENANT, SKU_CONC),
        )
        c.commit()

    results = _run_concurrent_sales(
        product_id,
        customer_id,
        n_tasks=10,
        qty_per_task=2,
        max_workers=10,
    )
    oks = [r for r in results if r["kind"] == "ok"]
    assert len(oks) == 10
    codes = [r["code"] for r in oks]
    assert len(codes) == len(set(codes)), "sale_code duplicado sob concorrência"

    stock, sold_units = _read_stock_and_sold(product_id)
    assert stock == pytest.approx(0.0, abs=1e-6)
    assert sold_units == 20
    assert stock + sold_units == pytest.approx(initial, abs=1e-6)

    assert _read_sku_master_total() == pytest.approx(stock, abs=1e-6)


def test_concurrent_sales_oversubscribe_partial_failures(concurrent_db):
    """Sobre-subscrição: apenas parte das vendas conclui; estoque nunca negativo."""
    _, product_id, customer_id = concurrent_db
    initial = 7.0
    with connection_mod.get_db_conn() as c:
        c.execute(
            "UPDATE products SET stock = ? WHERE tenant_id = ? AND id = ?;",
            (initial, TENANT, product_id),
        )
        c.execute(
            """
            UPDATE sku_master SET total_stock = ?
            WHERE tenant_id = ? AND sku = ?;
            """,
            (initial, TENANT, SKU_CONC),
        )
        c.commit()

    results = _run_concurrent_sales(
        product_id,
        customer_id,
        n_tasks=12,
        qty_per_task=1,
        max_workers=12,
    )
    oks = [r for r in results if r["kind"] == "ok"]
    fails = [r for r in results if r["kind"] == "val"]
    assert len(oks) == 7
    assert len(fails) == 5

    stock, sold_units = _read_stock_and_sold(product_id)
    assert stock == pytest.approx(0.0, abs=1e-6)
    assert sold_units == 7
    assert stock >= -1e-9
    assert stock + sold_units == pytest.approx(initial, abs=1e-6)


def test_concurrent_sales_stress_random_quantities(concurrent_db):
    """Stress: quantidades aleatórias; invariante global e ``sku_master`` alinhado."""
    _, product_id, customer_id = concurrent_db
    initial = 50.0
    with connection_mod.get_db_conn() as c:
        c.execute(
            "UPDATE products SET stock = ? WHERE tenant_id = ? AND id = ?;",
            (initial, TENANT, product_id),
        )
        c.execute(
            """
            UPDATE sku_master SET total_stock = ?
            WHERE tenant_id = ? AND sku = ?;
            """,
            (initial, TENANT, SKU_CONC),
        )
        c.commit()

    random.seed(42)
    quantities = [random.randint(1, 3) for _ in range(30)]

    from services.sales_service import record_sale

    def _one(q: int) -> dict[str, Any]:
        try:
            code, total = record_sale(
                product_id,
                q,
                customer_id,
                0.0,
                payment_method=PAYMENT,
                tenant_id=TENANT,
            )
            return {"kind": "ok", "code": code, "q": q, "total": total}
        except ValueError:
            return {"kind": "val", "q": q}

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=15) as pool:
        futs = [pool.submit(_one, q) for q in quantities]
        for f in as_completed(futs):
            results.append(f.result())

    oks = [r for r in results if r["kind"] == "ok"]
    codes = [r["code"] for r in oks]
    assert len(codes) == len(set(codes))

    sold_sum = sum(r["q"] for r in oks)
    stock, sold_from_db = _read_stock_and_sold(product_id)
    assert sold_from_db == sold_sum
    assert stock + sold_from_db == pytest.approx(initial, abs=1e-6)
    assert stock >= -1e-9
    assert _read_sku_master_total() == pytest.approx(stock, abs=1e-6)
