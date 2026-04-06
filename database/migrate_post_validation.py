"""Validação pós-migração SQLite × PostgreSQL (contagens, somas chave, IDs).

Compara origem SQLite (ficheiro) com destino Postgres (``DATABASE_URL`` / cadeia habitual).
Relatório linha-a-linha estilo: ``customers: OK (120 vs 120)``.

Uso::

    python -m database.migrate_post_validation --sqlite C:/path/business.db
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env", override=False)

from database.config import sqlite_db_path
from database.connection import get_postgres_conn
from database.migrate_sqlite_to_postgres import _MIGRATION_TABLE_ORDER
from database.sql_compat import is_sqlite_conn, qmarks_to_percent_s

_logger = logging.getLogger(__name__)

_FLOAT_TOL = 0.02

# tabela → lista de (rótulo, sql completo) — só avaliado se a tabela existir
_TABLE_SUM_RULES: dict[str, tuple[tuple[str, str], ...]] = {
    "sales": (
        ("Σ total", "SELECT COALESCE(SUM(total), 0) AS v FROM sales"),
        ("Σ qty", "SELECT COALESCE(SUM(quantity), 0) AS v FROM sales"),
        ("+Σ cogs", "SELECT COALESCE(SUM(cogs_total), 0) AS v FROM sales"),
    ),
    "products": (
        ("Σ stock", "SELECT COALESCE(SUM(stock), 0) AS v FROM products WHERE deleted_at IS NULL"),
        (
            "Σ stock*cost",
            "SELECT COALESCE(SUM(stock * cost), 0) AS v FROM products WHERE deleted_at IS NULL",
        ),
    ),
    "stock_cost_entries": (
        ("Σ total_entry_cost", "SELECT COALESCE(SUM(total_entry_cost), 0) AS v FROM stock_cost_entries"),
    ),
    "price_history": (
        ("Σ new_price", "SELECT COALESCE(SUM(new_price), 0) AS v FROM price_history"),
    ),
    "sku_master": (
        ("Σ total_stock", "SELECT COALESCE(SUM(total_stock), 0) AS v FROM sku_master WHERE deleted_at IS NULL"),
        (
            "Σ avg*soma",
            "SELECT COALESCE(SUM(avg_unit_cost * total_stock), 0) AS v FROM sku_master WHERE deleted_at IS NULL",
        ),
    ),
}


def _exec(conn: Any, sql: str, params: Sequence[Any] = ()) -> Any:
    sql_use = sql if is_sqlite_conn(conn) else qmarks_to_percent_s(sql)
    return conn.execute(sql_use, params)


def _scalar_count(conn: Any, table: str) -> int | None:
    try:
        cur = _exec(conn, f"SELECT COUNT(*) AS c FROM {table}", ())
        row = cur.fetchone()
        if row is None:
            return None
        v = row["c"] if isinstance(row, dict) else row[0]
        return int(v)
    except Exception as exc:
        _logger.debug("count %s: %s", table, exc)
        return None


def _scalar_float_v(conn: Any, sql: str) -> float | None:
    try:
        cur = _exec(conn, sql, ())
        row = cur.fetchone()
        if row is None:
            return None
        v = row["v"] if isinstance(row, dict) else row[0]
        return float(v) if v is not None else 0.0
    except Exception as exc:
        _logger.debug("float %s: %s", sql[:60], exc)
        return None


def _scalar_min_max_id(conn: Any, table: str) -> tuple[int | None, int | None]:
    try:
        cur = _exec(
            conn,
            f"SELECT MIN(id) AS lo, MAX(id) AS hi FROM {table}",
            (),
        )
        row = cur.fetchone()
        if row is None:
            return None, None
        if isinstance(row, dict):
            lo, hi = row.get("lo"), row.get("hi")
        else:
            lo, hi = row[0], row[1]
        if lo is None and hi is None:
            return None, None
        return int(lo) if lo is not None else None, int(hi) if hi is not None else None
    except Exception:
        return None, None


def _sqlite_has_table(conn: sqlite3.Connection, table: str) -> bool:
    r = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;",
        (table,),
    ).fetchone()
    return r is not None


def _pg_has_table(pg_conn: Any, table: str) -> bool:
    cur = pg_conn.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        LIMIT 1;
        """,
        (table.lower(),),
    )
    return cur.fetchone() is not None


def _float_match(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= _FLOAT_TOL


@dataclass
class TablePostMigrationRow:
    table: str
    sc: int | None
    pc: int | None
    count_ok: bool
    ids_detail: str
    sums_detail: str
    ok: bool


@dataclass
class PostMigrationReport:
    sqlite_path: str
    rows: list[TablePostMigrationRow] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(r.ok for r in self.rows)


def validate_post_migration(*, sqlite_path: Path | None = None) -> PostMigrationReport:
    env = (os.environ.get("ALIEH_MIGRATE_SQLITE") or "").strip()
    path = (
        sqlite_path
        if sqlite_path is not None
        else (Path(env).expanduser().resolve() if env else sqlite_db_path())
    )
    if not path.is_file():
        raise FileNotFoundError(f"SQLite não encontrado: {path}")

    report = PostMigrationReport(sqlite_path=str(path))
    s_conn = sqlite3.connect(str(path), timeout=60.0)
    s_conn.row_factory = sqlite3.Row

    try:
        with get_postgres_conn() as p_conn:
            for table in _MIGRATION_TABLE_ORDER:
                if not _sqlite_has_table(s_conn, table):
                    _logger.info("Validação: %s — omitida (sem tabela no SQLite)", table)
                    continue
                if not _pg_has_table(p_conn, table):
                    report.rows.append(
                        TablePostMigrationRow(
                            table=table,
                            sc=_scalar_count(s_conn, table),
                            pc=None,
                            count_ok=False,
                            ids_detail="postgres: sem tabela",
                            sums_detail="—",
                            ok=False,
                        )
                    )
                    continue

                sc = _scalar_count(s_conn, table)
                pc = _scalar_count(p_conn, table)
                count_ok = (
                    sc is not None
                    and pc is not None
                    and sc == pc
                )

                slo, shi = _scalar_min_max_id(s_conn, table)
                plo, phi = _scalar_min_max_id(p_conn, table)
                if slo is not None or shi is not None or plo is not None or phi is not None:
                    id_match = slo == plo and shi == phi
                    ids_detail = f"ids sqlite {slo}..{shi} | postgres {plo}..{phi}"
                    if not id_match:
                        ids_detail += " ✗"
                    else:
                        ids_detail += " ✓"
                else:
                    id_match = True
                    ids_detail = "ids n/a"

                sum_parts: list[str] = []
                sums_ok = True
                for label, sql in _TABLE_SUM_RULES.get(table, ()):
                    sv = _scalar_float_v(s_conn, sql)
                    pv = _scalar_float_v(p_conn, sql)
                    if sv is None and pv is None:
                        continue
                    sm = _float_match(sv, pv)
                    sums_ok = sums_ok and sm
                    sum_parts.append(
                        f"{label} {sv:.2f} vs {pv:.2f}{'' if sm else ' ✗'}"
                    )
                sums_detail = "; ".join(sum_parts) if sum_parts else "—"

                ok = count_ok and id_match and sums_ok
                report.rows.append(
                    TablePostMigrationRow(
                        table=table,
                        sc=sc,
                        pc=pc,
                        count_ok=count_ok,
                        ids_detail=ids_detail,
                        sums_detail=sums_detail,
                        ok=ok,
                    )
                )
    finally:
        s_conn.close()

    return report


def format_post_migration_report(report: PostMigrationReport) -> str:
    lines: list[str] = [
        "=" * 72,
        "RELATÓRIO — Validação pós-migração SQLite × PostgreSQL",
        "=" * 72,
        f"SQLite: {report.sqlite_path}",
        "",
    ]
    for r in report.rows:
        if r.sc is None:
            sc_txt = "?"
        else:
            sc_txt = str(r.sc)
        if r.pc is None:
            pc_txt = "?"
        else:
            pc_txt = str(r.pc)
        if r.ok:
            lines.append(f"{r.table}: OK ({sc_txt} vs {pc_txt})")
        else:
            lines.append(f"{r.table}: MISMATCH ({sc_txt} vs {pc_txt})")
        if r.ids_detail and r.ids_detail != "ids n/a":
            lines.append(f"    └ {r.ids_detail}")
        if r.sums_detail and r.sums_detail != "—":
            lines.append(f"    └ {r.sums_detail}")
    lines += [
        "",
        "=" * 72,
        f"RESULTADO GLOBAL: {'OK — migração consistente' if report.all_ok and report.rows else 'ATENÇÃO — rever linhas MISMATCH'}",
        "=" * 72,
    ]
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Validar migração SQLite → Postgres.")
    ap.add_argument("--sqlite", type=Path, default=None, help="Ficheiro .db origem")
    ap.add_argument("-o", "--output", type=Path, default=None, help="Guardar relatório UTF-8")
    args = ap.parse_args()
    rep = validate_post_migration(sqlite_path=args.sqlite)
    text = format_post_migration_report(rep)
    print(text)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        _logger.info("Relatório escrito em %s", args.output)


if __name__ == "__main__":
    main()
