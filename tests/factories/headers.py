"""Cabeçalhos de actor para a API protótipo (paridade com ``deps.py``)."""


def actor_headers(
    *,
    role: str,
    user_id: str = "qa-test-user",
    tenant_id: str = "default",
    username: str | None = None,
) -> dict[str, str]:
    h: dict[str, str] = {
        "X-User-Id": user_id,
        "X-Tenant-Id": tenant_id,
        "X-Role": role,
    }
    if username:
        h["X-Username"] = username
    return h
