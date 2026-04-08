"""Cópias periódicas de auditoria e backup completo do SQLite.

**Auditoria** (ficheiro `app.log` + tabelas relevantes em JSON):

- Pasta por defeito: ``<raiz do projeto>/audit_backups/`` (configurável).
- Espelho opcional: segunda cópia para outro caminho (SO ou segredos Streamlit).
- Intervalo por defeito: 24 h (``ALIEH_AUDIT_BACKUP_INTERVAL_SECONDS``).

**SQLite completo** (ficheiro da BD em uso → cópia consistente via ``backup()`` API):

- Pasta por defeito: ``/backups/db_backups/`` quando gravável; senão
  ``<repo>/.alieh_data/db_backups/`` ou ``$TMP/alieh_db_backups/`` (ex.: Streamlit Cloud).
  Nome ``business_YYYYMMDD_HHMM.db``.
- Arranque (thread), intervalo (``ALIEH_SQLITE_BACKUP_INTERVAL_SECONDS``, defeito 1 h),
  encerramento do processo (``atexit``, síncrono best-effort).
- Retenção: últimos N ficheiros (``ALIEH_SQLITE_BACKUP_KEEP``, defeito 20).

Falhas são registadas em log e **não** interrompem a aplicação.
"""

from __future__ import annotations

import atexit
import errno
import gc
import json
import logging
import os
import shutil
import stat
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from database.audit_table_export import export_audit_db_payload
from database.config import get_db_provider
from database.connection import DB_PATH
from database.sqlite_tools import sqlite_backup_file_to_file
from utils.audit_remote_sink import forward_audit_snapshot
from utils.critical_log import critical_audit_log_path
from utils.env_safe import STREAMLIT_CONFIG_READ_ERRORS

_logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INTERVAL_S = 86400
_STATE_NAME = ".audit_backup_state.json"

# --- Backup completo SQLite (ficheiro .db) ---
_STATE_SQLITE_FULL = ".sqlite_full_backup_state.json"
_DEFAULT_SQLITE_BACKUP_INTERVAL_S = 3600
_DEFAULT_SQLITE_BACKUP_KEEP = 20

_sqlite_startup_backup_scheduled = False
_sqlite_atexit_registered = False
_periodic_sqlite_thread: threading.Thread | None = None
_periodic_sqlite_lock = threading.Lock()
_sqlite_full_backup_lock = threading.Lock()


def _secrets_get(key: str) -> str | None:
    try:
        v = st.secrets.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    except STREAMLIT_CONFIG_READ_ERRORS:
        pass
    return None


def _config_interval_seconds() -> int:
    raw = (os.environ.get("ALIEH_AUDIT_BACKUP_INTERVAL_SECONDS") or "").strip()
    if not raw:
        raw = _secrets_get("alieh_audit_backup_interval_seconds") or ""
    try:
        n = int(raw) if raw else _DEFAULT_INTERVAL_S
    except ValueError:
        n = _DEFAULT_INTERVAL_S
    return max(60, n) if n > 0 else _DEFAULT_INTERVAL_S


def _config_backup_dir() -> Path:
    env = (os.environ.get("ALIEH_AUDIT_BACKUP_DIR") or "").strip()
    if env:
        return Path(env).expanduser()
    sec = _secrets_get("alieh_audit_backup_dir")
    if sec:
        return Path(sec).expanduser()
    return _REPO_ROOT / "audit_backups"


def _config_export_dir() -> Path | None:
    env = (os.environ.get("ALIEH_AUDIT_EXPORT_DIR") or "").strip()
    if env:
        return Path(env).expanduser()
    sec = _secrets_get("alieh_audit_export_dir")
    if sec:
        return Path(sec).expanduser()
    return None


def _is_backup_disabled() -> bool:
    v = (os.environ.get("ALIEH_AUDIT_BACKUP_DISABLED") or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    try:
        v2 = st.secrets.get("alieh_audit_backup_disabled")
        if v2 is not None and str(v2).strip().lower() in ("1", "true", "yes", "on"):
            return True
    except STREAMLIT_CONFIG_READ_ERRORS:
        pass
    return False


def _resolve_default_sqlite_full_backup_dir() -> Path:
    """Prefer ``/backups/db_backups`` (Docker); senão caminho gravável no host (nuvem)."""
    primary = Path("/backups/db_backups")
    try:
        primary.mkdir(parents=True, exist_ok=True)
        return primary
    except (PermissionError, OSError):
        pass
    local = _REPO_ROOT / ".alieh_data" / "db_backups"
    try:
        local.mkdir(parents=True, exist_ok=True)
        return local
    except (PermissionError, OSError):
        pass
    fallback = Path(tempfile.gettempdir()) / "alieh_db_backups"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _config_sqlite_full_backup_dir() -> Path:
    env = (os.environ.get("ALIEH_SQLITE_BACKUP_DIR") or "").strip()
    if env:
        return Path(env).expanduser()
    sec = _secrets_get("alieh_sqlite_backup_dir")
    if sec:
        return Path(sec).expanduser()
    return _resolve_default_sqlite_full_backup_dir()


def _config_sqlite_full_backup_interval_seconds() -> int:
    raw = (os.environ.get("ALIEH_SQLITE_BACKUP_INTERVAL_SECONDS") or "").strip()
    if not raw:
        raw = _secrets_get("alieh_sqlite_backup_interval_seconds") or ""
    try:
        n = int(raw) if raw else _DEFAULT_SQLITE_BACKUP_INTERVAL_S
    except ValueError:
        n = _DEFAULT_SQLITE_BACKUP_INTERVAL_S
    return max(60, n) if n > 0 else _DEFAULT_SQLITE_BACKUP_INTERVAL_S


def _config_sqlite_full_backup_keep() -> int:
    raw = (os.environ.get("ALIEH_SQLITE_BACKUP_KEEP") or "").strip()
    if not raw:
        raw = _secrets_get("alieh_sqlite_backup_keep") or ""
    try:
        n = int(raw) if raw else _DEFAULT_SQLITE_BACKUP_KEEP
    except ValueError:
        n = _DEFAULT_SQLITE_BACKUP_KEEP
    return max(1, min(n, 500))


def _is_sqlite_full_backup_disabled() -> bool:
    v = (os.environ.get("ALIEH_SQLITE_BACKUP_DISABLED") or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    try:
        v2 = st.secrets.get("alieh_sqlite_backup_disabled")
        if v2 is not None and str(v2).strip().lower() in ("1", "true", "yes", "on"):
            return True
    except STREAMLIT_CONFIG_READ_ERRORS:
        pass
    return False


def _read_sqlite_full_state(backup_dir: Path) -> dict[str, Any]:
    p = backup_dir / _STATE_SQLITE_FULL
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_sqlite_full_state(backup_dir: Path, state: dict[str, Any]) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    p = backup_dir / _STATE_SQLITE_FULL
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=0, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _allocate_sqlite_backup_dest(backup_dir: Path) -> Path:
    stem = datetime.now().strftime("business_%Y%m%d_%H%M")
    path = backup_dir / f"{stem}.db"
    if not path.exists():
        return path
    n = 1
    while True:
        alt = backup_dir / f"{stem}_{n}.db"
        if not alt.exists():
            return alt
        n += 1


def _prune_sqlite_full_backups(backup_dir: Path, keep: int) -> None:
    try:
        files = sorted(
            [p for p in backup_dir.glob("business_*.db") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    for old in files[keep:]:
        for attempt in range(5):
            try:
                try:
                    os.chmod(
                        old,
                        stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH,
                    )
                except OSError:
                    pass
                old.unlink()
                _logger.debug("Removed old SQLite backup: %s", old)
                break
            except OSError as exc:
                busy = getattr(exc, "winerror", None) in (32, 5) or exc.errno in (
                    errno.EACCES,
                    errno.EPERM,
                )
                if busy and attempt < 4:
                    gc.collect()
                    time.sleep(0.08 * (attempt + 1))
                    continue
                _logger.warning("Could not remove old SQLite backup %s: %s", old, exc)
                break


def run_sqlite_full_backup(*, reason: str = "") -> bool:
    """
    Cópia consistente do ficheiro SQLite activo (API ``backup()``).
    Não bloqueia outros módulos excepto durante a própria operação.
    """
    if get_db_provider() != "sqlite":
        return False
    if _is_sqlite_full_backup_disabled():
        _logger.debug("SQLite full backup skipped (disabled).")
        return False
    if not DB_PATH.is_file():
        _logger.debug("SQLite full backup skipped: file not found (%s).", DB_PATH)
        return False

    backup_dir = _config_sqlite_full_backup_dir()
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _logger.warning("SQLite full backup: cannot create directory %s: %s", backup_dir, exc)
        return False

    dest = _allocate_sqlite_backup_dest(backup_dir)
    try:
        with _sqlite_full_backup_lock:
            sqlite_backup_file_to_file(DB_PATH, dest)
    except (ConnectionError, OSError) as exc:
        _logger.warning(
            "SQLite full backup failed (%s): %s",
            reason or "—",
            exc,
            exc_info=True,
        )
        try:
            if dest.is_file():
                dest.unlink(missing_ok=True)  # type: ignore[arg-type]
        except OSError:
            pass
        return False

    try:
        _best_effort_readonly(dest)
    except OSError:
        pass

    try:
        _prune_sqlite_full_backups(backup_dir, _config_sqlite_full_backup_keep())
    except Exception:
        _logger.debug("SQLite backup prune failed.", exc_info=True)

    try:
        _resolved = dest.resolve()
    except OSError:
        _resolved = dest
    _logger.info("SQLite full backup ok (%s) -> %s", reason or "—", _resolved)
    return True


def schedule_sqlite_full_backup(reason: str) -> None:
    """Executa :func:`run_sqlite_full_backup` num thread daemon (não bloqueia a UI)."""

    def _run() -> None:
        try:
            run_sqlite_full_backup(reason=reason)
        except Exception:
            _logger.warning("SQLite full backup thread crashed (%s).", reason, exc_info=True)

    t = threading.Thread(target=_run, daemon=True, name=f"sqlite-backup-{reason}")
    t.start()


def register_sqlite_full_backup_atexit() -> None:
    """Antes de encerrar o processo, tenta um backup síncrono (best-effort)."""

    global _sqlite_atexit_registered
    if _sqlite_atexit_registered:
        return
    if get_db_provider() != "sqlite":
        return
    _sqlite_atexit_registered = True

    def _on_exit() -> None:
        try:
            run_sqlite_full_backup(reason="shutdown")
        except Exception:
            _logger.debug("SQLite shutdown backup failed.", exc_info=True)

    atexit.register(_on_exit)


def maybe_run_periodic_sqlite_full_backup() -> None:
    """
    Se passou o intervalo desde o último sucesso, agenda backup completo em background.
    Evita vários threads em simultâneo.
    """
    if get_db_provider() != "sqlite":
        return
    if _is_sqlite_full_backup_disabled():
        return

    backup_dir = _config_sqlite_full_backup_dir()
    interval = _config_sqlite_full_backup_interval_seconds()
    now = time.time()

    with _periodic_sqlite_lock:
        global _periodic_sqlite_thread
        thr = _periodic_sqlite_thread
        if thr is not None and thr.is_alive():
            return

        state = _read_sqlite_full_state(backup_dir)
        last_ok = float(state.get("last_success_unix", 0) or 0)
        if last_ok > 0 and (now - last_ok) < interval:
            return

        def _job() -> None:
            global _periodic_sqlite_thread
            now2 = time.time()
            try:
                ok = run_sqlite_full_backup(reason="periodic")
                st2 = _read_sqlite_full_state(backup_dir)
                if ok:
                    st2["last_success_unix"] = now2
                    st2.pop("last_error", None)
                else:
                    st2["last_error"] = "backup_failed"
                    st2["last_error_unix"] = now2
                try:
                    _write_sqlite_full_state(backup_dir, st2)
                except OSError as wexc:
                    _logger.warning("Could not write SQLite backup state: %s", wexc)
            finally:
                with _periodic_sqlite_lock:
                    _periodic_sqlite_thread = None

        _periodic_sqlite_thread = threading.Thread(
            target=_job,
            daemon=True,
            name="sqlite-full-backup-periodic",
        )
        _periodic_sqlite_thread.start()


def run_startup_sqlite_full_backup_once() -> None:
    """Um backup ao arranque do processo (primeira chamada, em thread)."""
    global _sqlite_startup_backup_scheduled
    if _sqlite_startup_backup_scheduled:
        return
    if get_db_provider() != "sqlite":
        return
    if _is_sqlite_full_backup_disabled():
        return
    _sqlite_startup_backup_scheduled = True

    def _run() -> None:
        try:
            ok = run_sqlite_full_backup(reason="startup")
            if not ok:
                return
            try:
                backup_dir = _config_sqlite_full_backup_dir()
                state = _read_sqlite_full_state(backup_dir)
                state["last_success_unix"] = time.time()
                state["last_startup_backup_unix"] = state["last_success_unix"]
                state.pop("last_error", None)
                _write_sqlite_full_state(backup_dir, state)
            except OSError:
                pass
        except Exception:
            _logger.warning("SQLite full backup thread crashed (startup).", exc_info=True)

    threading.Thread(target=_run, daemon=True, name="sqlite-backup-startup").start()


def _read_state(backup_dir: Path) -> dict[str, Any]:
    p = backup_dir / _STATE_NAME
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(backup_dir: Path, state: dict[str, Any]) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    p = backup_dir / _STATE_NAME
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=0, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _best_effort_readonly(path: Path) -> None:
    try:
        mode = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
        os.chmod(path, mode)
    except OSError:
        pass


def _mirror_files(paths: list[Path], dest_dir: Path | None) -> None:
    if not dest_dir or not paths:
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in paths:
        if not src.is_file():
            continue
        target = dest_dir / src.name
        try:
            shutil.copy2(src, target)
            _best_effort_readonly(target)
        except OSError as exc:
            _logger.warning("Audit export mirror failed for %s: %s", src, exc)


def maybe_run_periodic_audit_backup() -> None:
    """
    Executa cópia se tiver passado o intervalo desde a última tentativa bem-sucedida.
    Chamado no arranque da app (após ``init_db``).
    """
    if _is_backup_disabled():
        return

    backup_dir = _config_backup_dir()
    interval = _config_interval_seconds()
    state = _read_state(backup_dir)
    last_ok = float(state.get("last_success_unix", 0) or 0)
    now = time.time()
    if last_ok > 0 and (now - last_ok) < interval:
        return

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    created: list[Path] = []

    try:
        log_src = critical_audit_log_path()
        if log_src.is_file():
            dest_log = backup_dir / f"app_{stamp}.log"
            shutil.copy2(log_src, dest_log)
            _best_effort_readonly(dest_log)
            created.append(dest_log)

        db_payload = export_audit_db_payload()
        db_dest = backup_dir / f"db_audit_{stamp}.json"
        db_dest.write_text(
            json.dumps(db_payload, default=str, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _best_effort_readonly(db_dest)
        created.append(db_dest)

        exp = _config_export_dir()
        _mirror_files(created, exp)

        state["last_success_unix"] = now
        state["last_backup_stamp"] = stamp
        state.pop("last_error", None)
        _write_state(backup_dir, state)

        try:
            forward_audit_snapshot(
                backup_stamp=stamp,
                db_export=db_payload,
                backup_file_paths=[str(p) for p in created],
            )
        except Exception:
            _logger.debug("Audit snapshot webhook scheduling failed.", exc_info=True)
    except OSError as exc:
        _logger.warning("Periodic audit backup failed: %s", exc, exc_info=True)
        state["last_error"] = str(exc)
        state["last_error_unix"] = now
        try:
            _write_state(backup_dir, state)
        except OSError:
            pass


def maybe_run_periodic_maintenance_backups() -> None:
    """
    Rotina única no arranque: cópias de auditoria (log + JSON) e agendamento do backup
    binário SQLite. Erros isolados não interrompem a app.
    """
    try:
        maybe_run_periodic_audit_backup()
    except Exception:
        _logger.warning("Periodic audit backup raised unexpectedly.", exc_info=True)
    try:
        maybe_run_periodic_sqlite_full_backup()
    except Exception:
        _logger.warning("Periodic SQLite full backup scheduler raised unexpectedly.", exc_info=True)
