"""Logging estruturado para operações críticas (rastreabilidade / auditoria).

Ficheiro de auditoria em modo **append-only** (sem rotação que sobrescreva ficheiros)
e **cadeia de hashes** encadeada por linha (deteção de alteração ou remoção de linhas).

- Cada linha inclui ``audit_chain=<64 hex>`` derivado de
  ``H( hash_linha_anterior || separador || payload_canónico )`` (SHA-256), ou **HMAC-SHA256**
  com a mesma entrada se existir a variável de ambiente ``ALIEH_LOG_CHAIN_SECRET``
  (recomendado em produção: sem o segredo não é possível recalcular a cadeia válida).

- O primeiro evento após ficheiro vazio usa uma origem fixa (génesis) repetível para verificação.

Não há garantia criptográfica contra um atacante com acesso raiz ao servidor e ao segredo;
o objectivo é **dificultar alteração casual** e permitir **verificação off-line** da cadeia.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

from utils.app_auth import get_audit_session_user, get_audit_session_user_id
from utils.audit_remote_sink import forward_critical_audit_event

_LOGGER_NAME = "alieh.critical"
_logger = logging.getLogger(_LOGGER_NAME)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = _REPO_ROOT / "logs"
_DEFAULT_LOG_FILE = _LOG_DIR / "app.log"


def critical_audit_log_path() -> Path:
    """Caminho do ficheiro append-only de eventos críticos (para cópias de segurança)."""
    return _DEFAULT_LOG_FILE


_GENESIS_PREV = "0" * 64
_SEP = "\x1e"
_AUDIT_CHAIN_RE = re.compile(r"\baudit_chain=([0-9a-f]{64})\b", re.IGNORECASE)

_FORMAT = "%(asctime)s | %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"

_CHAIN_LOCK = threading.Lock()
_chain_tail_initialized = False
_chain_prev_in_memory: str = _GENESIS_PREV


def _digest(prev_hash: str, payload: str) -> str:
    raw = (prev_hash + _SEP + payload).encode("utf-8")
    secret = (os.environ.get("ALIEH_LOG_CHAIN_SECRET") or "").strip()
    if secret:
        return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hashlib.sha256(raw).hexdigest()


def _read_last_chain_hash_from_disk(path: Path) -> str:
    """Recupera o último audit_chain de um ficheiro existente (continuidade após restart)."""
    if not path.is_file():
        return _GENESIS_PREV
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return _GENESIS_PREV
            chunk_sz = min(65536, size)
            f.seek(size - chunk_sz)
            tail = f.read().decode("utf-8", errors="replace")
        for line in reversed([ln.strip() for ln in tail.splitlines() if ln.strip()]):
            m = _AUDIT_CHAIN_RE.search(line)
            if m:
                return m.group(1).lower()
    except OSError:
        pass
    return _GENESIS_PREV


def _ensure_chain_tail_loaded_unlocked() -> None:
    global _chain_tail_initialized, _chain_prev_in_memory
    if not _chain_tail_initialized:
        _chain_prev_in_memory = _read_last_chain_hash_from_disk(_DEFAULT_LOG_FILE)
        _chain_tail_initialized = True


def _ensure_handler() -> None:
    if _logger.handlers:
        return
    formatter = logging.Formatter(fmt=_FORMAT, datefmt=_DATEFMT)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    _logger.addHandler(stream_handler)

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        # Append-only: não usar RotatingFileHandler (evita truncar/sobrescrever cópias antigas).
        file_handler = logging.FileHandler(
            _DEFAULT_LOG_FILE,
            mode="a",
            encoding="utf-8",
            delay=True,
        )
        file_handler.setFormatter(formatter)
        _logger.addHandler(file_handler)
    except OSError:
        pass

    _logger.setLevel(logging.INFO)
    _logger.propagate = False


def _resolved_log_user_id(user_id: str | None) -> str:
    if user_id is not None and str(user_id).strip():
        return str(user_id).strip()
    return get_audit_session_user_id()


def log_critical_event(action: str, *, user_id: str | None = None, **details: Any) -> None:
    """
    Regista um evento com timestamp, cadeia de integridade, user=, user_id= e details.
    ``user_id`` explícito sobrepõe-se ao valor da sessão quando não vazio.
    Evite ``user`` e ``user_id`` em **details.
    """
    try:
        _ensure_handler()
        parts = [
            f"action={action}",
            f"user={get_audit_session_user()}",
            f"user_id={_resolved_log_user_id(user_id)}",
        ]
        for key in sorted(details.keys()):
            parts.append(f"{key}={details[key]!s}")
        payload = " | ".join(parts)

        global _chain_prev_in_memory, _chain_tail_initialized

        with _CHAIN_LOCK:
            _ensure_chain_tail_loaded_unlocked()
            prev = _chain_prev_in_memory
            digest = _digest(prev, payload)
            prev_short = prev[:16] if len(prev) >= 16 else prev
            message = (
                f"audit_prev={prev_short} | audit_chain={digest} | {payload}"
            )
            _chain_prev_in_memory = digest
            _logger.info(message)

        uid = _resolved_log_user_id(user_id)
        forward_critical_audit_event(
            action=action,
            user=get_audit_session_user(),
            user_id=uid,
            audit_prev_short=prev_short,
            audit_chain=digest,
            raw_log_line=message,
            details=dict(details),
        )
    except Exception as exc:
        logging.getLogger(__name__).debug(
            "log_critical_event failed: %s", exc, exc_info=True
        )


def verify_audit_log_file(path: Path | None = None) -> tuple[bool, list[str]]:
    """
    Percorre o ficheiro de auditoria e confirma a cadeia ``audit_chain``.
    Útil para controlos internos ou scripts de auditoria.

    Retorna (sucesso, lista de mensagens de erro por linha inválida ou quebra da cadeia).
    Requer o mesmo ``ALIEH_LOG_CHAIN_SECRET`` que na escrita (se foi usado).
    """
    log_path = path or _DEFAULT_LOG_FILE
    errors: list[str] = []
    if not log_path.is_file():
        return True, []

    prev = _GENESIS_PREV
    line_no = 0
    try:
        with log_path.open(encoding="utf-8", errors="replace") as f:
            for raw in f:
                line_no += 1
                line = raw.rstrip("\r\n")
                if not line or "audit_chain=" not in line:
                    continue
                m = _AUDIT_CHAIN_RE.search(line)
                if not m:
                    errors.append(f"Linha {line_no}: audit_chain ausente ou inválido.")
                    continue
                declared = m.group(1).lower()
                tail = line[m.end() :]
                if not tail.startswith(" | "):
                    errors.append(
                        f"Linha {line_no}: formato inválido após audit_chain."
                    )
                    continue
                payload = tail[3:]
                expected = _digest(prev, payload)
                if expected != declared:
                    errors.append(
                        f"Linha {line_no}: cadeia quebrada (hash declarado != esperado)."
                    )
                prev = declared
    except OSError as exc:
        errors.append(f"Leitura falhou: {exc}")

    return len(errors) == 0, errors
