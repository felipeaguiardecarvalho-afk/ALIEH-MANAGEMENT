"""
Roteiro: baixa manual de stock (painel Estoque).

Valida :func:`database.repositories.product_repository.decrement_product_stock_manual`
e :func:`services.product_service.apply_manual_stock_write_down`: apenas ``products.stock``
diminui; custo e preço mantêm-se; ``sku_master.total_stock`` sincroniza.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from database import connection as connection_mod
from database.repositories.product_repository import decrement_product_stock_manual
from services.product_service import apply_manual_stock_write_down

TENANT = "default"
SKU_BAIXA = "TBAIXA-001"


def _seed_product_with_stock(conn, *, stock: float) -> int:
    now = datetime.now().isoformat(timespec="seconds")
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
            "Produto baixa test",
            SKU_BAIXA,
            "ENT-BAIXA",
            50.0,
            100.0,
            stock,
            "Preto",
            "Cinza",
            "Wayfarer",
            "Verão",
            "Unissex",
            now,
        ),
    )
    pid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        """
        INSERT INTO sku_master (
            tenant_id, sku, total_stock, avg_unit_cost, selling_price,
            updated_at, deleted_at, structured_cost_total
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, 0);
        """,
        (TENANT, SKU_BAIXA, stock, 50.0, 100.0, now),
    )
    return pid


@pytest.fixture
def baixa_db(tmp_path, monkeypatch):
    """SQLite isolado com um lote em stock para testes de baixa."""
    monkeypatch.setenv("DB_PROVIDER", "sqlite")
    db_path = tmp_path / "manual_stock_baixa.db"
    monkeypatch.setattr(connection_mod, "DB_PATH", db_path)
    from database.init_db import init_db

    init_db()
    with connection_mod.get_db_conn() as conn:
        pid = _seed_product_with_stock(conn, stock=10.0)
    yield db_path, pid


def test_decrement_product_stock_manual_reduces_stock_keeps_cost_price(baixa_db):
    _, pid = baixa_db
    with connection_mod.get_db_conn() as conn:
        new = decrement_product_stock_manual(conn, pid, 3.5, tenant_id=TENANT)
    assert new == pytest.approx(6.5)
    with connection_mod.get_db_conn() as c:
        row = c.execute(
            "SELECT stock, cost, price FROM products WHERE tenant_id = ? AND id = ?;",
            (TENANT, pid),
        ).fetchone()
        assert float(row[0]) == pytest.approx(6.5)
        assert float(row[1]) == pytest.approx(50.0)
        assert float(row[2]) == pytest.approx(100.0)
        sm = c.execute(
            "SELECT total_stock FROM sku_master WHERE tenant_id = ? AND sku = ?;",
            (TENANT, SKU_BAIXA),
        ).fetchone()
        assert float(sm[0]) == pytest.approx(6.5)


def test_apply_manual_stock_write_down_service(baixa_db):
    _, pid = baixa_db
    ns = apply_manual_stock_write_down(pid, 2.0, user_id="u-test", tenant_id=TENANT)
    assert ns == pytest.approx(8.0)
    with connection_mod.get_db_conn() as c:
        st = float(
            c.execute(
                "SELECT stock FROM products WHERE tenant_id = ? AND id = ?;",
                (TENANT, pid),
            ).fetchone()[0]
        )
        assert st == pytest.approx(8.0)


def test_decrement_rejects_insufficient_stock(baixa_db):
    _, pid = baixa_db
    with pytest.raises(ValueError, match="Stock insuficiente"):
        with connection_mod.get_db_conn() as conn:
            decrement_product_stock_manual(conn, pid, 50.0, tenant_id=TENANT)


def test_decrement_rejects_non_positive_qty(baixa_db):
    _, pid = baixa_db
    with pytest.raises(ValueError, match="maior que zero"):
        with connection_mod.get_db_conn() as conn:
            decrement_product_stock_manual(conn, pid, 0.0, tenant_id=TENANT)


def test_decrement_allows_full_depletion(baixa_db):
    _, pid = baixa_db
    with connection_mod.get_db_conn() as conn:
        new = decrement_product_stock_manual(conn, pid, 10.0, tenant_id=TENANT)
    assert new == pytest.approx(0.0)
    with connection_mod.get_db_conn() as c:
        sm = c.execute(
            "SELECT total_stock FROM sku_master WHERE tenant_id = ? AND sku = ?;",
            (TENANT, SKU_BAIXA),
        ).fetchone()
        assert float(sm[0]) == pytest.approx(0.0)
