"""Counters surfaced in structured HTTP logs (no external APM)."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_requests_total = 0
_errors_total = 0
_sales_submit_ok_total = 0


def inc_request() -> None:
    global _requests_total
    with _lock:
        _requests_total += 1


def inc_error() -> None:
    global _errors_total
    with _lock:
        _errors_total += 1


def inc_sales_submit_ok() -> None:
    global _sales_submit_ok_total
    with _lock:
        _sales_submit_ok_total += 1


def snapshot() -> dict[str, int]:
    with _lock:
        return {
            "cumulative_requests": _requests_total,
            "cumulative_errors": _errors_total,
            "cumulative_sales_submit_ok": _sales_submit_ok_total,
        }
