"""
Rotina de recuperação de backup SQLite + validação pós-restauro.

Uso típico após falha:
  1. Copiar o ficheiro de backup (ex.: cópia manual de ``business.db`` ou download do Cloud)
     para um caminho temporário.
  2. ``restore_sqlite_from_backup(backup_path, target_path)`` — substitui a base activa
     de forma atómica (via ficheiro ``*.recover_tmp``).
  3. ``validate_restored_backup_set(db_path, audit_export_json=..., audit_log_path=...)``
     — integridade SQLite, opcionalmente alinhamento com export JSON de auditoria e
     verificação da cadeia em ``app.log``.

Não inicia Streamlit; seguro para scripts operacionais ou testes.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from database.db_errors import DB_DRIVER_ERRORS
from database.sqlite_tools import sqlite_connect_path

_SAFE_TABLE_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


@dataclass
class RecoveryValidationReport:
    """Resultado agregado da validação após restauro."""

    integrity_ok: bool = False
    integrity_errors: list[str] = field(default_factory=list)
    """Diferenças entre contagens no JSON de export e na BD restaurada."""
    export_row_mismatches: list[str] = field(default_factory=list)
    audit_log_ok: bool | None = None
    audit_log_errors: list[str] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        if not self.integrity_ok:
            return False
        if self.export_row_mismatches:
            return False
        if self.audit_log_ok is False:
            return False
        return True


def verify_sqlite_integrity(db_path: Path | str) -> tuple[bool, list[str]]:
    """
    ``PRAGMA integrity_check`` e ``PRAGMA foreign_key_check`` (SQLite 3.37+).

    Devolve (True, []) se tudo estiver coerente.
    """
    path = Path(db_path)
    errors: list[str] = []
    try:
        conn = sqlite_connect_path(path)
    except (ConnectionError, OSError) as exc:
        return False, [f"Não foi possível abrir a base: {exc}"]
    try:
        try:
            row = conn.execute("PRAGMA integrity_check;").fetchone()
        except DB_DRIVER_ERRORS as exc:
            return False, [f"Ficheiro corrompido ou não é SQLite: {exc}"]
        msg = str(row[0]) if row and row[0] is not None else ""
        if msg.lower() != "ok":
            errors.append(f"integrity_check: {msg or 'sem resultado'}")
        try:
            fk_rows = conn.execute("PRAGMA foreign_key_check;").fetchall()
        except DB_DRIVER_ERRORS as exc:
            errors.append(f"foreign_key_check indisponível: {exc}")
        else:
            if fk_rows:
                errors.append(
                    f"foreign_key_check: {len(fk_rows)} violação(ões) de chave estrangeira"
                )
    finally:
        conn.close()
    return len(errors) == 0, errors


def restore_sqlite_from_backup(backup_path: Path | str, target_path: Path | str) -> None:
    """
    Substitui ``target_path`` por uma cópia bit-a-bit de ``backup_path``.

    - Cria directório pai se necessário.
    - Escreve primeiro em ``<target>.recover_tmp`` e só depois ``replace`` atómico
      (no mesmo volume).

    **Windows:** é necessário que **nenhum** processo tenha o ficheiro de destino
    aberto (feche o Streamlit / scripts que usem ``get_db_conn()`` sobre esse caminho).
    """
    src = Path(backup_path).expanduser().resolve()
    dst = Path(target_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Ficheiro de backup não encontrado: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".recover_tmp")
    try:
        shutil.copy2(src, tmp)
        # Windows: ``Path.replace`` falha se o destino estiver bloqueado por outra
        # ligação SQLite; remover o destino antes de renomear o tmp.
        if sys.platform == "win32":
            if dst.is_file():
                dst.unlink()
            tmp.rename(dst)
        else:
            tmp.replace(dst)
    except BaseException:
        try:
            if tmp.is_file():
                tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def verify_export_row_counts_match_db(db_path: Path | str, export_json_path: Path | str) -> list[str]:
    """
    Compara o número de linhas gravadas no export periódico de auditoria (chave
    ``tables``) com ``SELECT COUNT(*)`` na base restaurada.

    Tabelas cujo valor em ``tables`` não é uma lista (ex.: erro de export) são ignoradas.
    Nomes de tabela só aceites se corresponderem a um identificador SQL seguro.
    """
    path = Path(db_path)
    raw = Path(export_json_path).read_text(encoding="utf-8")
    data = json.loads(raw)
    tables = data.get("tables") or {}
    mismatches: list[str] = []

    try:
        conn = sqlite_connect_path(path, row_factory=sqlite3.Row)
    except (ConnectionError, OSError) as exc:
        return [f"Não foi possível abrir a base: {exc}"]
    try:
        for name, rows in tables.items():
            if not _SAFE_TABLE_NAME.match(str(name)):
                mismatches.append(f"Tabela ignorada (nome inválido): {name!r}")
                continue
            if isinstance(rows, dict) and "error" in rows:
                continue
            if not isinstance(rows, list):
                continue
            try:
                cur = conn.execute(f"SELECT COUNT(*) AS n FROM {name};")
                n = int(cur.fetchone()["n"])
            except DB_DRIVER_ERRORS as exc:
                mismatches.append(f"{name}: consulta COUNT falhou — {exc}")
                continue
            if n != len(rows):
                mismatches.append(
                    f"{name}: export tem {len(rows)} linha(s), BD restaurada tem {n}"
                )
    finally:
        conn.close()
    return mismatches


def validate_restored_backup_set(
    db_path: Path | str,
    *,
    audit_export_json: Path | str | None = None,
    audit_log_path: Path | str | None = None,
) -> RecoveryValidationReport:
    """
    Executa verificações pós-restauro: integridade da BD, opcionalmente coerência com
    ``db_audit_*.json`` e ``verify_audit_log_file`` no ``app.log`` do mesmo conjunto
    de backup.
    """
    report = RecoveryValidationReport()
    ok, errs = verify_sqlite_integrity(db_path)
    report.integrity_ok = ok
    report.integrity_errors = errs

    if audit_export_json is not None:
        report.export_row_mismatches = verify_export_row_counts_match_db(
            db_path, audit_export_json
        )

    if audit_log_path is not None:
        from utils.critical_log import verify_audit_log_file

        al_ok, al_err = verify_audit_log_file(Path(audit_log_path))
        report.audit_log_ok = al_ok
        report.audit_log_errors = al_err
    else:
        report.audit_log_ok = None

    return report
