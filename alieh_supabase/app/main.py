from __future__ import annotations

import os

import streamlit as st

from alieh_supabase.services.health_service import storage_connectivity
from alieh_supabase.utils.settings import bootstrap_env, get_supabase_config


def _hydrate_from_streamlit_secrets() -> None:
    """Espelha segredos Streamlit para os nomes esperados pelo cliente Supabase."""
    try:
        s = st.secrets
    except (AttributeError, RuntimeError):
        return
    for secret_key, env_key in (
        ("SUPABASE_URL", "SUPABASE_URL"),
        ("supabase_url", "SUPABASE_URL"),
        ("SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY"),
        ("supabase_anon_key", "SUPABASE_ANON_KEY"),
    ):
        if secret_key in s and env_key not in os.environ:
            val = s[secret_key]
            if val is not None and str(val).strip():
                os.environ[env_key] = str(val).strip()


def main() -> None:
    st.set_page_config(page_title="ALIEH — Supabase", layout="centered")
    bootstrap_env()
    _hydrate_from_streamlit_secrets()

    st.title("ALIEH")
    st.caption("Base nova — Supabase · alieh_supabase/app · database · services · utils")

    try:
        get_supabase_config()
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()

    st.subheader("Estado da ligação")
    overview = storage_connectivity()
    if overview.get("ok"):
        st.success("Cliente Supabase ativo.")
    else:
        st.warning("Cliente criado; Storage pode estar bloqueado por políticas ou projeto vazio.")
    st.json(overview)


if __name__ == "__main__":
    main()
