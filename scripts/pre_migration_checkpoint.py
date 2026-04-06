"""
Checkpoint de segurança antes de migração (SQLite / testes / cópia da BD / registo).

Requisitos cumpridos:
  - Exige ``DB_PROVIDER=sqlite`` definido no ambiente (não basta o defeito implícito).
  - Executa ``pytest`` na pasta ``tests/``; falha se algum teste falhar.
  - Cria cópia consistente (API ``backup()``) de cada ficheiro SQLite candidato que exista.
  - Escreve relatório com estado do sistema no directório do checkpoint.

Uso (na raiz do repositório):
  DB_PROVIDER=sqlite python scripts/pre_migration_checkpoint.py

  PowerShell:
  $env:DB_PROVIDER='sqlite'; python scripts/pre_migration_checkpoint.py

Rollback: copiar os ficheiros ``*.db`` do directório do checkpoint de volta para os
caminhos listados no relatório (com a app parada).
"""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent

if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sqlite_meta(path: Path) -> dict[str, Any]:
    """Estado mínimo da BD para o relatório (user_version + nº de tabelas utilizador)."""
    from contextlib import closing

    from database.sqlite_tools import sqlite_connect_path

    try:
        with closing(sqlite_connect_path(path)) as conn:
            uv_row = conn.execute("PRAGMA user_version").fetchone()
            uv = int(uv_row[0]) if uv_row else 0
            n = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchone()
            n_tables = int(n[0]) if n else 0
            ver_row = conn.execute("SELECT sqlite_version()").fetchone()
            sqlite_ver = str(ver_row[0]) if ver_row else "n/d"
    except (ConnectionError, OSError) as exc:
        return {"error": str(exc)}
    return {
        "user_version": uv,
        "user_tables": n_tables,
        "sqlite_version": sqlite_ver,
    }


def _collect_db_candidates() -> list[Path]:
    from database.config import BASE_DIR, sqlite_db_path
    from database.connection import DB_PATH

    raw: list[Path] = [
        DB_PATH,
        sqlite_db_path(),
        BASE_DIR / "database.db",
        BASE_DIR / "business.db",
        BASE_DIR / "businessdev.db",
    ]
    seen: set[str] = set()
    out: list[Path] = []
    for p in raw:
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _verify_sqlite_provider() -> tuple[str, str]:
    """Devolve (valor bruto de env, valor efectivo via get_db_provider).

    Exige ``DB_PROVIDER=sqlite`` explicitamente no ambiente (sem depender só do
    defeito implícito), para auditoria pré-migração.
    """
    from database.config import DB_PROVIDER_ENV, get_db_provider

    raw = (os.environ.get(DB_PROVIDER_ENV) or "").strip()
    if not raw:
        raise SystemExit(
            f"Defina {DB_PROVIDER_ENV}=sqlite no ambiente antes de correr o checkpoint "
            f"(obrigatório para rollback documentado)."
        )
    norm = raw.lower()
    if norm in ("postgres", "postgresql", "pg", "supabase"):
        raise SystemExit(
            f"{DB_PROVIDER_ENV}={raw!r} não é compatível com este checkpoint SQLite-only."
        )
    if norm not in ("sqlite", "file"):
        raise SystemExit(
            f"{DB_PROVIDER_ENV}={raw!r} inválido para este checkpoint; use sqlite."
        )
    effective = get_db_provider()
    if effective != "sqlite":
        raise SystemExit(
            f"DB_PROVIDER efectivo é {effective!r}, esperado sqlite (inconsistência interna)."
        )
    return raw, effective


def _run_pytest(report_dir: Path) -> int:
    log_file = report_dir / "pytest_output.txt"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(_REPO / "tests"),
        "-v",
        "--tb=short",
        "--color=no",
    ]
    proc = subprocess.run(
        cmd,
        cwd=_REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "DB_PROVIDER": "sqlite"},
    )
    log_file.write_text(
        f"command: {' '.join(cmd)}\n"
        f"exit_code: {proc.returncode}\n\n"
        f"--- stdout ---\n{proc.stdout}\n\n--- stderr ---\n{proc.stderr}\n",
        encoding="utf-8",
    )
    return int(proc.returncode)


def _requirements_sha256() -> str:
    p = _REPO / "requirements.txt"
    if not p.is_file():
        return "n/d"
    return _sha256_file(p)


def _git_head() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "n/d"


def main() -> int:
    stamp = _utc_stamp()
    out_dir = _REPO / "backups" / f"migration_checkpoint_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "ALIEH — checkpoint pré-migração",
        "=============================",
        f"UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Local: {datetime.now().astimezone().isoformat()}",
        f"Platform: {platform.platform()}",
        f"Python: {sys.version.split()[0]} ({sys.executable})",
        f"Repo: {_REPO}",
        f"Git HEAD: {_git_head()}",
        f"requirements.txt sha256: {_requirements_sha256()}",
        "",
        "## DB_PROVIDER",
    ]

    try:
        raw, eff = _verify_sqlite_provider()
    except SystemExit as exc:
        (out_dir / "CHECKPOINT_FAILED.txt").write_text(
            "\n".join(lines + ["", str(exc.args[0])]), encoding="utf-8"
        )
        print(exc.args[0], file=sys.stderr)
        return 1

    lines.append(f"  env {raw}")
    lines.append(f"  effective provider: {eff}")
    lines.append("")
    lines.append("## pytest")
    code = _run_pytest(out_dir)
    lines.append(f"  exit_code: {code}")
    lines.append(f"  log: {out_dir / 'pytest_output.txt'}")
    if code != 0:
        lines.append("")
        lines.append("CHECKPOINT ABORTADO: pytest falhou.")
        (out_dir / "CHECKPOINT_REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
        print(f"pytest falhou (código {code}). Ver:", out_dir / "pytest_output.txt", file=sys.stderr)
        return code or 1

    lines.append("  status: OK (todos os testes passaram)")
    lines.append("")
    lines.append("## Backups SQLite (API backup())")

    backed: list[tuple[Path, Path]] = []
    for i, src in enumerate(_collect_db_candidates()):
        if not src.is_file():
            lines.append(f"  skip (não existe): {src}")
            continue
        safe_name = f"db_{i}_{src.name}"
        dest = out_dir / "sqlite" / safe_name
        try:
            from database.sqlite_tools import sqlite_backup_file_to_file

            sqlite_backup_file_to_file(src, dest)
        except (ConnectionError, OSError) as exc:
            lines.append(f"  ERRO {src} -> {dest}: {exc}")
            (out_dir / "CHECKPOINT_REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
            print(f"Falha ao copiar {src}: {exc}", file=sys.stderr)
            return 1
        sz = dest.stat().st_size
        digest = _sha256_file(dest)
        meta = _sqlite_meta(dest)
        lines.append(f"  OK: {src}")
        lines.append(f"      -> {dest}")
        lines.append(f"      bytes: {sz}  sha256: {digest}")
        if "error" in meta:
            lines.append(f"      meta: (erro ao ler) {meta['error']}")
        else:
            lines.append(
                f"      PRAGMA user_version={meta['user_version']}  "
                f"user_tables={meta['user_tables']}  sqlite_version={meta['sqlite_version']}"
            )
        backed.append((src, dest))

    lines.append("")
    lines.append("## Rollback")
    lines.append("  Parar a app. Substituir cada caminho original pelo ficheiro indicado acima.")
    lines.append(f"  Pacote: {out_dir}")
    lines.append("")
    lines.append("CHECKPOINT CONCLUÍDO COM SUCESSO.")

    (out_dir / "CHECKPOINT_REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
    print(str(out_dir / "CHECKPOINT_REPORT.txt"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
