from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supabase import Client


def list_storage_buckets(client: Client) -> dict[str, Any]:
    """Verificação leve de conectividade (Storage); políticas podem restringir o resultado."""
    try:
        buckets = client.storage.list_buckets()
        return {"ok": True, "buckets": buckets}
    except Exception as exc:  # noqa: BLE001 — front mostra a mensagem ao utilizador
        return {"ok": False, "error": str(exc)}
