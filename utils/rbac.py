"""Controlo de acesso por perfil (RBAC) — helpers para a UI Streamlit.

Reduz chamadas espalhadas a `require_role` e erros de omissão em operações sensíveis.
"""

from __future__ import annotations

from utils.app_auth import (
    ROLE_ADMIN,
    ROLE_OPERATOR,
    get_session_user_role,
    is_auth_configured,
    is_logged_in,
    require_any_role,
    require_role,
)


def require_admin() -> None:
    """Catálogo mestre, custos gravados, precificação, exclusões irrevogáveis, entrada de estoque."""
    require_role(ROLE_ADMIN)


def require_operator_or_admin() -> None:
    """Vendas e cadastro operacional de clientes."""
    require_any_role(ROLE_OPERATOR, ROLE_ADMIN)


def is_admin() -> bool:
    """Devolve True em modo sem autenticação configurada (fluxo aberto)."""
    if not is_auth_configured():
        return True
    if not is_logged_in():
        return False
    return get_session_user_role() == ROLE_ADMIN


def is_operator_or_admin() -> bool:
    if not is_auth_configured():
        return True
    if not is_logged_in():
        return False
    return get_session_user_role() in (ROLE_OPERATOR, ROLE_ADMIN)
