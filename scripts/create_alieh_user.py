"""
Cria um utilizador na tabela ``users`` (autenticação multi-utilizador).

Uso (na raíz do projeto):
  python scripts/create_alieh_user.py NOME_UTILIZADOR [role] [tenant_id]
  role opcional: admin | operator (padrão: operator)
  tenant_id opcional: padrão ``default`` (mesmo inquilino que instalações antigas)
O script pede a senha em stdin (sem eco no Windows pode variar; use ambiente seguro).

Requer que a base SQLite já exista (corra a app uma vez ou chame init_db).
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from database.init_db import init_db  # noqa: E402
from database.user_repo import DEFAULT_USER_ROLE, insert_user  # noqa: E402


def main() -> None:
    init_db()
    if len(sys.argv) < 2:
        print(
            "Uso: python scripts/create_alieh_user.py <username> [admin|operator] [tenant_id]",
            file=sys.stderr,
        )
        sys.exit(1)
    username = sys.argv[1].strip()
    if not username:
        print("Username inválido.", file=sys.stderr)
        sys.exit(1)
    role = DEFAULT_USER_ROLE
    tenant: str | None = None
    if len(sys.argv) >= 3:
        role = sys.argv[2].strip().lower() or DEFAULT_USER_ROLE
        if role not in ("admin", "operator"):
            print("role deve ser admin ou operator.", file=sys.stderr)
            sys.exit(1)
    if len(sys.argv) >= 4:
        tenant = sys.argv[3].strip() or None
    p1 = getpass.getpass("Senha: ")
    p2 = getpass.getpass("Repetir senha: ")
    if p1 != p2:
        print("As senhas não coincidem.", file=sys.stderr)
        sys.exit(1)
    try:
        uid = insert_user(None, username, p1, role=role, tenant_id=tenant)
        print(
            f"Utilizador criado: id={uid} username={username!r} role={role!r} tenant_id={(tenant or 'default')!r}"
        )
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
