"""
Exportação completa do SQLite para ficheiros JSON/CSV (migração PostgreSQL / Supabase).

- Descobre todas as tabelas de utilizador (`sqlite_master`).
- Preserva nomes de colunas, tipos textuais e valores; `tenant_id` e chaves primárias
  saem tal como na base (ids originais).
- Grava em ``/backups/export/<carimbo>/`` por defeito (evita sobrescritas).

Nota: a ordem sugerida no ``manifest.json`` ajuda a importar com FKs; em Postgres pode ser
necessário ``SET session_replication_role = replica`` ou import em transacção com FKs
adiadas, conforme o seu pipeline.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from database.config import get_db_provider
from database.connection import DB_PATH, get_db_conn
from utils.env_safe import STREAMLIT_CONFIG_READ_ERRORS

_logger = logging.getLogger(__name__)

DEFAULT_EXPORT_ROOT = Path("/backups/export")


def _default_export_root() -> Path:
    raw = (os.environ.get("ALIEH_SQLITE_EXPORT_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser()
    try:
        import streamlit as st

        sec = st.secrets.get("alieh_sqlite_export_root")
        if sec is not None and str(sec).strip():
            return Path(str(sec).strip()).expanduser()
    except STREAMLIT_CONFIG_READ_ERRORS:
        pass
    return DEFAULT_EXPORT_ROOT

# Ordem indicativa para import com dependências (tabelas conhecidas primeiro; resto A–Z).
_PREFERRED_TABLE_ORDER: tuple[str, ...] = (
    "app_schema_migrations",
    "sku_sequence_counter",
    "customer_sequence_counter",
    "sale_sequence_counter",
    "users",
    "customers",
    "sku_master",
    "products",
    "sku_cost_components",
    "stock_cost_entries",
    "sku_pricing_records",
    "sales",
    "price_history",
    "login_user_throttle",
    "login_attempt_audit",
    "sku_deletion_audit",
    "uat_manual_checklist",
)


def _list_user_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name;
        """
    ).fetchall()
    return [str(r[0]) for r in rows]


def _order_tables(names: list[str]) -> list[str]:
    pref_set = set(_PREFERRED_TABLE_ORDER)
    preferred = [t for t in _PREFERRED_TABLE_ORDER if t in names]
    rest = sorted(n for n in names if n not in pref_set)
    return preferred + rest


def _cell_to_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"__bytes_b64": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _row_to_dict(description: list[tuple], row: sqlite3.Row) -> dict[str, Any]:
    cols = [d[0] for d in description]
    return {cols[i]: _cell_to_json(row[i]) for i in range(len(cols))}


def export_all_data(
    export_root: Path | None = None,
    *,
    include_json: bool = True,
    include_csv: bool = True,
    subdir_with_timestamp: bool = True,
) -> Path:
    """
    Exporta todas as tabelas SQLite para ``export_root``.

    :returns: directório criado (ex.: ``/backups/export/export_20260104_120000``).
    :raises RuntimeError: se ``DB_PROVIDER`` não for ``sqlite``.
    """
    if get_db_provider() != "sqlite":
        raise RuntimeError(
            "export_all_data() apenas suporta fonte SQLite. "
            "Use DB_PROVIDER=sqlite ou exporte a partir da instância com ficheiro .db."
        )

    root = Path(export_root) if export_root is not None else _default_export_root()
    if subdir_with_timestamp:
        stamp = datetime.now(timezone.utc).strftime("export_%Y%m%d_%H%M%S")
        out_dir = root / stamp
    else:
        out_dir = root

    out_dir.mkdir(parents=True, exist_ok=True)

    tables_info: list[dict[str, Any]] = []
    table_names: list[str] = []

    with get_db_conn() as conn:
        names = _list_user_tables(conn)
        ordered = _order_tables(names)
        sqlite_version = conn.execute("SELECT sqlite_version();").fetchone()[0]

        for table in ordered:
            cur = conn.execute(f'SELECT * FROM "{table}";')
            description = list(cur.description or [])
            rows_raw = cur.fetchall()
            rows = [_row_to_dict(description, r) for r in rows_raw]
            col_names = [d[0] for d in description]

            entry: dict[str, Any] = {
                "table": table,
                "row_count": len(rows),
                "columns": col_names,
                "primary_keys_sqlite": [],  # preenchido abaixo quando existir
                "files": {},
            }

            # ROWID tables: informação limitada; PK explícitas via pragma
            try:
                pk_rows = conn.execute(f'PRAGMA table_info("{table}");').fetchall()
                entry["primary_keys_sqlite"] = [
                    str(p[1])
                    for p in pk_rows
                    if len(p) >= 6 and int(p[5] or 0) > 0
                ]
            except (sqlite3.Error, IndexError, TypeError, ValueError):
                pass

            safe_name = table.replace("/", "_").replace("\\", "_")

            if include_json:
                json_path = out_dir / f"{safe_name}.json"
                payload = {
                    "table": table,
                    "columns": col_names,
                    "rows": rows,
                }
                json_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                entry["files"]["json"] = json_path.name

            if include_csv and col_names:
                csv_path = out_dir / f"{safe_name}.csv"
                buf = io.StringIO(newline="")
                w = csv.DictWriter(buf, fieldnames=col_names, extrasaction="ignore")
                w.writeheader()
                for r in rows:
                    flat = {
                        k: (
                            json.dumps(v, ensure_ascii=False)
                            if isinstance(v, (dict, list))
                            else v
                        )
                        for k, v in r.items()
                    }
                    w.writerow(flat)
                csv_path.write_text(buf.getvalue(), encoding="utf-8")
                entry["files"]["csv"] = csv_path.name
            elif include_csv and not col_names:
                entry["files"]["csv"] = None

            tables_info.append(entry)
            table_names.append(table)

    try:
        db_path_resolved = str(DB_PATH.resolve())
    except OSError:
        db_path_resolved = str(DB_PATH)

    manifest = {
        "export_format_version": 1,
        "exported_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": {
            "engine": "sqlite",
            "sqlite_version": sqlite_version,
            "database_path": db_path_resolved,
            "note": "IDs e tenant_id são os valores originais da base SQLite.",
        },
        "target_hints": {
            "postgresql": {
                "encoding": "UTF-8",
                "suggested_import_order": table_names,
                "csv_note": "Células JSON (ex.: blobs codificados) vêm como texto JSON na coluna CSV.",
            },
        },
        "tables": tables_info,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    _logger.info("SQLite export completo: %s (%s tabelas)", out_dir, len(tables_info))
    return out_dir


def export_all_data_safe(
    export_root: Path | None = None,
    **kwargs: Any,
) -> Path | None:
    """
    Como :func:`export_all_data`, mas não propaga excepções (útil em UI / jobs).
    """
    try:
        return export_all_data(export_root, **kwargs)
    except Exception:
        _logger.exception("export_all_data_safe falhou")
        return None
