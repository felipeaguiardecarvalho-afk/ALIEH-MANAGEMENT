#!/usr/bin/env python3
"""
Validação de ambiente para operadores / CI (não importa ``services/``).

Modos:
  ``python scripts/qa/validate_deployment_env.py qa-gate``
      — exige DATABASE_URL, ALIEH_PG_INTEGRATION=1, ALIEH_API_TEST_URL (uso típico com ALIEH_QA_GATE=1 no pytest).
"""
from __future__ import annotations

import os
import sys


def validate_qa_gate_env() -> None:
    dsn = (os.environ.get("DATABASE_URL") or "").strip()
    if not dsn:
        raise SystemExit("DATABASE_URL em falta.")
    if (os.environ.get("ALIEH_PG_INTEGRATION") or "").strip().lower() not in ("1", "true", "yes"):
        raise SystemExit("ALIEH_PG_INTEGRATION deve ser 1 para o gate Postgres.")
    if not (os.environ.get("ALIEH_API_TEST_URL") or "").strip():
        raise SystemExit("ALIEH_API_TEST_URL em falta.")
    allow = (os.environ.get("ALIEH_ALLOW_NON_SUPABASE_DB") or "").strip().lower() in ("1", "true", "yes")
    low = dsn.lower()
    if not allow and "supabase" not in low:
        raise SystemExit(
            "DATABASE_URL deve apontar ao Supabase (ou defina ALIEH_ALLOW_NON_SUPABASE_DB=1 para outra BD)."
        )


def main() -> None:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode == "qa-gate":
        validate_qa_gate_env()
        print("validate_deployment_env: qa-gate OK")
        return
    print("Uso: python scripts/qa/validate_deployment_env.py qa-gate", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
