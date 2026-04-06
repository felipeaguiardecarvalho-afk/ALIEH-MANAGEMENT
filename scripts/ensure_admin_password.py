"""
Garante que o utilizador ``admin`` no inquilino por defeito pode iniciar sessão com a senha indicada.

Útil quando a tabela ``users`` já tem linhas (modo BD): o login legacy deixa de aplicar.

Uso (na raiz do repositório):
  python scripts/ensure_admin_password.py [senha]

Senha por omissão: 250515 (alinha com auth_password local em secrets.toml).

Não versionar senhas em produção; prefira ``python scripts/create_alieh_user.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from database.init_db import init_db  # noqa: E402
from database.user_repo import (  # noqa: E402
    DEFAULT_TENANT_ID,
    count_users,
    insert_user,
    update_user_password,
)


def main() -> None:
    init_db()
    password = (sys.argv[1] if len(sys.argv) > 1 else "250515").strip()
    if not password:
        print("Senha vazia.", file=sys.stderr)
        sys.exit(1)
    if count_users(None) == 0:
        print(
            "Nenhum utilizador na BD — o login usa credenciais legacy (secrets / env). "
            "auth_password=250515 nos secrets já basta."
        )
        return
    if update_user_password(None, "admin", password, tenant_id=DEFAULT_TENANT_ID):
        print("Senha do utilizador «admin» actualizada.")
        return
    try:
        insert_user(
            None,
            "admin",
            password,
            role="admin",
            tenant_id=DEFAULT_TENANT_ID,
        )
        print("Utilizador «admin» criado com perfil admin.")
    except ValueError as exc:
        print(
            "Não foi possível actualizar nem criar «admin». "
            f"Verifique o inquilino ou duplicados: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
