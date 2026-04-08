"""Comparar contagens, totais financeiros e entidades principais entre SQLite e PostgreSQL.

Gera relatório textual para validar paridade após migração ou sincronização. Abre o SQLite
directamente pelo caminho do ficheiro (não usa :func:`database.connection.get_db_conn`),
para não depender de ``DB_PROVIDER`` / ``DATABASE_URL`` ao mesmo tempo.

PostgreSQL abre uma **ligação nova e dedicada** por relatório via ``get_postgres_conn`` (sem reutilizar
ligação global da app). Pilha pooler-safe (``prepare_threshold=0``, ``autocommit``, ``DISCARD ALL``,
etc.). Consultas no Postgres usam ``cursor().execute()`` (não ``Connection.execute``).

Uso::

    python -m database.cross_db_parity

    # ou com caminho explícito do SQLite:
    python -m database.cross_db_parity --sqlite C:/path/to/business.db

Requer ``DATABASE_URL`` (ou cadeia Supabase) para Postgres; opcionalmente ``.env`` na raiz.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv

# Raiz do repositório: database/ → parent é pacote, parent.parent é repo.
_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env", override=False)
logging.getLogger(__name__).info(
    "DATABASE_URL detected: %s",
    "yes" if (os.environ.get("DATABASE_URL") or "").strip() else "no",
)

from database.connection import DB_PATH, get_postgres_conn
from database.sql_compat import is_sqlite_conn, qmarks_to_percent_s

_logger = logging.getLogger(__name__)
_pg_cursor_exec_logged = False


@contextmanager
def _parity_dedicated_postgres():
    """
    Context manager: **nova** ligação PostgreSQL só para este fluxo de parity (fecha ao sair).

    ``silent_probe=True`` evita misturar logs de selecção de backend com a sessão da aplicação.
    """
    _logger.info(
        "Parity: opening dedicated PostgreSQL connection (not reusing app-wide connection state)"
    )
    with get_postgres_conn(silent_probe=True) as conn:
        yield conn


# Tabelas de domínio (schema.sql / init); nomes validados só a partir desta lista.
_TABLES_COMPARE: tuple[str, ...] = (
    "app_schema_migrations",
    "products",
    "sku_master",
    "customers",
    "users",
    "sku_sequence_counter",
    "customer_sequence_counter",
    "sale_sequence_counter",
    "price_history",
    "sku_cost_components",
    "sku_pricing_records",
    "stock_cost_entries",
    "sales",
    "sku_deletion_audit",
    "login_user_throttle",
    "login_attempt_audit",
    "uat_manual_checklist",
)

# Qualificar ``FROM`` / ``JOIN`` com ``public.`` nas queries enviadas ao Postgres.
_TABLE_ALT = "|".join(re.escape(t) for t in sorted(_TABLES_COMPARE, key=len, reverse=True))
_QUALIFY_PUBLIC_SQL = re.compile(rf"\b(FROM|JOIN)\s+({_TABLE_ALT})\b", re.IGNORECASE)


def _postgres_sql_public(sql: str) -> str:
    def _sub(m: re.Match[str]) -> str:
        return f"{m.group(1)} public.{m.group(2)}"

    return _QUALIFY_PUBLIC_SQL.sub(_sub, sql)


def _exec(conn: Any, sql: str, params: Sequence[Any] = ()) -> Any:
    """Executa SQL com ``?`` (SQLite) ou ``%s`` (Postgres).

    No PostgreSQL usa :meth:`cursor` explícito (sem ``Connection.execute``), alinhado a
    ``prepare_threshold=0`` / pooler Supabase.
    """
    global _pg_cursor_exec_logged
    sql_use = sql if is_sqlite_conn(conn) else qmarks_to_percent_s(sql)
    if is_sqlite_conn(conn):
        return conn.execute(sql_use, params)
    if not _pg_cursor_exec_logged:
        _logger.info("Using cursor-based execution (no prepared statements)")
        _pg_cursor_exec_logged = True
    cur = conn.cursor()
    try:
        cur.execute(sql_use, params, prepare=False)
        return cur
    except Exception:
        cur.close()
        raise


def _scalar_float(
    conn: Any, sql: str, *, context: str = "", strict_pg: bool = True
) -> float | None:
    is_sqlite = is_sqlite_conn(conn)
    cur = None
    try:
        cur = _exec(conn, sql, ())
        row = cur.fetchone()
        if row is None:
            if not is_sqlite and strict_pg:
                _logger.error(
                    "PostgreSQL parity read returned no row [%s]: %s",
                    context or "scalar_float",
                    sql[:500],
                )
                raise RuntimeError(
                    f"PostgreSQL returned no row for {context or 'scalar_float'!r}"
                )
            return None
        v = row["v"] if isinstance(row, dict) else row[0]
        return float(v) if v is not None else 0.0
    except Exception as exc:
        if not is_sqlite and strict_pg:
            _logger.error(
                "PostgreSQL parity read failed [%s]: %s | sql=%s",
                context or "scalar_float",
                exc,
                sql[:500],
                exc_info=True,
            )
            raise
        _logger.debug("scalar_float skip (sqlite): %s | %s", sql[:80], exc)
        return None
    finally:
        if cur is not None:
            cur.close()


def _scalar_int(
    conn: Any, sql: str, *, context: str = "", strict_pg: bool = True
) -> int | None:
    is_sqlite = is_sqlite_conn(conn)
    cur = None
    try:
        cur = _exec(conn, sql, ())
        row = cur.fetchone()
        if row is None:
            if not is_sqlite and strict_pg:
                _logger.error(
                    "PostgreSQL parity read returned no row [%s]: %s",
                    context or "scalar_int",
                    sql[:500],
                )
                raise RuntimeError(
                    f"PostgreSQL returned no row for {context or 'scalar_int'!r}"
                )
            return None
        v = row["c"] if isinstance(row, dict) else row[0]
        return int(v) if v is not None else 0
    except Exception as exc:
        if not is_sqlite and strict_pg:
            _logger.error(
                "PostgreSQL parity read failed [%s]: %s | sql=%s",
                context or "scalar_int",
                exc,
                sql[:500],
                exc_info=True,
            )
            raise
        _logger.debug("scalar_int skip (sqlite): %s | %s", sql[:80], exc)
        return None
    finally:
        if cur is not None:
            cur.close()


def open_sqlite_for_compare(sqlite_path: Path | None) -> sqlite3.Connection:
    path = sqlite_path if sqlite_path is not None else DB_PATH
    conn = sqlite3.connect(str(path), timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _mask_dsn(dsn: str) -> str:
    if not dsn:
        return "(vazio)"
    return re.sub(r"(//[^:/]+:)([^@]+)(@)", r"\1***\3", dsn, count=1)


@dataclass
class TableCountResult:
    table: str
    sqlite_rows: int | None
    postgres_rows: int | None

    @property
    def match(self) -> bool:
        if self.sqlite_rows is None or self.postgres_rows is None:
            return False
        return self.sqlite_rows == self.postgres_rows


@dataclass
class MetricResult:
    label: str
    sqlite_value: float | None
    postgres_value: float | None
    abs_tolerance: float = 0.02

    @property
    def match(self) -> bool:
        if self.sqlite_value is None or self.postgres_value is None:
            return False
        return abs(float(self.sqlite_value) - float(self.postgres_value)) <= self.abs_tolerance


@dataclass
class EntitySnapshot:
    label: str
    sqlite_value: int | None
    postgres_value: int | None

    @property
    def match(self) -> bool:
        if self.sqlite_value is None or self.postgres_value is None:
            return False
        return self.sqlite_value == self.postgres_value


@dataclass
class ParityReport:
    generated_at_utc: str
    sqlite_path: str
    postgres_target: str
    table_counts: list[TableCountResult] = field(default_factory=list)
    financial_metrics: list[MetricResult] = field(default_factory=list)
    entity_metrics: list[EntitySnapshot] = field(default_factory=list)

    @property
    def counts_ok(self) -> bool:
        return all(x.match for x in self.table_counts)

    @property
    def financials_ok(self) -> bool:
        return all(x.match for x in self.financial_metrics)

    @property
    def entities_ok(self) -> bool:
        return all(x.match for x in self.entity_metrics)

    @property
    def all_ok(self) -> bool:
        return self.counts_ok and self.financials_ok and self.entities_ok


def _collect_table_counts(s_conn: sqlite3.Connection, p_conn: Any) -> list[TableCountResult]:
    out: list[TableCountResult] = []
    for table in _TABLES_COMPARE:
        sq = _scalar_int(
            s_conn,
            f"SELECT COUNT(*) AS c FROM {table}",
            context=f"sqlite count {table}",
            strict_pg=False,
        )
        pq = _scalar_int(
            p_conn,
            f"SELECT COUNT(*) AS c FROM public.{table}",
            context=f"postgres count public.{table}",
        )
        out.append(TableCountResult(table, sq, pq))
    return out


def _collect_financial_metrics(s_conn: sqlite3.Connection, p_conn: Any) -> list[MetricResult]:
    specs: list[tuple[str, str, float]] = [
        ("Vendas: SUM(total)", "SELECT COALESCE(SUM(total), 0) AS v FROM sales", 0.02),
        ("Vendas: SUM(cogs_total)", "SELECT COALESCE(SUM(cogs_total), 0) AS v FROM sales", 0.02),
        (
            "Vendas: SUM(discount_amount)",
            "SELECT COALESCE(SUM(discount_amount), 0) AS v FROM sales",
            0.02,
        ),
        (
            "Produtos: SUM(stock) linhas activas",
            "SELECT COALESCE(SUM(stock), 0) AS v FROM products WHERE deleted_at IS NULL",
            0.02,
        ),
        (
            "Produtos: SUM(stock * cost) estimativa",
            "SELECT COALESCE(SUM(stock * cost), 0) AS v FROM products WHERE deleted_at IS NULL",
            0.05,
        ),
        (
            "sku_master: SUM(total_stock) activos",
            "SELECT COALESCE(SUM(total_stock), 0) AS v FROM sku_master WHERE deleted_at IS NULL",
            0.02,
        ),
    ]
    out: list[MetricResult] = []
    for label, sql, tol in specs:
        sv = _scalar_float(s_conn, sql, context=f"sqlite {label}", strict_pg=False)
        pv = _scalar_float(
            p_conn,
            _postgres_sql_public(sql),
            context=f"postgres {label}",
        )
        out.append(MetricResult(label, sv, pv, abs_tolerance=tol))
    return out


def _collect_entity_metrics(s_conn: sqlite3.Connection, p_conn: Any) -> list[EntitySnapshot]:
    specs: list[tuple[str, str]] = [
        ("DISTINCT tenant_id em products", "SELECT COUNT(DISTINCT tenant_id) AS c FROM products"),
        ("DISTINCT tenant_id em customers", "SELECT COUNT(DISTINCT tenant_id) AS c FROM customers"),
        ("DISTINCT tenant_id em sales", "SELECT COUNT(DISTINCT tenant_id) AS c FROM sales"),
        ("DISTINCT tenant_id em sku_master", "SELECT COUNT(DISTINCT tenant_id) AS c FROM sku_master"),
        (
            "Linhas sku_master (não apagado)",
            "SELECT COUNT(*) AS c FROM sku_master WHERE deleted_at IS NULL",
        ),
        ("Utilizadores (users)", "SELECT COUNT(*) AS c FROM users"),
        ("Clientes (customers)", "SELECT COUNT(*) AS c FROM customers"),
        ("Produtos (products)", "SELECT COUNT(*) AS c FROM products"),
    ]
    out: list[EntitySnapshot] = []
    for label, sql in specs:
        out.append(
            EntitySnapshot(
                label,
                _scalar_int(s_conn, sql, context=f"sqlite {label}", strict_pg=False),
                _scalar_int(
                    p_conn,
                    _postgres_sql_public(sql),
                    context=f"postgres {label}",
                ),
            )
        )
    return out


def compare_sqlite_postgres(
    *,
    sqlite_path: Path | None = None,
    postgres_dsn_hint: str | None = None,
) -> ParityReport:
    """
    Compara SQLite (ficheiro) com PostgreSQL (DSN em ambiente).

    ``postgres_dsn_hint``: só para mérito do relatório (ex.: máscara); a ligação real é
    aberta por :func:`_parity_dedicated_postgres` (nova sessão :func:`~database.connection.get_postgres_conn`).
    """
    from database.config import get_postgres_dsn, get_supabase_db_url

    dsn = postgres_dsn_hint
    if not dsn:
        dsn = (get_supabase_db_url() or get_postgres_dsn() or "").strip()
    target = _mask_dsn(dsn) if dsn else "postgres:(sem DSN no relatório)"

    path = sqlite_path if sqlite_path is not None else DB_PATH
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")

    s_conn = open_sqlite_for_compare(sqlite_path)
    try:
        with _parity_dedicated_postgres() as p_conn:
            report = ParityReport(
                generated_at_utc=generated,
                sqlite_path=str(path),
                postgres_target=target,
                table_counts=_collect_table_counts(s_conn, p_conn),
                financial_metrics=_collect_financial_metrics(s_conn, p_conn),
                entity_metrics=_collect_entity_metrics(s_conn, p_conn),
            )
    finally:
        s_conn.close()

    _logger.info(
        "Paridade SQLite × Postgres: contagens %s | financeiro %s | entidades %s",
        "OK" if report.counts_ok else "DIVERGÊNCIA",
        "OK" if report.financials_ok else "DIVERGÊNCIA",
        "OK" if report.entities_ok else "DIVERGÊNCIA",
    )
    return report


def format_parity_report_text(report: ParityReport) -> str:
    """Relatório legível (texto puro)."""
    lines: list[str] = [
        "=" * 80,
        "RELATÓRIO DE PARIDADE — SQLite × PostgreSQL",
        "=" * 80,
        f"Gerado (UTC): {report.generated_at_utc}",
        f"SQLite:      {report.sqlite_path}",
        f"PostgreSQL:  {report.postgres_target}",
        "",
        "1) CONTAGEM POR TABELA",
        "-" * 80,
        f"{'Tabela':<36} {'SQLite':>12} {'Postgres':>12} {'Match':>8}",
        "-" * 80,
    ]
    for row in report.table_counts:
        m = "sim" if row.match else "NÃO"
        ls = f"{row.sqlite_rows:,}" if row.sqlite_rows is not None else "—"
        lp = f"{row.postgres_rows:,}" if row.postgres_rows is not None else "—"
        lines.append(f"{row.table:<36} {ls:>12} {lp:>12} {m:>8}")
    lines += [
        "",
        "2) VALORES FINANCEIROS (totais)",
        "",
        f"{'Métrica':<48} {'SQLite':>16} {'Postgres':>16} {'Match':>8}",
        "-" * 80,
    ]
    for m in report.financial_metrics:
        ok = "sim" if m.match else "NÃO"
        sv = f"{m.sqlite_value:.2f}" if m.sqlite_value is not None else "—"
        pv = f"{m.postgres_value:.2f}" if m.postgres_value is not None else "—"
        lines.append(f"{m.label:<48} {sv:>16} {pv:>16} {ok:>8}")
    lines += [
        "",
        "3) ENTIDADES PRINCIPAIS",
        "",
        f"{'Métrica':<48} {'SQLite':>16} {'Postgres':>16} {'Match':>8}",
        "-" * 80,
    ]
    for e in report.entity_metrics:
        ok = "sim" if e.match else "NÃO"
        sv = f"{e.sqlite_value:,}" if e.sqlite_value is not None else "—"
        pv = f"{e.postgres_value:,}" if e.postgres_value is not None else "—"
        lines.append(f"{e.label:<48} {sv:>16} {pv:>16} {ok:>8}")
    lines += [
        "",
        "=" * 80,
        f"RESULTADO GLOBAL: {'PARIDADE OK' if report.all_ok else 'EXISTEM DIVERGÊNCIAS'}",
        "=" * 80,
    ]
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Comparar SQLite e PostgreSQL (paridade).")
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=None,
        help="Caminho do ficheiro .db SQLite (defeito: DB_PATH da app)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Escrever relatório neste ficheiro (UTF-8).",
    )
    args = parser.parse_args()
    report = compare_sqlite_postgres(sqlite_path=args.sqlite)
    text = format_parity_report_text(report)
    print(text)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        _logger.info("Relatório escrito em %s", args.output)


if __name__ == "__main__":
    main()
