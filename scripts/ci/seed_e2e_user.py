#!/usr/bin/env python3
"""
Insere (ou actualiza) um utilizador de teste na tabela ``users`` para CI / E2E.
Requer ``DATABASE_URL`` (Postgres com ``schema.sql`` aplicado).

Não altera ``services/`` — apenas dados de teste descartáveis.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.password_hash import hash_password  # noqa: E402


def main() -> None:
    dsn = (os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not dsn:
        print("seed_e2e_user: DATABASE_URL em falta — a ignorar.", file=sys.stderr)
        sys.exit(0)

    username = (os.environ.get("ALIEH_CI_E2E_USERNAME") or "e2e_ci").strip()
    password = (os.environ.get("ALIEH_CI_E2E_PASSWORD") or "E2E_ci_change_me_!").strip()
    tenant = (os.environ.get("ALIEH_CI_E2E_TENANT") or "default").strip()
    role = (os.environ.get("ALIEH_CI_E2E_ROLE") or "admin").strip().lower()
    if role not in ("admin", "operator", "viewer"):
        role = "admin"

    import psycopg

    ph = hash_password(password)
    now = datetime.now(timezone.utc).isoformat()

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM users WHERE tenant_id = %s AND lower(username) = lower(%s);",
                (tenant, username),
            )
            cur.execute(
                """
                INSERT INTO users (tenant_id, username, password_hash, created_at, role)
                VALUES (%s, %s, %s, %s, %s);
                """,
                (tenant, username, ph, now, role),
            )
    print(f"seed_e2e_user: OK tenant={tenant!r} username={username!r} role={role!r}")


if __name__ == "__main__":
    main()
