"""Ligação à base de dados (PostgreSQL exclusivo na aplicação).

- :func:`get_db_conn` — **entrada única**: ligação PostgreSQL (Supabase). Não há fallback
  para SQLite; falhas levantam :exc:`ConnectionError` após log FATAL.
- :func:`check_database_health` / :func:`maybe_run_periodic_database_health` — ``SELECT 1`` no
  arranque (via :mod:`services.db_startup`) e opcionalmente em intervalo definido por
  ``DATABASE_HEALTH_INTERVAL_SECONDS``. A seguir, :mod:`database.health_check` agenda o probe
  Postgres em background (:func:`~database.health_check.schedule_postgres_connectivity_probe_on_startup`).
- :func:`get_postgres_conn` — **Postgres** (psycopg 3): lê o DSN de ``DATABASE_URL``
  via :func:`database.config.get_database_url`; caso contrário cadeia Supabase / :mod:`database.config`.
  Se o URL não incluir ``sslmode``, anexa ``sslmode=require`` (Supabase / SSL obrigatório).
  Resolve o ``host`` do DSN para IPv4 com :func:`socket.gethostbyname` e passa ``hostaddr``
  a :func:`psycopg.connect` para evitar falhas quando o SO não encaminha IPv6 correctamente.
  ``prepare_threshold=0``, ``autocommit=True`` — sem comandos de sessão pós-conexão (compatível
  com PgBouncer / Supabase). Transacções explícitas usam ``conn.transaction()``. Cursores por
  defeito ``binary=False``. ``connect_timeout`` (defeito 10 s; override ``DATABASE_CONNECT_TIMEOUT``).
  Uma ligação por processo é reutilizada entre reruns Streamlit (cache com ``SELECT 1``); o
  ``close()`` na instância cacheada é um no-op para que ``with get_db_conn()`` não destrua o socket.

Na primeira ligação por processo: ``Active database backend=postgresql`` (alvo mascarado) e
``PostgreSQL connection established (PgBouncer safe mode)``.

**``DB_PATH``** mantém o caminho histórico do ficheiro SQLite (migrações, export) — a app
em produção não abre SQLite via :func:`get_db_conn`.
"""

from __future__ import annotations

import logging
import os
import re
import socket
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

import psycopg
from psycopg.rows import dict_row

from database.config import get_database_url, get_postgres_dsn, get_supabase_db_url

_logger = logging.getLogger(__name__)

# Segundos (ligação TCP ao servidor Postgres); limitado a intervalo seguro.
DATABASE_CONNECT_TIMEOUT_ENV = "DATABASE_CONNECT_TIMEOUT"
# > 0: executar :func:`check_database_health` no máximo uma vez por este intervalo (Streamlit reruns).
DATABASE_HEALTH_INTERVAL_SECONDS_ENV = "DATABASE_HEALTH_INTERVAL_SECONDS"

_first_postgres_connection_log_done = False
_using_database_logged: str | None = None
_last_periodic_health_monotonic: float = 0.0

# Cache ao nível do processo (Streamlit reruns). Ver :func:`_get_or_create_cached_conn`.
_cached_conn: psycopg.Connection | None = None
_cached_conn_real_close: Any | None = None
_cached_conn_key: tuple[Any, ...] | None = None

SQLITE_DB_FILENAME = "business.db"


def _resolve_sqlite_data_dir() -> Path:
    """
    ``/data`` em VPS/Docker com volume; em Streamlit Cloud (sem escrita em ``/data``)
    usa pasta no clone do repo ou ``tempfile``.
    """
    primary = Path("/data")
    try:
        primary.mkdir(parents=True, exist_ok=True)
        return primary
    except (PermissionError, OSError):
        pass
    repo_root = Path(__file__).resolve().parents[1]
    local = repo_root / ".alieh_data"
    try:
        local.mkdir(parents=True, exist_ok=True)
        return local
    except (PermissionError, OSError):
        pass
    fallback = Path(tempfile.gettempdir()) / "alieh_sqlite_data"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


SQLITE_DATA_DIR = _resolve_sqlite_data_dir()
DB_PATH: Path = SQLITE_DATA_DIR / SQLITE_DB_FILENAME
try:
    _db_path_logged = str(DB_PATH.resolve())
except OSError:
    _db_path_logged = str(DB_PATH)
_logger.info("SQLite reference path (migrations/tools): %s (dir=%s)", _db_path_logged, SQLITE_DATA_DIR)

DbConnection = psycopg.Connection


def _wrap_postgres_cursor_binary_false(conn: psycopg.Connection) -> None:
    """Força :meth:`cursor` com ``binary=False`` por defeito (simple protocol / pooler)."""
    real = conn.cursor

    def cursor(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("binary", False)
        return real(*args, **kwargs)

    conn.cursor = cursor  # type: ignore[method-assign]


def _connection_cache_key(dsn: str, connect_kw: dict[str, Any]) -> tuple[Any, ...]:
    """Chave para invalidar cache se DSN ou parâmetros efectivos de ligação mudarem."""
    return (
        dsn,
        connect_kw.get("sslmode"),
        connect_kw.get("hostaddr"),
        connect_kw.get("connect_timeout"),
        connect_kw.get("autocommit"),
        connect_kw.get("prepare_threshold"),
        connect_kw.get("row_factory") is dict_row,
    )


def _invalidate_cached_conn() -> None:
    """Fecho real e limpeza do singleton (ligação morta ou parâmetros alterados)."""
    global _cached_conn, _cached_conn_real_close, _cached_conn_key
    if _cached_conn is None:
        _cached_conn_key = None
        return
    close_fn = _cached_conn_real_close
    _cached_conn = None
    _cached_conn_real_close = None
    _cached_conn_key = None
    if close_fn is not None:
        try:
            close_fn()
        except Exception:
            pass


def _install_noop_close_for_cache(conn: psycopg.Connection) -> None:
    """Evita que ``with conn`` / ``conn.close()`` destruam o socket partilhado entre reruns."""
    global _cached_conn_real_close

    _cached_conn_real_close = conn.close

    def _noop_close(*_a: Any, **_k: Any) -> None:
        return None

    conn.close = _noop_close  # type: ignore[method-assign]


def _get_or_create_cached_conn(dsn: str, connect_kw: dict[str, Any]) -> psycopg.Connection:
    global _cached_conn, _cached_conn_key
    key = _connection_cache_key(dsn, connect_kw)
    if _cached_conn is not None and _cached_conn_key != key:
        _invalidate_cached_conn()

    if _cached_conn is not None:
        try:
            with _cached_conn.cursor() as cur:
                cur.execute("SELECT 1", prepare=False)
            _logger.debug("Reusing cached PostgreSQL connection")
            return _cached_conn
        except Exception:
            _invalidate_cached_conn()

    conn = psycopg.connect(dsn, **connect_kw)
    conn.prepare_threshold = 0
    _wrap_postgres_cursor_binary_false(conn)
    _install_noop_close_for_cache(conn)
    _cached_conn_key = key
    _cached_conn = conn
    return conn


def _log_using_database_once(kind: str) -> None:
    """Uma linha INFO por processo: backend activo e alvo seguro para diagnóstico em produção."""
    global _using_database_logged
    if _using_database_logged is None:
        _logger.info(
            "Active database backend=postgresql target=%s",
            describe_active_database(),
        )
        _using_database_logged = kind


def _postgres_connect_timeout_seconds() -> int:
    raw = (os.environ.get(DATABASE_CONNECT_TIMEOUT_ENV) or "10").strip()
    try:
        n = int(raw)
        return max(1, min(n, 600))
    except ValueError:
        return 10


def _execute_select_one_health(conn: DbConnection) -> None:
    """``SELECT 1 AS ok`` com ``dict_row``."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 AS ok", prepare=False)
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("health probe: empty row (postgres)")
    val = row["ok"] if "ok" in row else next(iter(row.values()))
    if int(val) != 1:
        raise RuntimeError("health probe: unexpected SELECT 1 result (postgres)")


def check_database_health() -> bool:
    """Verifica PostgreSQL com ``SELECT 1``. Propaga excepção se a ligação falhar."""
    global _last_periodic_health_monotonic
    with get_db_conn() as conn:
        _execute_select_one_health(conn)
    _last_periodic_health_monotonic = time.monotonic()
    return True


def maybe_run_periodic_database_health() -> None:
    """Se ``DATABASE_HEALTH_INTERVAL_SECONDS`` > 0, corre :func:`check_database_health` com debounce."""
    global _last_periodic_health_monotonic
    raw = (os.environ.get(DATABASE_HEALTH_INTERVAL_SECONDS_ENV) or "0").strip()
    try:
        interval = int(raw)
    except ValueError:
        interval = 0
    if interval <= 0:
        return
    now = time.monotonic()
    if now - _last_periodic_health_monotonic < float(interval):
        return
    _last_periodic_health_monotonic = now
    check_database_health()


def describe_active_database() -> str:
    """Identificador seguro para logs (DSN Postgres mascara password)."""
    dsn = get_supabase_db_url() or get_postgres_dsn() or ""
    if not dsn:
        return "postgres:(dsn não configurado)"
    masked = re.sub(r"(//[^:/]+:)([^@]+)(@)", r"\1***\3", dsn, count=1)
    return f"postgres:{masked}"


def _ensure_postgres_dsn_sslmode_require(dsn: str) -> tuple[str, str]:
    """Garante ``sslmode=require`` no DSN quando ausente (Supabase / Postgres na nuvem).

    Devolve ``(dsn_ajustado, rótulo_sslmode)`` para logs. Não altera ``sslmode`` já definido.
    """
    s = (dsn or "").strip()
    if not s:
        return dsn, "require"

    def _libpq_sslmode_param(text: str) -> str | None:
        m = re.search(r"(?:^|\s)sslmode\s*=\s*([^\s]+)", text, re.I)
        return m.group(1) if m else None

    if not re.match(r"postgres(ql)?://", s, re.I):
        existing = _libpq_sslmode_param(s)
        if existing:
            return dsn, existing
        return f"{s} sslmode=require", "require"

    parsed = urlparse(s)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    if "sslmode" in qs and qs["sslmode"]:
        return dsn, (qs["sslmode"][0] or "require").strip() or "require"

    new_query = parsed.query + ("&" if parsed.query else "") + "sslmode=require"
    adjusted = urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
    )
    return adjusted, "require"


def _host_port_from_url_hostport(token: str) -> tuple[str, str | None]:
    """Extrai host e porto opcional de ``host:port``, ``[ipv6]:port`` ou só ``host``."""
    t = (token or "").strip()
    if not t:
        return "", None
    if t.startswith("["):
        close = t.find("]")
        if close != -1:
            host = t[1:close]
            rest = t[close + 1 :]
            if rest.startswith(":") and rest[1:].isdigit():
                return host, rest[1:]
            return host, None
    if ":" in t:
        base, maybe_port = t.rsplit(":", 1)
        if maybe_port.isdigit():
            return base, maybe_port
    return t, None


def _extract_tcp_host_from_postgres_dsn(dsn: str) -> str | None:
    """Hostname do DSN Postgres (URL ou parâmetro ``host=``); ``None`` se não aplicável."""
    s = (dsn or "").strip()
    if not s:
        return None
    if re.match(r"postgres(ql)?://", s, re.I):
        parsed = urlparse(s)
        netloc = (parsed.netloc or "").strip()
        if not netloc:
            return None
        hostport = netloc.rsplit("@", 1)[-1]
        host, _ = _host_port_from_url_hostport(hostport)
        return host or None
    m = re.search(r"(?:^|\s)host\s*=\s*([^\s]+)", s, re.I)
    if not m:
        return None
    return m.group(1).strip().strip("'\"") or None


def _should_try_ipv4_hostaddr(hostname: str) -> bool:
    """Falso para socket Unix, IPv6 literais (``:``) e strings vazias."""
    if not hostname or hostname.startswith("/"):
        return False
    if ":" in hostname:
        return False
    return True


def _resolve_postgres_host_to_ipv4(host: str, *, silent_probe: bool) -> str | None:
    """Resolve ``host`` para IPv4 via :func:`socket.gethostbyname`; regista ``Resolved IPv4: …``."""
    if not _should_try_ipv4_hostaddr(host):
        return None
    try:
        ipv4 = socket.gethostbyname(host)
    except OSError as exc:
        lvl = logging.DEBUG if silent_probe else logging.WARNING
        _logger.log(
            lvl,
            "PostgreSQL IPv4 resolution skipped for host %r: %s",
            host,
            exc,
        )
        return None
    if silent_probe:
        _logger.debug("Resolved IPv4: %s", ipv4)
    else:
        _logger.info("Resolved IPv4: %s", ipv4)
    return ipv4


def _require_postgres_dsn() -> str:
    # :func:`get_database_url` → env ``DATABASE_URL`` + segredos Streamlit; depois Supabase / cadeia legacy.
    direct = get_database_url()
    if direct:
        return direct.strip()
    dsn = get_supabase_db_url() or get_postgres_dsn()
    if not dsn:
        raise RuntimeError(
            "PostgreSQL connection requested but no DSN is configured. "
            "Set DATABASE_URL, SUPABASE_DB_URL (recommended for Supabase), or other DSN "
            "environment variables documented in database.config."
        )
    return dsn


def get_postgres_conn(*, silent_probe: bool = False) -> psycopg.Connection:
    """Ligação Postgres (psycopg 3): ``DATABASE_URL`` / fallbacks; reuse por processo (Streamlit).

    ``prepare_threshold=0`` e ``sslmode`` no DSN (Supabase: ``require``). Sem ``DISCARD ALL`` nem
    outros comandos de sessão após conectar (evita ``DuplicatePreparedStatement`` com PgBouncer).
    ``cursor(..., binary=False)`` por defeito (só lado cliente). Operações multi-query:
    ``conn.transaction()``.

    ``silent_probe=True`` omite «Active database backend=…», o INFO «PgBouncer safe mode» (primeira ligação) e o traceback na falha;
    regista na mesma ``PostgreSQL connection FAILED: <tipo> - <mensagem> | repr=…`` para diagnóstico.
    """
    if not silent_probe:
        _log_using_database_once("postgres")
    global _first_postgres_connection_log_done
    raw_dsn = _require_postgres_dsn()
    dsn, sslmode_label = _ensure_postgres_dsn_sslmode_require(raw_dsn)
    timeout = _postgres_connect_timeout_seconds()
    _logger.debug(
        "PostgreSQL connect params: sslmode=%s prepare_threshold=0 connect_timeout=%s",
        sslmode_label,
        timeout,
    )
    connect_kw: dict[str, Any] = {
        "autocommit": True,
        "connect_timeout": timeout,
        "row_factory": dict_row,
        "prepare_threshold": 0,
        "sslmode": sslmode_label,
    }
    host = _extract_tcp_host_from_postgres_dsn(dsn)
    if host:
        hostaddr = _resolve_postgres_host_to_ipv4(host, silent_probe=silent_probe)
        if hostaddr:
            connect_kw["hostaddr"] = hostaddr
    try:
        conn = _get_or_create_cached_conn(dsn, connect_kw)
    except (psycopg.Error, OSError) as exc:
        _logger.error(
            "PostgreSQL connection FAILED: %s - %s | repr=%r",
            type(exc).__name__,
            str(exc),
            repr(exc),
            exc_info=not silent_probe,
        )
        raise ConnectionError(
            "Não foi possível ligar à base PostgreSQL. Verifique o DSN e a rede."
        ) from exc
    if not silent_probe and not _first_postgres_connection_log_done:
        _logger.info("PostgreSQL connection established (PgBouncer safe mode)")
        _first_postgres_connection_log_done = True
    return conn


def get_db_conn() -> psycopg.Connection:
    """PostgreSQL apenas — sem fallback SQLite (entrada única da aplicação)."""
    try:
        return get_postgres_conn()
    except Exception as exc:
        _logger.error("FATAL: PostgreSQL connection failed — no fallback allowed")
        raise ConnectionError("PostgreSQL connection required but failed") from exc
