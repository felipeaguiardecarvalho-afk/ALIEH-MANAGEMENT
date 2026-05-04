"""Lightweight in-process rate limits (per user + bucket)."""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Deque

_lock = threading.Lock()
_buckets: dict[str, Deque[float]] = {}


def _window_seconds() -> int:
    try:
        return max(10, int((os.environ.get("PROTOTYPE_RATE_LIMIT_WINDOW_SEC") or "60").strip()))
    except ValueError:
        return 60


def allow_request(user_id: str, bucket: str, *, max_events: int) -> bool:
    """Sliding window: at most ``max_events`` timestamps in the last window for ``user_id``+``bucket``."""
    uid = (user_id or "").strip() or "anon"
    key = f"{bucket}:{uid}"
    now = time.monotonic()
    window = float(_window_seconds())
    cutoff = now - window
    with _lock:
        dq = _buckets.get(key)
        if dq is None:
            dq = deque()
            _buckets[key] = dq
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= max_events:
            return False
        dq.append(now)
        return True


def sale_mutation_limit() -> int:
    try:
        return min(max(int((os.environ.get("PROTOTYPE_RATE_LIMIT_SALE_MUTATIONS") or "24").strip()), 1), 200)
    except ValueError:
        return 24


def write_mutation_limit() -> int:
    try:
        return min(max(int((os.environ.get("PROTOTYPE_RATE_LIMIT_WRITE_MUTATIONS") or "60").strip()), 1), 500)
    except ValueError:
        return 60
