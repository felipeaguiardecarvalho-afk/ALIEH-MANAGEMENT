"""
Robustez do sistema de auditoria: verificação da cadeia, adulteração, continuidade
pós-restart (relê tail do disco) e backup periódico (sem tocar em ``logs/app.log`` real).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def no_hmac_chain(monkeypatch):
    """Garante SHA-256 simples (sem HMAC) para valores reprodutíveis nos testes."""
    monkeypatch.delenv("ALIEH_LOG_CHAIN_SECRET", raising=False)


def _build_audit_line(iso_ts: str, prev_full: str, payload: str, digest: str) -> str:
    prev_short = prev_full[:16] if len(prev_full) >= 16 else prev_full
    return f"{iso_ts} | audit_prev={prev_short} | audit_chain={digest} | {payload}\n"


def _make_two_line_valid_log(tmp: Path) -> Path:
    """Constrói ``app.log`` com duas entradas encadeadas (sem usar o logger)."""
    import utils.critical_log as cl

    log_path = tmp / "audit_chain.log"
    g = cl._GENESIS_PREV  # noqa: SLF001
    p1 = "action=t1 | user=u | user_id=1"
    d1 = cl._digest(g, p1)  # noqa: SLF001
    line1 = _build_audit_line("2026-01-01T10:00:00", g, p1, d1)
    p2 = "action=t2 | user=u | user_id=1"
    d2 = cl._digest(d1, p2)  # noqa: SLF001
    line2 = _build_audit_line("2026-01-01T10:00:01", d1, p2, d2)
    log_path.write_text(line1 + line2, encoding="utf-8")
    return log_path


def test_verify_audit_detects_tampered_payload(tmp_path):
    """Alteração manual ao payload quebra a verificação da cadeia."""
    import utils.critical_log as cl

    log_path = _make_two_line_valid_log(tmp_path)
    text = log_path.read_text(encoding="utf-8")
    # Corrompe a segunda linha (payload após o hash).
    corrupted = text.replace("action=t2", "action=t2_FORGED", 1)
    log_path.write_text(corrupted, encoding="utf-8")

    ok, errors = cl.verify_audit_log_file(log_path)
    assert ok is False
    assert any("cadeia quebrada" in e for e in errors)


def test_verify_audit_detects_tampered_hash(tmp_path):
    """Alteração de um dígito do ``audit_chain`` falha."""
    import utils.critical_log as cl

    log_path = _make_two_line_valid_log(tmp_path)
    text = log_path.read_text(encoding="utf-8")
    # Substitui primeiro hex de audit_chain na segunda linha.
    lines = text.splitlines(keepends=True)
    assert len(lines) >= 2
    ln = lines[1]
    idx = ln.lower().find("audit_chain=")
    assert idx != -1
    start = idx + len("audit_chain=")
    # troca o primeiro caractere hex
    old_c = ln[start]
    new_c = "0" if old_c != "0" else "1"
    ln2 = ln[:start] + new_c + ln[start + 1 :]
    lines[1] = ln2
    log_path.write_text("".join(lines), encoding="utf-8")

    ok, errors = cl.verify_audit_log_file(log_path)
    assert ok is False
    assert errors


def test_chain_continuity_after_simulated_restart(tmp_path, monkeypatch):
    """
    Após reset da memória do processo, o próximo evento usa o último ``audit_chain``
    lido do disco (comportamento pós-restart).
    """
    import utils.critical_log as cl

    log_path = tmp_path / "restart.log"
    monkeypatch.setattr(cl, "_DEFAULT_LOG_FILE", log_path)
    monkeypatch.setattr(cl, "_LOG_DIR", tmp_path)

    # Estado inicial: ficheiro com uma linha válida.
    g = cl._GENESIS_PREV  # noqa: SLF001
    p1 = "action=before | user=u | user_id=1"
    d1 = cl._digest(g, p1)  # noqa: SLF001
    log_path.write_text(
        _build_audit_line("2026-02-01T12:00:00", g, p1, d1), encoding="utf-8"
    )

    # Simula novo processo: sem handlers presos e tail não carregado.
    cl._logger.handlers.clear()  # noqa: SLF001
    cl._chain_tail_initialized = False  # noqa: SLF001
    cl._chain_prev_in_memory = g  # noqa: SLF001

    monkeypatch.setattr(cl, "get_audit_session_user", lambda: "tester")
    monkeypatch.setattr(cl, "get_audit_session_user_id", lambda: "99")
    monkeypatch.setattr(cl, "forward_critical_audit_event", lambda **kwargs: None)

    cl.log_critical_event("after_restart", note="ok")

    ok, errors = cl.verify_audit_log_file(log_path)
    assert ok is True, errors
    lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    assert "after_restart" in lines[-1]


def test_periodic_audit_backup_creates_artifacts_and_respects_interval(
    tmp_path, monkeypatch
):
    """Primeira execução gera cópia do log + JSON; segunda dentro do intervalo não duplica."""
    import utils.audit_backup as ab

    backup_dir = tmp_path / "backups"
    src_log = tmp_path / "src_app.log"
    src_log.write_text(
        "2026-03-01T00:00:00 | audit_prev=abcd | audit_chain=" + "a" * 64 + " | action=x\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(ab, "_is_backup_disabled", lambda: False)
    monkeypatch.setattr(ab, "_config_backup_dir", lambda: backup_dir)
    monkeypatch.setattr(ab, "_config_interval_seconds", lambda: 86_400)
    monkeypatch.setattr(ab, "critical_audit_log_path", lambda: src_log)
    monkeypatch.setattr(
        ab,
        "export_audit_db_payload",
        lambda: {
            "exported_at": "2026-03-01T00:00:00+00:00",
            "database_path": str(tmp_path / "db.sqlite"),
            "tables": {"_test": []},
        },
    )
    monkeypatch.setattr(ab, "forward_audit_snapshot", lambda **kwargs: None)

    ab.maybe_run_periodic_audit_backup()

    json_files = list(backup_dir.glob("db_audit_*.json"))
    log_copies = list(backup_dir.glob("app_*.log"))
    assert len(json_files) == 1
    assert len(log_copies) == 1
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["tables"]["_test"] == []
    state_p = backup_dir / ".audit_backup_state.json"
    assert state_p.is_file()
    state = json.loads(state_p.read_text(encoding="utf-8"))
    assert "last_success_unix" in state
    assert "last_error" not in state or state.get("last_error") is None

    ab.maybe_run_periodic_audit_backup()
    assert len(list(backup_dir.glob("db_audit_*.json"))) == 1
    assert len(list(backup_dir.glob("app_*.log"))) == 1


def test_sqlite_full_backup_creates_timestamped_file_and_prunes(tmp_path, monkeypatch):
    import utils.audit_backup as ab

    db_src = tmp_path / "live.db"
    db_src.parent.mkdir(parents=True, exist_ok=True)
    conn = __import__("sqlite3").connect(str(db_src))
    conn.execute("CREATE TABLE x (i INTEGER);")
    conn.commit()
    conn.close()

    backup_root = tmp_path / "db_backups"
    monkeypatch.setattr(ab, "DB_PATH", db_src)
    monkeypatch.setattr(ab, "get_db_provider", lambda: "sqlite")
    monkeypatch.setattr(ab, "_is_sqlite_full_backup_disabled", lambda: False)
    monkeypatch.setattr(ab, "_config_sqlite_full_backup_dir", lambda: backup_root)
    monkeypatch.setattr(ab, "_config_sqlite_full_backup_keep", lambda: 2)

    assert ab.run_sqlite_full_backup(reason="test")
    files = sorted(backup_root.glob("business_*.db"))
    assert len(files) == 1
    assert files[0].stat().st_size > 0

    import time

    time.sleep(0.15)
    assert ab.run_sqlite_full_backup(reason="test2")
    time.sleep(0.15)
    assert ab.run_sqlite_full_backup(reason="test3")
    files2 = sorted(backup_root.glob("business_*.db"))
    assert len(files2) <= 2


def test_periodic_audit_backup_skipped_when_disabled(tmp_path, monkeypatch):
    import utils.audit_backup as ab

    backup_dir = tmp_path / "never_created"
    monkeypatch.setattr(ab, "_is_backup_disabled", lambda: True)
    monkeypatch.setattr(ab, "_config_backup_dir", lambda: backup_dir)
    ab.maybe_run_periodic_audit_backup()
    assert not backup_dir.exists()


def test_verify_empty_or_missing_file_is_ok(tmp_path):
    import utils.critical_log as cl

    ok, errors = cl.verify_audit_log_file(tmp_path / "nosuch.log")
    assert ok is True and errors == []

    p = tmp_path / "empty.log"
    p.write_text("", encoding="utf-8")
    ok2, err2 = cl.verify_audit_log_file(p)
    assert ok2 is True and err2 == []
