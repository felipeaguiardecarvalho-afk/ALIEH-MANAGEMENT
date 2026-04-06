"""Utilizadores — apenas acesso a dados (padrão get/create/update).

``conn`` pode ser ``None`` para abrir ligação com :func:`~database.connection.get_db_conn`.
"""

from __future__ import annotations

from datetime import datetime
from database.connection import DbConnection
from database.repositories.support import use_connection
from database.sql_compat import INTEGRITY_VIOLATION_ERRORS, db_execute, run_insert_returning_id
from database.tenancy import resolve_tenant_id
from utils.password_hash import hash_password

DEFAULT_USER_ROLE = "operator"

__all__ = [
    "DEFAULT_USER_ROLE",
    "get_users_count",
    "get_tenant_ids_with_users",
    "get_user_by_username",
    "create_user",
    "update_user_password",
]


def _normalize_role(role: str) -> str:
    r = (role or "").strip().lower()
    return r if r else DEFAULT_USER_ROLE


def get_users_count(conn: DbConnection | None) -> int:
    with use_connection(conn) as c:
        row = db_execute(c, "SELECT COUNT(*) AS c FROM users;").fetchone()
        return int(row["c"]) if row else 0


def get_tenant_ids_with_users(conn: DbConnection | None) -> list[str]:
    """Inquilinos que têm pelo menos um utilizador (para o ecrã de login)."""
    with use_connection(conn) as c:
        rows = db_execute(
            c,
            """
            SELECT DISTINCT tenant_id FROM users
            WHERE tenant_id IS NOT NULL AND TRIM(tenant_id) != ''
            ORDER BY LOWER(tenant_id);
            """,
        ).fetchall()
        return [str(r["tenant_id"]).strip() for r in rows if r["tenant_id"]]


def get_user_by_username(
    conn: DbConnection | None,
    username,  # noqa: ANN001
    tenant_id: str | None = None,
):
    with use_connection(conn) as c:
        u = (username or "").strip()
        if not u:
            return None
        tid = resolve_tenant_id(tenant_id)
        return db_execute(
            c,
            """
            SELECT id, username, password_hash, role, tenant_id
            FROM users
            WHERE tenant_id = ? AND LOWER(username) = LOWER(?)
            LIMIT 1;
            """,
            (tid, u),
        ).fetchone()


def create_user(
    conn: DbConnection | None,
    username: str,
    plain_password: str,
    *,
    role: str | None = None,
    tenant_id: str | None = None,
) -> int:
    """Insere utilizador; levanta ValueError se nome vazio ou duplicado."""
    with use_connection(conn) as c:
        u = (username or "").strip()
        if not u:
            raise ValueError("Utilizador obrigatório.")
        if not plain_password:
            raise ValueError("Senha obrigatória.")
        role_db = _normalize_role(role or "")
        tid = resolve_tenant_id(tenant_id)
        ph = hash_password(plain_password)
        now = datetime.now().isoformat(timespec="seconds")
        try:
            return run_insert_returning_id(
                c,
                """
                INSERT INTO users (tenant_id, username, password_hash, created_at, role)
                VALUES (?, ?, ?, ?, ?);
                """,
                (tid, u, ph, now, role_db),
            )
        except INTEGRITY_VIOLATION_ERRORS as exc:
            raise ValueError(f"Utilizador já existe: {u}") from exc


def update_user_password(
    conn: DbConnection | None,
    username: str,
    plain_password: str,
    *,
    tenant_id: str | None = None,
) -> bool:
    """Actualiza o hash da senha. Devolve ``True`` se uma linha foi alterada."""
    with use_connection(conn) as c:
        u = (username or "").strip()
        if not u or not plain_password:
            return False
        tid = resolve_tenant_id(tenant_id)
        ph = hash_password(plain_password)
        cur = db_execute(
            c,
            """
            UPDATE users SET password_hash = ?
            WHERE tenant_id = ? AND LOWER(username) = LOWER(?);
            """,
            (ph, tid, u),
        )
        try:
            return int(cur.rowcount or 0) > 0
        except (AttributeError, TypeError, ValueError):
            return False


# --- Compatibilidade (nomes legados) ---
count_users = get_users_count
list_distinct_tenant_ids_with_users = get_tenant_ids_with_users
fetch_user_by_username = get_user_by_username
insert_user = create_user

__all__ += [
    "count_users",
    "list_distinct_tenant_ids_with_users",
    "fetch_user_by_username",
    "insert_user",
]
