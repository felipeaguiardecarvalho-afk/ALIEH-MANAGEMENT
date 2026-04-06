"""Autenticação por utilizador/senha.

- **Modo BD (prioritário):** se existir **pelo menos um** registo na tabela
  ``users``, **só** esse modo é usado para validar palavra-passe. Credenciais
  legacy em env/Secrets ficam **desativadas** para login (mantidas apenas como
  referência operacional — ver aviso na página de login).
- **Modo legacy (compatibilidade):** se a tabela ``users`` estiver **vazia**, o
  par ALIEH_AUTH_* / Secrets continua a ser o mecanismo de login único.
- Desenvolvimento sem qualquer modo: a app abre sem login.

Produção / live: é obrigatório haver legacy (com ``users`` vazia) **ou**
utilizadores na BD.

``init_db()`` deve correr **antes** de ``ensure_authenticated_or_stop()``.

Limite de tentativas por **nome de utilizador** na base SQLite (partilhado entre
sessões e clientes) e registo opcional em ``login_attempt_audit``. Se a BD falhar,
usa-se um fallback por utilizador em ``st.session_state``.

Perfis (coluna ``users.role`` e ``alieh_auth_role`` na sessão): ``admin`` e
``operator`` (constantes ROLE_ADMIN / ROLE_OPERATOR). ``require_role`` prepara
controlo de UI futuro; sem chamadas na app o comportamento mantém-se.
"""

from __future__ import annotations

import math
import os
import secrets
import time
from typing import Optional, Tuple

import streamlit as st

from database.config import is_production_db_forced_by_env, is_public_streamlit_deploy
from database.login_throttle_repo import (
    LOCKOUT_SECONDS,
    MAX_FAILURES_BEFORE_LOCKOUT,
    clear_for_user_and_log_success,
    normalize_username,
    record_failure_and_audit_log,
    refresh_and_is_locked,
)
from database.tenancy import DEFAULT_TENANT_ID, resolve_tenant_id
from database.user_repo import DEFAULT_USER_ROLE, list_distinct_tenant_ids_with_users
from utils.env_safe import STREAMLIT_CONFIG_READ_ERRORS
from utils.error_messages import (
    MSG_AUTH_LEGACY_DISABLED_BY_DB_USERS,
    MSG_LOGIN_INVALID,
    MSG_PRODUCTION_AUTH_NOT_CONFIGURED,
    format_access_requires_one_of_roles,
    format_access_requires_role,
    format_login_rate_limited_wait,
)
from utils.password_hash import verify_password

ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"

_SESSION_AUTHENTICATED = "alieh_auth_ok"
_SESSION_USERNAME = "alieh_auth_username"
_SESSION_USER_ID = "alieh_auth_user_id"
_SESSION_USER_ROLE = "alieh_auth_role"
_SESSION_TENANT_ID = "alieh_tenant_id"
_SESSION_FAILS_BY_USER = "alieh_login_failures_by_user"
_SESSION_LOCK_UNTIL_BY_USER = "alieh_login_locked_until_by_user"
# Chaves antigas (sessão global): removidas no logout para migração suave.
_LEGACY_SESSION_LOGIN_FAILURES = "alieh_login_failures"
_LEGACY_SESSION_LOGIN_LOCKED_UNTIL = "alieh_login_locked_until"

_ENV_USER = "ALIEH_AUTH_USERNAME"
_ENV_PASSWORD = "ALIEH_AUTH_PASSWORD"
_ENV_USER_ID = "ALIEH_AUTH_USER_ID"
_ENV_RUNTIME = "ALIEH_ENV"

_PRODUCTION_VALUES = frozenset({"production", "prod"})


def is_production_environment() -> bool:
    """
    True em qualquer ambiente tratado como “live” / produção:

    - ALIEH_ENV = production ou prod (SO ou Secrets Streamlit);
    - ALIEH_PRODUCTION / ALIEH_USE_BUSINESS_DB (mesma semântica que a escolha de business.db);
    - Streamlit Community Cloud (caminho /mount/src/…).

    Nesses casos é obrigatório existir autenticação (legacy ou utilizadores na BD).
    """
    if is_production_db_forced_by_env():
        return True
    try:
        if is_public_streamlit_deploy():
            return True
    except Exception:
        pass
    v = (os.environ.get(_ENV_RUNTIME) or "").strip().lower()
    if v in _PRODUCTION_VALUES:
        return True
    try:
        sec_val = st.secrets.get(_ENV_RUNTIME) or st.secrets.get("alieh_env")
        if sec_val is not None and str(sec_val).strip().lower() in _PRODUCTION_VALUES:
            return True
    except STREAMLIT_CONFIG_READ_ERRORS:
        pass
    return False


def _credentials_from_secrets() -> Tuple[str, str]:
    try:
        sec = st.secrets
    except STREAMLIT_CONFIG_READ_ERRORS:
        return "", ""
    auth = sec.get("auth")
    if auth is not None and hasattr(auth, "get"):
        user = str(auth.get("username") or auth.get("user") or "").strip()
        password = str(auth.get("password") or "")
        if user and password:
            return user, password
    user = str(sec.get("auth_username") or "").strip()
    password = str(sec.get("auth_password") or "")
    return user, password


def _optional_user_id_from_config() -> Optional[str]:
    """ID opcional (env ou secrets) quando não há linha em ``users``."""
    v = (os.environ.get(_ENV_USER_ID) or "").strip()
    if v:
        return v
    try:
        sec = st.secrets
        auth = sec.get("auth")
        if auth is not None and hasattr(auth, "get"):
            uid = auth.get("user_id")
            if uid is not None and str(uid).strip():
                return str(uid).strip()
        raw = sec.get("auth_user_id")
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    except STREAMLIT_CONFIG_READ_ERRORS:
        pass
    return None


def get_expected_credentials() -> Tuple[str, str]:
    """Utilizador e senha legacy esperados, ou ("", "") se não configurados."""
    user = (os.environ.get(_ENV_USER) or "").strip()
    password = os.environ.get(_ENV_PASSWORD)
    if password is not None:
        password = str(password)
    else:
        password = ""
    if user and password:
        return user, password
    return _credentials_from_secrets()


def _legacy_credentials_configured() -> bool:
    u, p = get_expected_credentials()
    return bool(u and p)


def _db_has_users() -> bool:
    try:
        from database.user_repo import count_users

        return count_users(None) > 0
    except Exception:
        return False


def legacy_configured_but_superseded_by_db() -> bool:
    """
    True quando env/Secrets têm credencial legacy mas o login efectivo é só na BD.
    Útil para avisos na UI ou documentação operacional.
    """
    return _legacy_credentials_configured() and _db_has_users()


def is_auth_configured() -> bool:
    """True se há login legacy **ou** pelo menos um utilizador na tabela ``users``."""
    return _legacy_credentials_configured() or _db_has_users()


def is_logged_in() -> bool:
    return bool(st.session_state.get(_SESSION_AUTHENTICATED))


def get_audit_session_user() -> str:
    try:
        if not st.session_state.get(_SESSION_AUTHENTICATED):
            return "sem_autenticacao"
        name = st.session_state.get(_SESSION_USERNAME)
        if name is not None and str(name).strip():
            return str(name).strip()
        return "sessao_sem_utilizador"
    except Exception:
        return "streamlit_indisponivel"


def get_audit_session_user_id() -> str:
    try:
        uid = st.session_state.get(_SESSION_USER_ID)
        if uid is not None and str(uid).strip():
            return str(uid).strip()
        return "n/a"
    except Exception:
        return "streamlit_indisponivel"


def get_session_tenant_id() -> str:
    """
    Inquilino da sessão após login (ou ``DEFAULT_TENANT_ID`` se ausente / não autenticado).
    Usado por ``effective_tenant_id_for_request`` para isolamento de dados.
    """
    try:
        v = st.session_state.get(_SESSION_TENANT_ID)
        if v is not None and str(v).strip():
            return resolve_tenant_id(str(v).strip())
    except Exception:
        pass
    return DEFAULT_TENANT_ID


def get_session_user_role() -> str:
    """
    Perfil na sessão após login (minúsculas), ou ``operator`` por omissão se autenticado
    sem valor; string vazia se não autenticado.
    """
    try:
        if not st.session_state.get(_SESSION_AUTHENTICATED):
            return ""
        r = st.session_state.get(_SESSION_USER_ROLE)
        if r is not None and str(r).strip():
            return str(r).strip().lower()
        return DEFAULT_USER_ROLE
    except Exception:
        return ""


def require_role(role: str) -> None:
    """
    Garante o perfil indicado quando o login está configurado na app.
    Sem autenticação configurada (modo dev aberto), não faz nada — não altera o fluxo atual.
    """
    if not is_auth_configured():
        return
    required = (role or "").strip().lower()
    if not required:
        return
    if not is_logged_in():
        st.error("Acesso negado: inicie sessão para continuar.")
        st.stop()
    if get_session_user_role() != required:
        st.error(format_access_requires_role(required))
        st.stop()


def require_any_role(*roles: str) -> None:
    """
    Garante que a sessão tenha um dos perfis indicados quando o login está configurado.
    Sem autenticação configurada (modo dev aberto), não altera o fluxo atual.
    """
    if not is_auth_configured():
        return
    allowed = {str(r).strip().lower() for r in roles if r and str(r).strip()}
    if not allowed:
        return
    if not is_logged_in():
        st.error("Acesso negado: inicie sessão para continuar.")
        st.stop()
    if get_session_user_role() not in allowed:
        st.error(format_access_requires_one_of_roles(tuple(sorted(allowed))))
        st.stop()


def _session_login_success(
    username: str,
    user_id: Optional[str],
    role: str,
    *,
    tenant_id: str | None = None,
) -> None:
    st.session_state[_SESSION_AUTHENTICATED] = True
    st.session_state[_SESSION_USERNAME] = (username or "").strip()
    st.session_state[_SESSION_TENANT_ID] = resolve_tenant_id(tenant_id)
    uid = (user_id or "").strip()
    if uid:
        st.session_state[_SESSION_USER_ID] = uid
    else:
        st.session_state.pop(_SESSION_USER_ID, None)
    r = (role or "").strip().lower()
    st.session_state[_SESSION_USER_ROLE] = r if r else DEFAULT_USER_ROLE


def _legacy_login_profile(username: str) -> tuple[Optional[str], str]:
    """ID e role após login legacy: linha ``users`` homónima ou config + perfil admin."""
    try:
        from database.user_repo import fetch_user_by_username

        row = fetch_user_by_username(None, username, DEFAULT_TENANT_ID)
        if row:
            uid = str(row["id"])
            r = str(row["role"] or "").strip().lower() or DEFAULT_USER_ROLE
            return uid, r
    except Exception:
        pass
    return _optional_user_id_from_config(), ROLE_ADMIN


def _role_from_user_row(row) -> str:  # noqa: ANN001
    r = str(row["role"] or "").strip().lower()
    return r if r else DEFAULT_USER_ROLE


def try_login(
    username: str, password: str, *, login_tenant_id: str | None = None
) -> bool:
    username = (username or "").strip()
    password = password or ""
    tid_login = resolve_tenant_id(login_tenant_id)

    if _db_has_users():
        try:
            from database.user_repo import fetch_user_by_username

            row = fetch_user_by_username(None, username, tid_login)
            if row and verify_password(password, row["password_hash"]):
                _session_login_success(
                    username,
                    str(row["id"]),
                    _role_from_user_row(row),
                    tenant_id=str(row["tenant_id"]),
                )
                return True
        except Exception:
            if is_production_environment():
                return False
        if is_production_environment():
            return False
        return False

    legacy_user, legacy_pass = get_expected_credentials()
    if legacy_user and legacy_pass:
        if secrets.compare_digest(username, legacy_user) and secrets.compare_digest(
            password,
            legacy_pass,
        ):
            uid, sess_role = _legacy_login_profile(username)
            _session_login_success(
                username, uid, sess_role, tenant_id=DEFAULT_TENANT_ID
            )
            return True
        return False

    try:
        from database.user_repo import fetch_user_by_username

        row = fetch_user_by_username(None, username, tid_login)
        if row and verify_password(password, row["password_hash"]):
            _session_login_success(
                username,
                str(row["id"]),
                _role_from_user_row(row),
                tenant_id=str(row["tenant_id"]),
            )
            return True
    except Exception:
        if is_production_environment():
            return False

    if is_production_environment():
        return False
    return False


def _optional_client_hint() -> Optional[str]:
    """Indício opcional de cliente (ex.: cabeçalho de proxy), truncado."""
    try:
        ctx = getattr(st, "context", None)
        if ctx is None:
            return None
        h = getattr(ctx, "headers", None)
        if h is None or not hasattr(h, "get"):
            return None
        xf = h.get("X-Forwarded-For") or h.get("x-forwarded-for")
        if xf:
            return str(xf)[:256]
        return None
    except Exception:
        return None


def _session_fallback_ensure_dicts() -> tuple[dict, dict]:
    fails = st.session_state.get(_SESSION_FAILS_BY_USER)
    until = st.session_state.get(_SESSION_LOCK_UNTIL_BY_USER)
    if not isinstance(fails, dict):
        fails = {}
        st.session_state[_SESSION_FAILS_BY_USER] = fails
    if not isinstance(until, dict):
        until = {}
        st.session_state[_SESSION_LOCK_UNTIL_BY_USER] = until
    return fails, until


def _session_fallback_refresh_user(username_norm: str) -> None:
    if not username_norm:
        return
    _, until = _session_fallback_ensure_dicts()
    lu = float(until.get(username_norm, 0) or 0)
    if lu > 0 and time.time() >= lu:
        until.pop(username_norm, None)
        fails, _ = _session_fallback_ensure_dicts()
        fails.pop(username_norm, None)


def _session_fallback_is_locked(username_norm: str) -> Tuple[bool, int]:
    if not username_norm:
        return False, 0
    _session_fallback_refresh_user(username_norm)
    _, until = _session_fallback_ensure_dicts()
    lu = float(until.get(username_norm, 0) or 0)
    if lu > 0 and time.time() < lu:
        return True, max(0, int(math.ceil(lu - time.time())))
    return False, 0


def _session_fallback_record_failure(
    username_norm: str,
) -> Tuple[bool, int, int]:
    """Espelha a política do repositório quando SQLite não está acessível."""
    if not username_norm:
        return False, 0, 0
    fails, until = _session_fallback_ensure_dicts()
    locked, rem = _session_fallback_is_locked(username_norm)
    if locked:
        return True, rem, int(fails.get(username_norm, 0) or 0)

    c = int(fails.get(username_norm, 0) or 0) + 1
    fails[username_norm] = c
    if c >= MAX_FAILURES_BEFORE_LOCKOUT:
        until[username_norm] = time.time() + LOCKOUT_SECONDS
        fails[username_norm] = 0
        return True, LOCKOUT_SECONDS, MAX_FAILURES_BEFORE_LOCKOUT
    return False, 0, c


def _throttle_tenant(
    throttle_tenant_id: str | None,
) -> str:
    if throttle_tenant_id is not None and str(throttle_tenant_id).strip():
        return resolve_tenant_id(throttle_tenant_id)
    return get_session_tenant_id()


def _throttle_user_is_locked(
    username_norm: str, throttle_tenant_id: str | None = None
) -> Tuple[bool, int]:
    if not username_norm:
        return False, 0
    ttid = _throttle_tenant(throttle_tenant_id)
    db_locked, db_rem = False, 0
    try:
        db_locked, db_rem = refresh_and_is_locked(None, username_norm, ttid)
    except Exception:
        db_locked, db_rem = False, 0
    sf_locked, sf_rem = _session_fallback_is_locked(username_norm)
    if db_locked and sf_locked:
        return True, max(db_rem, sf_rem)
    if db_locked:
        return True, db_rem
    if sf_locked:
        return True, sf_rem
    return False, 0


def _throttle_record_failure(
    username_norm: str, throttle_tenant_id: str | None = None
) -> Tuple[bool, int, int]:
    if not username_norm:
        return False, 0, 0
    ttid = _throttle_tenant(throttle_tenant_id)
    hint = _optional_client_hint()
    try:
        locked, rem, consecutive = record_failure_and_audit_log(
            username_norm, client_hint=hint, tenant_id=ttid
        )
        fails, until = _session_fallback_ensure_dicts()
        fails.pop(username_norm, None)
        until.pop(username_norm, None)
        return locked, rem, consecutive
    except Exception:
        locked, rem, consecutive = _session_fallback_record_failure(username_norm)
        return locked, rem, consecutive


def _throttle_clear_success(
    username_norm: str, throttle_tenant_id: str | None = None
) -> None:
    ttid = _throttle_tenant(throttle_tenant_id)
    hint = _optional_client_hint()
    try:
        clear_for_user_and_log_success(
            username_norm, client_hint=hint, tenant_id=ttid
        )
    except Exception:
        pass
    fails, until = _session_fallback_ensure_dicts()
    fails.pop(username_norm, None)
    until.pop(username_norm, None)


def _login_throttle_clear_session_keys() -> None:
    st.session_state.pop(_SESSION_FAILS_BY_USER, None)
    st.session_state.pop(_SESSION_LOCK_UNTIL_BY_USER, None)
    st.session_state.pop(_LEGACY_SESSION_LOGIN_FAILURES, None)
    st.session_state.pop(_LEGACY_SESSION_LOGIN_LOCKED_UNTIL, None)


def logout() -> None:
    st.session_state.pop(_SESSION_AUTHENTICATED, None)
    st.session_state.pop(_SESSION_USERNAME, None)
    st.session_state.pop(_SESSION_USER_ID, None)
    st.session_state.pop(_SESSION_USER_ROLE, None)
    st.session_state.pop(_SESSION_TENANT_ID, None)
    _login_throttle_clear_session_keys()


def _render_production_auth_missing_and_stop() -> None:
    """Bloqueia totalmente a app até existir modo de login (legacy ou BD)."""
    st.title("ALIEH — Produção sem autenticação configurada")
    st.error(
        "Não é possível iniciar: neste ambiente o login é obrigatório, mas não há "
        "credencial legacy nem utilizadores registados na base de dados."
    )
    st.markdown(MSG_PRODUCTION_AUTH_NOT_CONFIGURED)
    st.stop()


def render_login_and_stop() -> None:
    """Mostra o formulário de login e interrompe a execução até credenciais válidas."""
    st.title("ALIEH — Acesso")
    st.caption("Inicie sessão para utilizar a gestão comercial.")
    if legacy_configured_but_superseded_by_db():
        st.warning(MSG_AUTH_LEGACY_DISABLED_BY_DB_USERS)
    login_tid = DEFAULT_TENANT_ID
    with st.form("alieh_login_form"):
        try:
            if _db_has_users():
                tlist = list_distinct_tenant_ids_with_users(None)
                if len(tlist) > 1:
                    login_tid = st.selectbox(
                        "Empresa (inquilino)",
                        options=tlist,
                        index=0,
                        help="Cada empresa tem dados isolados. O utilizador é válido só no inquilino escolhido.",
                    )
                elif len(tlist) == 1:
                    login_tid = tlist[0]
                    st.caption(f"Dados do inquilino: **{login_tid}**")
        except Exception:
            pass
        username = st.text_input(
            "Utilizador",
            key="alieh_login_username",
            autocomplete="username",
        )
        password = st.text_input(
            "Senha",
            type="password",
            key="alieh_login_password",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button("Entrar")
    if submitted:
        norm = normalize_username(username)
        locked, rem = _throttle_user_is_locked(norm, login_tid)
        if locked:
            st.error(format_login_rate_limited_wait(rem))
            st.stop()
        if try_login(username, password, login_tenant_id=login_tid):
            _throttle_clear_success(norm, login_tid)
            st.rerun()
        locked_now, rem_now, consecutive = _throttle_record_failure(norm, login_tid)
        if locked_now:
            st.error(format_login_rate_limited_wait(rem_now))
        else:
            st.error(MSG_LOGIN_INVALID)
            if _db_has_users():
                st.info(
                    "Com utilizadores na base de dados, só vale a palavra-passe "
                    "registada em **users** (o par legacy dos secrets não é usado para login). "
                    "Para criar ou redefinir: `python scripts/create_alieh_user.py`."
                )
            elif _legacy_credentials_configured():
                st.info(
                    "Confirme **auth_username** / **auth_password** em `.streamlit/secrets.toml` "
                    "(ou **ALIEH_AUTH_USERNAME** / **ALIEH_AUTH_PASSWORD** no ambiente). "
                    "O valor tem de coincidir exactamente."
                )
            left = MAX_FAILURES_BEFORE_LOCKOUT - consecutive
            if left > 0 and norm:
                st.caption(
                    f"Tentativas restantes para este utilizador antes do bloqueio temporário: {left}."
                )
    st.stop()


def ensure_authenticated_or_stop() -> None:
    """
    Produção: exige legacy ou utilizadores na BD (a base já deve estar inicializada).
    Fora de produção: sem modos de login → não pede credenciais.
    Com login configurado: exige sessão ou formulário.
    """
    if is_production_environment() and not is_auth_configured():
        _render_production_auth_missing_and_stop()
    if not is_auth_configured():
        return
    if is_logged_in():
        return
    render_login_and_stop()
