"""Request-scoped actor for access logs (set from FastAPI dependencies)."""

from __future__ import annotations

from contextvars import ContextVar

_actor_log: ContextVar[tuple[str, str, str] | None] = ContextVar(
    "prototype_actor_log", default=None
)


def set_actor_for_log(user_id: str, tenant_id: str | None, role: str) -> None:
    tid = (tenant_id or "").strip()
    _actor_log.set((user_id.strip(), tid, role.strip()))


def clear_actor_for_log() -> None:
    _actor_log.set(None)


def get_actor_for_log() -> tuple[str, str, str] | None:
    return _actor_log.get()
