from __future__ import annotations

from typing import Any

from alieh_supabase.database.client import get_supabase
from alieh_supabase.database.queries import health


def storage_connectivity() -> dict[str, Any]:
    """Camada de serviço: obtém cliente e executa verificação de infraestrutura."""
    return health.list_storage_buckets(get_supabase())
