"""
Testes da rotina de recuperação de backup: restauro SQLite, integridade,
coerência com export JSON de auditoria e verificação da cadeia em ``app.log``.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime

import pytest

from database import connection as connection_mod
from utils import backup_recovery as br
from utils import critical_log as cl


TENANT = "default"


def _seed_one_customer(conn: sqlite3.Connection) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO customers (
            tenant_id, customer_code, name, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?);
        """,
        (TENANT, "C90001", "Cliente backup-test", now, now),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _count_customers(conn: sqlite3.Connection) -> int:
    r = conn.execute(
        "SELECT COUNT(*) FROM customers WHERE tenant_id = ?;",
        (TENANT,),
    ).fetchone()
    return int(r[0])


def _make_valid_audit_log_line() -> str:
    g = cl._GENESIS_PREV  # noqa: SLF001
    p1 = "action=backup_marker | user=u | user_id=1"
    d1 = cl._digest(g, p1)  # noqa: SLF001
    prev_short = g[:16]
    return (
        f"2026-04-01T00:00:00 | audit_prev={prev_short} | audit_chain={d1} | {p1}\n"
    )


@pytest.fixture
def recovery_env(tmp_path, monkeypatch):
    """Base isolada + ficheiro de log de auditoria no mesmo diretório (pacote de backup)."""
    monkeypatch.setenv("DB_PROVIDER", "sqlite")
    db = tmp_path / "live.db"
    monkeypatch.setattr(connection_mod, "DB_PATH", db)
    from database.init_db import init_db

    init_db()
    log_path = tmp_path / "app.log"
    monkeypatch.setattr(cl, "_DEFAULT_LOG_FILE", log_path)
    monkeypatch.setattr(cl, "_LOG_DIR", tmp_path)
    cl._logger.handlers.clear()  # noqa: SLF001
    cl._chain_tail_initialized = False  # noqa: SLF001
    cl._chain_prev_in_memory = cl._GENESIS_PREV  # noqa: SLF001

    with connection_mod.get_db_conn() as conn:
        _seed_one_customer(conn)

    log_path.write_text(_make_valid_audit_log_line(), encoding="utf-8")

    bundle = tmp_path / "backup_bundle"
    bundle.mkdir()
    backup_db = bundle / "business.db.bak"
    backup_log = bundle / "app.log.bak"
    shutil.copy2(db, backup_db)
    shutil.copy2(log_path, backup_log)

    counts = {}
    with sqlite3.connect(db) as conn:
        counts["customers"] = _count_customers(conn)

    yield {
        "db": db,
        "log": log_path,
        "backup_db": backup_db,
        "backup_log": backup_log,
        "bundle": bundle,
        "counts": counts,
    }


def test_restore_after_data_loss_integrity_and_counts(recovery_env, tmp_path):
    """Simula perda de dados na base activa e valida restauro a partir do backup."""
    db = recovery_env["db"]
    backup_db = recovery_env["backup_db"]
    backup_log = recovery_env["backup_log"]

    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM customers;")
        conn.commit()
    with sqlite3.connect(db) as c0:
        assert _count_customers(c0) == 0

    # Restaura para um ficheiro novo: no Windows o ``live.db`` pode permanecer
    # referenciado após ``init_db``/testes; em produção feche a app antes de
    # substituir o ficheiro da base.
    restored = tmp_path / "restored_live.db"
    br.restore_sqlite_from_backup(backup_db, restored)

    ok, errs = br.verify_sqlite_integrity(restored)
    assert ok is True, errs
    with sqlite3.connect(restored) as conn:
        assert _count_customers(conn) == recovery_env["counts"]["customers"]

    report = br.validate_restored_backup_set(
        restored, audit_log_path=backup_log
    )
    assert report.integrity_ok
    assert report.audit_log_ok is True
    assert report.all_ok


def test_validate_export_json_row_counts(recovery_env, tmp_path):
    """Export JSON do mesmo estado do backup deve alinhar contagens após restauro."""
    db = recovery_env["db"]
    backup_db = recovery_env["backup_db"]
    export_path = tmp_path / "db_audit_snapshot.json"

    with sqlite3.connect(backup_db) as conn:
        n_cust = conn.execute("SELECT COUNT(*) FROM customers;").fetchone()[0]

    export_path.write_text(
        json.dumps(
            {
                "exported_at": "2026-04-01T00:00:00+00:00",
                "database_path": str(backup_db),
                "tables": {
                    "customers": [{}] * int(n_cust),
                    "products": [],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    restored = tmp_path / "restored_for_export.db"
    br.restore_sqlite_from_backup(backup_db, restored)
    mm = br.verify_export_row_counts_match_db(restored, export_path)
    assert mm == []

    export_bad = tmp_path / "db_audit_bad.json"
    export_bad.write_text(
        json.dumps({"tables": {"customers": []}}),
        encoding="utf-8",
    )
    mm2 = br.verify_export_row_counts_match_db(restored, export_bad)
    assert mm2 and any("customers" in m for m in mm2)


def test_restore_missing_backup_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        br.restore_sqlite_from_backup(tmp_path / "nonexistent.db", tmp_path / "target.db")


def test_verify_integrity_detects_corrupt_db(tmp_path):
    p = tmp_path / "bad.db"
    p.write_bytes(b"not sqlite")
    ok, errs = br.verify_sqlite_integrity(p)
    assert ok is False
    assert errs
