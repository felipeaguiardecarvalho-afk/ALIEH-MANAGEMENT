"""TTL in-process cache for safe read-only API responses (api-prototype).

Not used for stock-critical paths beyond list metadata; stock on sale uses ``POST /sales/preview``.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}


def read_cache_ttl_seconds() -> int:
    raw = (os.environ.get("PROTOTYPE_READ_CACHE_TTL_SECONDS") or "45").strip()
    try:
        return min(max(int(raw), 5), 120)
    except ValueError:
        return 45


def cache_get(key: str) -> Any | None:
    now = time.monotonic()
    with _lock:
        ent = _store.get(key)
        if not ent:
            return None
        exp, val = ent
        if now >= exp:
            del _store[key]
            return None
        return val


def cache_set(key: str, value: Any) -> None:
    with _lock:
        _store[key] = (time.monotonic() + float(read_cache_ttl_seconds()), value)


def invalidate_tenant_sale_reads(tenant_id: str | None) -> None:
    """Invalidate cached customers list, saleable SKUs, and per-SKU batch lists for a tenant."""
    tid = (tenant_id or "default").strip() or "default"
    prefixes = (f"cust_list:{tid}:", f"sale_skus:{tid}:", f"inv_batches:{tid}:")
    with _lock:
        for k in list(_store.keys()):
            if any(k.startswith(p) for p in prefixes):
                del _store[k]


def cached_call(key: str, producer: Callable[[], T]) -> T:
    hit = cache_get(key)
    if hit is not None:
        return hit  # type: ignore[return-value]
    val = producer()
    cache_set(key, val)
    return val
