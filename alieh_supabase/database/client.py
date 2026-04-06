from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supabase import Client

_client: Client | None = None


def get_supabase() -> Client:
    """Cliente Supabase (singleton lazy)."""
    global _client
    if _client is None:
        from supabase import create_client

        from alieh_supabase.utils.settings import get_supabase_config

        url, key = get_supabase_config()
        _client = create_client(url, key)
    return _client


def reset_client_for_tests() -> None:
    """Anula o singleton (apenas testes)."""
    global _client
    _client = None
