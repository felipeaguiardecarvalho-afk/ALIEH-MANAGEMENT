"""
Isolated prototype FastAPI layer. Adds repo root to sys.path, then imports existing services/* unchanged.
Run from this directory: see requirements.txt for the uvicorn command.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

_PROTOTYPE_DIR = Path(__file__).resolve().parent
_ROOT = _PROTOTYPE_DIR.parent
# Prototype package (`routes`, `deps`, …) must resolve from this folder even if cwd differs.
if str(_PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(_PROTOTYPE_DIR))
if str(_ROOT) not in sys.path:
    sys.path.insert(1, str(_ROOT))

# Mesmo .env da raiz do monorepo que o Streamlit / gate — uvicorn a partir de api-prototype/ não o carrega sozinho.
try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env", override=False)
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import http_exception_handler
from starlette.requests import Request
from starlette.responses import JSONResponse

import audit_db
from prototype_gateway_middleware import InternalGatewayMiddleware, TrustedOriginMiddleware
from prototype_observability import CorrelationAndAccessLogMiddleware
from prototype_env import is_production_runtime
from prototype_metrics import snapshot
from prototype_startup import validate_prototype_startup
from routes.audit import router as audit_router
from routes.costs import router as costs_router
from routes.customers import router as customers_router
from routes.dashboard import router as dashboard_router
from routes.inventory import router as inventory_router
from routes.pricing import router as pricing_router
from routes.products import router as products_router
from routes.sales import router as sales_router
from routes.storage import router as storage_router
from routes.uat import router as uat_router

_LOG = logging.getLogger("alieh.prototype.main")


def _run_callable_with_timeout(fn, *, timeout_sec: float = 5.0) -> tuple[bool, float, str | None]:
    t0 = time.perf_counter()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(fn)
            fut.result(timeout=timeout_sec)
        return True, round((time.perf_counter() - t0) * 1000, 2), None
    except concurrent.futures.TimeoutError:
        return False, round((time.perf_counter() - t0) * 1000, 2), "TimeoutError"
    except Exception as e:
        return False, round((time.perf_counter() - t0) * 1000, 2), type(e).__name__


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    validate_prototype_startup()
    audit_db.ensure_prototype_audit_table()
    from database.sale_idempotency import ensure_sale_idempotency_table, purge_expired_idempotency_rows

    ensure_sale_idempotency_table()
    try:
        n = await asyncio.to_thread(purge_expired_idempotency_rows)
        if n:
            _LOG.info("idempotency_purge_initial_removed=%s", n)
    except Exception:
        _LOG.exception("idempotency_purge_initial_failed")

    async def _purge_hourly():
        while True:
            await asyncio.sleep(3600)
            try:
                n = await asyncio.wait_for(
                    asyncio.to_thread(purge_expired_idempotency_rows),
                    timeout=120.0,
                )
                if n:
                    _LOG.info("idempotency_purge_hourly_removed=%s", n)
            except Exception:
                _LOG.exception("idempotency_purge_hourly_failed")

    task = asyncio.create_task(_purge_hourly())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="ALIEH API Prototype", version="0.1.0", lifespan=_lifespan)

# Ordem: último adicionado = mais exterior. Correlação por fora para X-Request-Id em toda a pilha.
app.add_middleware(InternalGatewayMiddleware)
app.add_middleware(TrustedOriginMiddleware)
app.add_middleware(CorrelationAndAccessLogMiddleware)

app.include_router(costs_router)
app.include_router(audit_router)
app.include_router(sales_router)
app.include_router(dashboard_router)
app.include_router(products_router)
app.include_router(customers_router)
app.include_router(inventory_router)
app.include_router(pricing_router)
app.include_router(uat_router)
app.include_router(storage_router)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return await http_exception_handler(request, exc)
    logging.getLogger("alieh.prototype").exception(
        "unhandled_exception",
        extra={"path": request.url.path, "method": request.method},
    )
    rid = (request.headers.get("X-Request-Id") or "").strip()
    headers = {"X-Request-Id": rid} if rid else {}
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Erro interno do servidor.",
            "error": {
                "code": "internal_error",
                "message": "Erro interno do servidor.",
                "context": {"path": request.url.path},
            },
        },
        headers=headers,
    )


def _sales_route_paths() -> list[str]:
    return sorted(
        getattr(r, "path", "")
        for r in app.routes
        if getattr(r, "path", "").startswith("/sales/")
    )


def _core_tables_probe() -> dict:
    """Verificação leve de acesso às tabelas centrais (sem alterar dados)."""
    t0 = time.perf_counter()
    try:
        from database.repositories.support import use_connection
        from database.sql_compat import db_execute

        with use_connection(None) as conn:
            db_execute(conn, "SELECT 1 FROM products WHERE false;", ()).fetchall()
        return {"ok": True, "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}
    except Exception as e:
        return {
            "ok": False,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "error_type": type(e).__name__,
        }


def _worst_status(*parts: str) -> str:
    if "FAIL" in parts:
        return "FAIL"
    if "DEGRADED" in parts:
        return "DEGRADED"
    return "OK"


def _component_line(block: dict, *, slow_ms: float = 1200.0) -> str:
    if not block.get("ok"):
        return "FAIL"
    try:
        lat = float(block.get("latency_ms") or 0)
    except (TypeError, ValueError):
        lat = 0.0
    if lat > slow_ms:
        return "DEGRADED"
    return "OK"


@app.get("/metrics")
def metrics(request: Request):
    """Contadores em memória (sem PII). Em produção exige ``?token=ALIEH_METRICS_SCRAPE_TOKEN``."""
    if is_production_runtime():
        token = (os.environ.get("ALIEH_METRICS_SCRAPE_TOKEN") or "").strip()
        q = (request.query_params.get("token") or "").strip()
        if not token or q != token:
            raise HTTPException(status_code=404, detail="Not Found")
    return snapshot()


@app.get("/health")
def health():
    sales_paths = _sales_route_paths()

    def _db_probe():
        from database.connection import check_database_health

        check_database_health()

    db_ok, db_ms, db_err = _run_callable_with_timeout(_db_probe, timeout_sec=5.0)
    db_block = {
        "ok": db_ok,
        "latency_ms": db_ms,
        **({"error_type": db_err} if db_err else {}),
    }

    core = _core_tables_probe()
    core_line = _component_line(core)

    db_line = "FAIL" if not db_block.get("ok") else _component_line(db_block)

    overall = _worst_status(db_line, core_line)
    return {
        "status": overall,
        "prototype": True,
        "sales_paths": sales_paths,
        "dependencies": {
            "database": db_block,
            "core_tables": core,
            "database_status": db_line,
            "core_tables_status": core_line,
        },
    }
