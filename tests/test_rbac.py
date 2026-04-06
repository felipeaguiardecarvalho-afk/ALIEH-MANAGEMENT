"""
Testes RBAC: simula sessões Streamlit com perfis distintos e valida que
``require_*`` e ``is_*`` comportam como esperado (operador não passa gates admin).

``st.stop()`` é substituído por uma excepção de teste para deteção determinística.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from utils import app_auth as auth
from utils import rbac


class StreamlitStopped(Exception):
    """Simula encerramento da app quando ``st.stop()`` é chamado."""


@pytest.fixture
def mock_streamlit():
    """
    Injeta estado de sessão mutável e captura ``st.stop`` / ``st.error`` em
    ``utils.app_auth`` (onde ``require_role`` resolve ``st``).
    """
    session: dict = {}

    st_mock = MagicMock()
    st_mock.session_state = session
    st_mock.error = MagicMock()
    st_mock.stop = MagicMock(side_effect=StreamlitStopped)

    with patch("utils.app_auth.st", st_mock):
        yield session, st_mock


def _login(session: dict, *, role: str, user: str = "tester") -> None:
    session[auth._SESSION_AUTHENTICATED] = True  # noqa: SLF001
    session[auth._SESSION_USERNAME] = user  # noqa: SLF001
    session[auth._SESSION_USER_ROLE] = role  # noqa: SLF001


def _logout(session: dict) -> None:
    session.clear()


# --- require_role / require_any_role (app_auth) ---


@pytest.mark.parametrize("role", ["admin", "ADMIN", "Admin"])
def test_require_role_admin_allows_admin_session(mock_streamlit, role):
    session, st_mock = mock_streamlit
    _login(session, role=role)
    with patch.object(auth, "is_auth_configured", return_value=True):
        auth.require_role(auth.ROLE_ADMIN)
    st_mock.stop.assert_not_called()


def test_require_role_admin_blocks_operator(mock_streamlit):
    session, st_mock = mock_streamlit
    _login(session, role="operator")
    with patch.object(auth, "is_auth_configured", return_value=True):
        with pytest.raises(StreamlitStopped):
            auth.require_role(auth.ROLE_ADMIN)
    st_mock.error.assert_called_once()
    st_mock.stop.assert_called_once()


def test_require_role_blocks_when_not_logged_in(mock_streamlit):
    session, st_mock = mock_streamlit
    _logout(session)
    with patch.object(auth, "is_auth_configured", return_value=True):
        with pytest.raises(StreamlitStopped):
            auth.require_role(auth.ROLE_ADMIN)
    st_mock.stop.assert_called_once()


def test_require_role_noop_when_auth_not_configured(mock_streamlit):
    session, st_mock = mock_streamlit
    _login(session, role="operator")
    with patch.object(auth, "is_auth_configured", return_value=False):
        auth.require_role(auth.ROLE_ADMIN)
    st_mock.stop.assert_not_called()


@pytest.mark.parametrize(
    "role,should_allow",
    [
        ("operator", True),
        ("admin", True),
        ("OPERATOR", True),
        ("viewer", False),
        # Sem valor explícito na sessão: ``get_session_user_role`` usa perfil por defeito ``operator``.
        ("", True),
    ],
)
def test_require_any_role_operator_or_admin(mock_streamlit, role, should_allow):
    session, st_mock = mock_streamlit
    session[auth._SESSION_AUTHENTICATED] = True  # noqa: SLF001
    session[auth._SESSION_USER_ROLE] = role  # noqa: SLF001

    with patch.object(auth, "is_auth_configured", return_value=True):
        if should_allow:
            auth.require_any_role(auth.ROLE_OPERATOR, auth.ROLE_ADMIN)
            st_mock.stop.assert_not_called()
        else:
            with pytest.raises(StreamlitStopped):
                auth.require_any_role(auth.ROLE_OPERATOR, auth.ROLE_ADMIN)
            st_mock.stop.assert_called_once()


def test_require_any_role_not_logged_in(mock_streamlit):
    session, st_mock = mock_streamlit
    _logout(session)
    with patch.object(auth, "is_auth_configured", return_value=True):
        with pytest.raises(StreamlitStopped):
            auth.require_any_role(auth.ROLE_OPERATOR, auth.ROLE_ADMIN)


# --- rbac helpers ---


def test_require_admin_blocks_operator(mock_streamlit):
    session, st_mock = mock_streamlit
    _login(session, role="operator")
    with patch.object(auth, "is_auth_configured", return_value=True):
        with pytest.raises(StreamlitStopped):
            rbac.require_admin()
    st_mock.stop.assert_called_once()


def test_require_admin_allows_admin(mock_streamlit):
    session, st_mock = mock_streamlit
    _login(session, role="admin")
    with patch.object(auth, "is_auth_configured", return_value=True):
        rbac.require_admin()
    st_mock.stop.assert_not_called()


def test_require_operator_or_admin_allows_operator(mock_streamlit):
    session, st_mock = mock_streamlit
    _login(session, role="operator")
    with patch.object(auth, "is_auth_configured", return_value=True):
        rbac.require_operator_or_admin()
    st_mock.stop.assert_not_called()


def test_require_operator_or_admin_blocks_unknown_role(mock_streamlit):
    session, st_mock = mock_streamlit
    _login(session, role="guest")
    with patch.object(auth, "is_auth_configured", return_value=True):
        with pytest.raises(StreamlitStopped):
            rbac.require_operator_or_admin()


def test_is_admin_true_when_auth_disabled(mock_streamlit):
    session, _ = mock_streamlit
    _logout(session)
    with patch.object(rbac, "is_auth_configured", return_value=False):
        assert rbac.is_admin() is True


def test_is_admin_false_operator_when_auth_on(mock_streamlit):
    session, _ = mock_streamlit
    _login(session, role="operator")
    with patch.object(rbac, "is_auth_configured", return_value=True):
        assert rbac.is_admin() is False


def test_is_admin_true_admin_when_auth_on(mock_streamlit):
    session, _ = mock_streamlit
    _login(session, role="admin")
    with patch.object(rbac, "is_auth_configured", return_value=True):
        assert rbac.is_admin() is True


def test_is_operator_or_admin_false_when_auth_on_not_logged_in(mock_streamlit):
    session, _ = mock_streamlit
    _logout(session)
    with patch.object(rbac, "is_auth_configured", return_value=True):
        assert rbac.is_operator_or_admin() is False


def test_authenticated_without_role_defaults_to_operator_for_gates(mock_streamlit):
    """Utilizador autenticado sem ``alieh_auth_role`` deve usar perfil por defeito (operator)."""
    session, st_mock = mock_streamlit
    session[auth._SESSION_AUTHENTICATED] = True  # noqa: SLF001
    session[auth._SESSION_USERNAME] = "orphan"  # noqa: SLF001
    session.pop(auth._SESSION_USER_ROLE, None)  # noqa: SLF001

    with patch.object(auth, "is_auth_configured", return_value=True):
        rbac.require_operator_or_admin()
    st_mock.stop.assert_not_called()

    with patch.object(auth, "is_auth_configured", return_value=True):
        with pytest.raises(StreamlitStopped):
            rbac.require_admin()


def test_operator_cannot_pass_admin_gate_multiple_entry_points(mock_streamlit):
    """Garante que operador falha tanto em ``require_role(admin)`` como ``require_admin``."""
    session, _ = mock_streamlit
    _login(session, role="operator")
    with patch.object(auth, "is_auth_configured", return_value=True):
        with pytest.raises(StreamlitStopped):
            auth.require_role(auth.ROLE_ADMIN)
        with pytest.raises(StreamlitStopped):
            rbac.require_admin()
