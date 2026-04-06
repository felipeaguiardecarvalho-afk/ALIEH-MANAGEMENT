"""Envio best-effort de auditoria para webhook HTTP (SIEM / agregadores).

- Activa só com URL configurada; sem URL não há chamadas de rede.
- Falhas de rede ou HTTP **não** afectam a app nem o registo local (apenas ``logging`` debug).
- Eventos em tempo real: ``critical_audit`` (cada ``log_critical_event``).
- Lotes opcionais: ``audit_snapshot`` (export periódico da base + metadados), se
  ``ALIEH_AUDIT_WEBHOOK_SNAPSHOTS`` ou ``alieh_audit_webhook_snapshots`` estiver activo.

Configuração (prioridade: variável de ambiente, depois ``st.secrets`` quando disponível):

- ``ALIEH_AUDIT_WEBHOOK_URL`` / ``alieh_audit_webhook_url``
- ``ALIEH_AUDIT_WEBHOOK_DISABLED`` / ``alieh_audit_webhook_disabled`` — ``true`` desliga envio
- ``ALIEH_AUDIT_WEBHOOK_TIMEOUT_SECONDS`` — timeout por pedido (defeito 8)
- ``ALIEH_AUDIT_WEBHOOK_HEADERS_JSON`` — cabeçalhos extra JSON, ex.: ``{"Authorization":"Bearer …"}``
- ``ALIEH_AUDIT_WEBHOOK_SNAPSHOTS`` / ``alieh_audit_webhook_snapshots`` — incluir snapshots de backup
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from utils.env_safe import STREAMLIT_CONFIG_READ_ERRORS

_logger = logging.getLogger(__name__)

_SOURCE = "alieh-management"
_SCHEMA_VERSION = 1


def _secrets_get(key: str) -> str | None:
    try:
        import streamlit as st

        v = st.secrets.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    except STREAMLIT_CONFIG_READ_ERRORS:
        pass
    return None


def _env_or_secret(env_key: str, secret_key: str) -> str:
    v = (os.environ.get(env_key) or "").strip()
    if v:
        return v
    s = _secrets_get(secret_key)
    return (s or "").strip()


def _is_truthy_env_or_secret(env_key: str, secret_key: str) -> bool:
    v = (os.environ.get(env_key) or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    try:
        import streamlit as st

        s = st.secrets.get(secret_key)
        if s is not None and str(s).strip().lower() in ("1", "true", "yes", "on"):
            return True
    except STREAMLIT_CONFIG_READ_ERRORS:
        pass
    return False


def _webhook_disabled() -> bool:
    return _is_truthy_env_or_secret(
        "ALIEH_AUDIT_WEBHOOK_DISABLED", "alieh_audit_webhook_disabled"
    )


def resolve_audit_webhook_url() -> str | None:
    url = _env_or_secret("ALIEH_AUDIT_WEBHOOK_URL", "alieh_audit_webhook_url")
    return url if url else None


def webhook_snapshots_enabled() -> bool:
    return _is_truthy_env_or_secret(
        "ALIEH_AUDIT_WEBHOOK_SNAPSHOTS", "alieh_audit_webhook_snapshots"
    )


def _timeout_seconds() -> float:
    raw = _env_or_secret(
        "ALIEH_AUDIT_WEBHOOK_TIMEOUT_SECONDS", "alieh_audit_webhook_timeout_seconds"
    )
    if not raw:
        return 8.0
    try:
        return max(1.0, min(120.0, float(raw)))
    except ValueError:
        return 8.0


def _extra_headers() -> dict[str, str]:
    raw = (os.environ.get("ALIEH_AUDIT_WEBHOOK_HEADERS_JSON") or "").strip()
    if not raw:
        raw = _secrets_get("alieh_audit_webhook_headers_json") or ""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items()}
    except (json.JSONDecodeError, TypeError):
        _logger.warning("ALIEH_AUDIT_WEBHOOK_HEADERS_JSON inválido — ignorado.")
        return {}


def _post_json(url: str, payload: dict[str, Any], *, timeout: float) -> None:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for hk, hv in _extra_headers().items():
        req.add_header(hk, hv)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(256)
    except urllib.error.HTTPError as exc:
        _logger.debug(
            "Audit webhook HTTP %s: %s",
            exc.code,
            exc.reason,
            exc_info=True,
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        _logger.debug("Audit webhook failed: %s", exc, exc_info=True)


def submit_audit_webhook_payload(
    payload: dict[str, Any],
    *,
    timeout: float | None = None,
) -> None:
    """Dispara POST JSON em thread daemon; nunca levanta para o chamador."""
    if _webhook_disabled():
        return
    url = resolve_audit_webhook_url()
    if not url:
        return
    t = float(timeout) if timeout is not None else _timeout_seconds()

    def _run() -> None:
        try:
            _post_json(url, payload, timeout=t)
        except Exception as exc:
            _logger.debug("Audit webhook unexpected error: %s", exc, exc_info=True)

    threading.Thread(target=_run, daemon=True, name="alieh-audit-webhook").start()


def forward_critical_audit_event(
    *,
    action: str,
    user: str,
    user_id: str,
    audit_prev_short: str,
    audit_chain: str,
    raw_log_line: str,
    details: dict[str, Any],
) -> None:
    payload: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "source": _SOURCE,
        "event_type": "critical_audit",
        "emitted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "action": action,
        "user": user,
        "user_id": user_id,
        "audit_prev_short": audit_prev_short,
        "audit_chain": audit_chain,
        "raw_log_line": raw_log_line,
        "details": {str(k): details[k] for k in sorted(details.keys())},
    }
    submit_audit_webhook_payload(payload, timeout=_timeout_seconds())


def forward_audit_snapshot(
    *,
    backup_stamp: str,
    db_export: dict[str, Any],
    backup_file_paths: list[str],
) -> None:
    if not webhook_snapshots_enabled():
        return
    payload: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "source": _SOURCE,
        "event_type": "audit_snapshot",
        "emitted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "backup_stamp": backup_stamp,
        "database_export": db_export,
        "backup_files": backup_file_paths,
    }
    submit_audit_webhook_payload(payload, timeout=max(_timeout_seconds(), 30.0))
