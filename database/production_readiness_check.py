"""
Validação automática de prontidão para deploy em produção com Postgres (Supabase).

Executar na raiz do projeto (com ``.env`` configurado)::

    python -m database.production_readiness_check

Requisitos: ``DATABASE_URL`` preenchido e ``DB_PROVIDER=postgres`` (ou sinónimo aceite
por :mod:`database.config`). O script cria um ``tenant_id`` descartável, corre escrita
de negócio real via serviços e remove todas as linhas desse tenant no final.
"""

from __future__ import annotations

import logging
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import NoReturn

from dotenv import load_dotenv

_logger = logging.getLogger(__name__)


class ProductionReadinessError(Exception):
    """Falha de validação com mensagem já formatada para o operador."""


def _configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(message)s",
            stream=sys.stdout,
        )


def _fail(msg: str) -> NoReturn:
    raise ProductionReadinessError(msg)


def _validate_env() -> None:
    import os

    from database.config import DATABASE_URL_ENV, DB_PROVIDER_ENV, _normalize_db_provider

    url = (os.environ.get(DATABASE_URL_ENV) or "").strip()
    if not url:
        _fail(
            f"[FAIL] ENV -> {DATABASE_URL_ENV} ausente ou vazio. "
            "Defina o DSN do Supabase/Postgres antes do deploy."
        )

    raw_provider = (os.environ.get(DB_PROVIDER_ENV) or "").strip()
    if not raw_provider:
        _fail(
            f"[FAIL] ENV -> {DB_PROVIDER_ENV} deve estar definido explicitamente como "
            "'postgres' para este check (valores vazios nao sao aceites)."
        )
    try:
        provider = _normalize_db_provider(raw_provider)
    except ValueError as exc:
        _fail(f"[FAIL] ENV -> {DB_PROVIDER_ENV} invalido: {exc}")
    if provider != "postgres":
        _fail(
            f"[FAIL] ENV -> {DB_PROVIDER_ENV} deve resolver para Postgres; obtido: {provider!r}."
        )


def run() -> int:
    """Executa todas as etapas; devolve 0 se pronto, 1 caso contrário."""
    _configure_logging()
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    from database.config import BASE_DIR

    # Carrega .env na raiz do projecto; não sobrescreve variáveis já definidas.
    load_dotenv(Path(BASE_DIR) / ".env", override=False)

    exit_code = 1
    tenant_id: str | None = None

    try:
        _validate_env()
        _logger.info("[OK] ENV validado")

        tenant_id = f"prodchk_{uuid.uuid4().hex[:20]}"

        from database.repositories.readiness_probe_repository import (
            ensure_readiness_probe_sequence_counters,
            delete_readiness_probe_tenant_data,
        )
        from database.repositories.session import write_transaction

        with write_transaction(immediate=True) as conn:
            ensure_readiness_probe_sequence_counters(conn, tenant_id)
        _logger.info("[OK] sequências do tenant de verificação garantidas")

        from database.connection import get_postgres_conn

        with get_postgres_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1", prepare=False)
        _logger.info("Postgres connection OK")
        _logger.info("[OK] conexão Postgres")

        import psycopg

        from database.connection import get_db_conn

        probe_conn = get_db_conn()
        try:
            if not isinstance(probe_conn, psycopg.Connection):
                _fail(
                    "[FAIL] etapa motor de dados -> esperada ligacao psycopg (Postgres); "
                    "verifique DATABASE_URL e ausencia de fallback SQLite."
                )
        finally:
            probe_conn.close()

        from database.repositories.product_repository import get_distinct_skus_for_enter_code
        from database.repositories.query_repository import (
            fetch_customers_ordered,
            fetch_product_by_id,
            fetch_products,
        )
        from database.repositories.sales_repository import fetch_sale_row_by_code
        from services.customer_service import insert_customer_row
        from services.product_service import add_product, update_sku_selling_price
        from services.sales_service import record_sale

        tid = tenant_id
        suffix = uuid.uuid4().hex[:8]
        product_name = f"Prod readiness {suffix}"
        customer_name = f"Cliente readiness {suffix}"

        enter_code = add_product(
            product_name,
            stock=5.0,
            registered_date=date.today(),
            frame_color="Preto",
            lens_color="Cinza",
            style="Aviador",
            palette="Clássico",
            gender="Unissex",
            unit_cost=20.0,
            tenant_id=tid,
        )

        sku_rows = get_distinct_skus_for_enter_code(None, enter_code, tenant_id=tid)
        if len(sku_rows) != 1:
            _fail(
                f"[FAIL] escrita/leitura -> esperado 1 SKU para enter_code; obtido {len(sku_rows)}."
            )
        sku = (sku_rows[0]["sku"] or "").strip()
        if not sku:
            _fail("[FAIL] escrita/leitura -> SKU vazio apos cadastro.")

        update_sku_selling_price(
            sku, 100.0, note="production_readiness_check", tenant_id=tid
        )

        customer_code = insert_customer_row(
            customer_name,
            cpf=None,
            rg=None,
            phone=None,
            email=None,
            instagram=None,
            zip_code=None,
            street=None,
            number=None,
            neighborhood=None,
            city=None,
            state=None,
            country=None,
            tenant_id=tid,
        )

        customers = fetch_customers_ordered(tenant_id=tid)
        match = [r for r in customers if str(r["customer_code"]) == str(customer_code)]
        if len(match) != 1:
            _fail(
                "[FAIL] escrita/leitura -> cliente criado nao encontrado pela listagem."
            )
        customer_id = int(match[0]["id"])

        products = fetch_products(tenant_id=tid)
        prod_row = next(
            (p for p in products if (p["product_enter_code"] or "") == enter_code),
            None,
        )
        if prod_row is None:
            _fail("[FAIL] escrita/leitura -> produto nao encontrado apos cadastro.")
        product_id = int(prod_row["id"])
        stock_before = float(prod_row["stock"] or 0)
        if abs(stock_before - 5.0) > 1e-9:
            _fail(
                f"[FAIL] consistencia -> estoque inicial esperado 5.0; obtido {stock_before}."
            )

        qty_sold = 2
        sale_code, final_total = record_sale(
            product_id,
            qty_sold,
            customer_id,
            0.0,
            payment_method="Pix",
            tenant_id=tid,
        )

        row_after = fetch_product_by_id(product_id, tenant_id=tid)
        if row_after is None:
            _fail("[FAIL] escrita/leitura -> produto desapareceu apos venda.")

        stock_after = float(row_after["stock"] or 0)
        expected_total = 100.0 * qty_sold
        if float(final_total) <= 0:
            _fail(
                f"[FAIL] consistencia -> sale.total deve ser > 0; obtido {final_total}."
            )
        if abs(float(final_total) - expected_total) > 1e-6:
            _fail(
                f"[FAIL] consistencia -> total da venda esperado {expected_total}; "
                f"obtido {final_total}."
            )
        if abs(stock_after - (stock_before - qty_sold)) > 1e-9:
            _fail(
                f"[FAIL] consistencia -> estoque apos venda esperado {stock_before - qty_sold}; "
                f"obtido {stock_after}."
            )

        sale_row = fetch_sale_row_by_code(None, sale_code=sale_code, tenant_id=tid)
        if sale_row is None:
            _fail("[FAIL] consistencia -> venda nao encontrada pelo codigo.")
        if int(sale_row["customer_id"]) != customer_id:
            _fail(
                f"[FAIL] consistencia -> customer_id na venda esperado {customer_id}; "
                f"obtido {sale_row['customer_id']}."
            )
        if int(sale_row["product_id"]) != product_id:
            _fail(
                f"[FAIL] consistencia -> product_id na venda esperado {product_id}; "
                f"obtido {sale_row['product_id']}."
            )

        _logger.info("[OK] escrita/leitura")
        _logger.info("[OK] integridade")

        exit_code = 0

    except ProductionReadinessError as exc:
        _logger.error("%s", exc)
    except Exception as exc:
        _logger.error(
            "[FAIL] etapa inesperada -> %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
    finally:
        if tenant_id is not None:
            try:
                from database.repositories.readiness_probe_repository import (
                    delete_readiness_probe_tenant_data,
                )
                from database.repositories.session import write_transaction

                with write_transaction(immediate=True) as conn:
                    delete_readiness_probe_tenant_data(conn, tenant_id)
                _logger.info("[OK] cleanup")
            except Exception as exc:
                _logger.error(
                    "[FAIL] cleanup -> %s: %s",
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                exit_code = 1

    if exit_code == 0:
        print("PRODUCTION READY ✅", flush=True)
    else:
        print("NOT READY ❌", flush=True)

    return exit_code


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
