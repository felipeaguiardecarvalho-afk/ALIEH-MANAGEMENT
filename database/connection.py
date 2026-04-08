"""Ligação à base de dados.

- :func:`get_db_conn` — **entrada única** recomendada: SQLite ou Postgres conforme
  :func:`database.config.get_database_provider` (automático via ``DATABASE_URL`` ou explícito
  ``DB_PROVIDER``; ver :mod:`database.config`).
- :func:`check_database_health` / :func:`maybe_run_periodic_database_health` — ``SELECT 1`` no
  arranque (via :mod:`services.db_startup`) e opcionalmente em intervalo definido por
  ``DATABASE_HEALTH_INTERVAL_SECONDS``. A seguir, :mod:`database.health_check` agenda o probe
  Postgres em background (:func:`~database.health_check.schedule_postgres_connectivity_probe_on_startup`).
- :func:`get_conn` — somente SQLite (usado internamente quando o provedor é sqlite).
- :func:`get_postgres_conn` — **Postgres** (psycopg 3): lê o DSN de ``DATABASE_URL``
  (env) quando definido; caso contrário mantém a cadeia em :mod:`database.config`.
  Se o URL não incluir ``sslmode``, anexa ``sslmode=require`` (Supabase / SSL obrigatório).
  Resolve o ``host`` do DSN para IPv4 com :func:`socket.gethostbyname` e passa ``hostaddr``
  a :func:`psycopg.connect` para evitar falhas quando o SO não encaminha IPv6 correctamente.
  ``prepare_threshold=0``, ``autocommit=True`` e ``DISCARD ALL`` na sessão para PgBouncer /
  Supabase pooler (``DuplicatePreparedStatement``). Transacções explícitas usam ainda
  ``conn.transaction()``. Cursores por defeito ``binary=False``. ``connect_timeout`` via env.

Na primeira ligação por processo é registado ``Active database backend=sqlite`` ou
``backend=postgresql`` com alvo mascarado (DSN sem password).

**SQLite:** ficheiro em ``DB_PATH``. Ordem de pastas: ``/data`` (Docker) se gravável;
senão ``.alieh_data`` na raiz do repositório (ex.: Streamlit Cloud); senão ``/tmp/...``.
O ficheiro só é criado ao abrir a primeira ligação (:func:`database.init_db` usa ``IF NOT EXISTS``).

Ligações SQLite usam :class:`database.timed_sqlite.TimedSqliteConnection` para registo de
duração das queries (DEBUG por defeito; INFO se exceder ``SLOW_QUERY_MS``).
"""

from __future__ import annotations

import logging
import os
import re
import socket
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Union
from urllib.parse import parse_qs, urlparse, urlunparse

import psycopg
from psycopg.errors import DuplicatePreparedStatement
from psycopg.rows import dict_row

from database.config import (
    get_database_provider,
    get_postgres_dsn,
    get_supabase_db_url,
    record_postgres_unreachable_use_sqlite_fallback,
    should_use_sqlite_fallback_after_postgres_failure,
)
from database.timed_sqlite import TimedSqliteConnection

_logger = logging.getLogger(__name__)

DATABASE_URL_ENV = "DATABASE_URL"
# Segundos (ligação TCP ao servidor Postgres); limitado a intervalo seguro.
DATABASE_CONNECT_TIMEOUT_ENV = "DATABASE_CONNECT_TIMEOUT"
# > 0: executar :func:`check_database_health` no máximo uma vez por este intervalo (Streamlit reruns).
DATABASE_HEALTH_INTERVAL_SECONDS_ENV = "DATABASE_HEALTH_INTERVAL_SECONDS"

_first_sqlite_connection_log_done = False
_first_postgres_connection_log_done = False
_using_database_logged: str | None = None
_last_periodic_health_monotonic: float = 0.0
_primary_database_postgres_logged = False
_fallback_to_sqlite_logged = False

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
_logger.info("SQLite database path: %s (dir=%s)", _db_path_logged, SQLITE_DATA_DIR)

# Tipo de retorno unificado (SQLite Row vs Postgres dict_row).
DbConnection = Union[sqlite3.Connection, psycopg.Connection]


def _wrap_postgres_cursor_binary_false(conn: psycopg.Connection) -> None:
    """Força :meth:`cursor` com ``binary=False`` por defeito (simple protocol / pooler)."""
    real = conn.cursor

    def cursor(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("binary", False)
        return real(*args, **kwargs)

    conn.cursor = cursor  # type: ignore[method-assign]


def _apply_pgbouncer_safe_session(conn: psycopg.Connection) -> None:
    """
    Limpa estado de sessão e força cursores seguros para PgBouncer (pooler Supabase :6543).

    Usa ``cur.execute(..., prepare=False)`` — ``Connection.execute`` pode disparar
    DuplicatePreparedStatement no modo transação do pooler. Se ``DISCARD ALL`` falhar
    com esse erro, continua-se sem descarte (ligação ainda utilizável).
    """
    try:
        with conn.cursor() as cur:
            cur.execute("DISCARD ALL;", prepare=False)
    except DuplicatePreparedStatement:
        _logger.warning(
            "DISCARD ALL omitido (DuplicatePreparedStatement — pooler transacção); "
            "estado de sessão pode herdar GUCs do backend."
        )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE;",
                prepare=False,
            )
    except DuplicatePreparedStatement:
        _logger.warning(
            "SET SESSION CHARACTERISTICS omitido (DuplicatePreparedStatement — pooler)."
        )
    _wrap_postgres_cursor_binary_false(conn)
    _logger.info("PgBouncer safe mode enabled (no prepared statements)")


def _log_using_database_once(kind: str) -> None:
    """Uma linha INFO por processo: backend activo e alvo seguro para diagnóstico em produção."""
    global _using_database_logged
    if _using_database_logged is None:
        if kind == "sqlite":
            _logger.info("Active database backend=sqlite path=%s", DB_PATH)
        else:
            _logger.info(
                "Active database backend=postgresql target=%s",
                describe_active_database(),
            )
        _using_database_logged = kind


def _postgres_connect_timeout_seconds() -> int:
    raw = (os.environ.get(DATABASE_CONNECT_TIMEOUT_ENV) or "30").strip()
    try:
        n = int(raw)
        return max(1, min(n, 600))
    except ValueError:
        return 30


def _activate_postgres_auto_sqlite_fallback(exc: BaseException | None) -> None:
    """Fallback SQLite após falha Postgres quando :func:`should_use_sqlite_fallback_after_postgres_failure`."""
    global _using_database_logged, _first_postgres_connection_log_done, _fallback_to_sqlite_logged
    label = type(exc).__name__ if exc is not None else "unknown"
    _logger.error(
        "PostgreSQL connection failed (%s); falling back to SQLite "
        "(credentials not logged).",
        label,
    )
    if not _fallback_to_sqlite_logged:
        _logger.info("Fallback activated: SQLite")
        _fallback_to_sqlite_logged = True
    record_postgres_unreachable_use_sqlite_fallback()
    _using_database_logged = None
    _first_postgres_connection_log_done = False


def _execute_select_one_health(conn: DbConnection) -> None:
    """``SELECT 1 AS ok`` — compatível com SQLite ``Row`` e Postgres ``dict_row``."""
    if isinstance(conn, sqlite3.Connection):
        row = conn.execute("SELECT 1 AS ok").fetchone()
        if row is None or int(row["ok"]) != 1:
            raise RuntimeError("health probe: unexpected SELECT 1 result (sqlite)")
        return
    with conn.cursor() as cur:
        cur.execute("SELECT 1 AS ok")
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("health probe: empty row (postgres)")
    val = row["ok"] if "ok" in row else next(iter(row.values()))
    if int(val) != 1:
        raise RuntimeError("health probe: unexpected SELECT 1 result (postgres)")


def check_database_health(*, apply_auto_fallback: bool = True) -> bool:
    """
    Verifica acessibilidade do motor actual com ``SELECT 1``.

    Em falha, regista erro. Se ``apply_auto_fallback`` e o Postgres foi escolhido só por
    ``DATABASE_URL`` (sem ``DB_PROVIDER=postgres``), activa fallback SQLite e repete o probe.
    """
    global _last_periodic_health_monotonic
    try:
        with get_db_conn() as conn:
            _execute_select_one_health(conn)
        _last_periodic_health_monotonic = time.monotonic()
        return True
    except Exception as exc:
        _logger.error(
            "Database health check failed (%s); SELECT 1 did not succeed.",
            type(exc).__name__,
        )
        if (
            apply_auto_fallback
            and should_use_sqlite_fallback_after_postgres_failure()
            and get_database_provider() == "postgres"
        ):
            _activate_postgres_auto_sqlite_fallback(exc)
            try:
                with get_db_conn() as conn:
                    _execute_select_one_health(conn)
                _last_periodic_health_monotonic = time.monotonic()
                return True
            except Exception as exc2:
                _logger.error(
                    "Database health check failed after SQLite fallback (%s).",
                    type(exc2).__name__,
                )
                return False
        return False


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
    if get_database_provider() == "sqlite":
        return f"sqlite:{DB_PATH}"
    dsn = get_supabase_db_url() or get_postgres_dsn() or ""
    if not dsn:
        return "postgres:(dsn não configurado)"
    masked = re.sub(r"(//[^:/]+:)([^@]+)(@)", r"\1***\3", dsn, count=1)
    return f"postgres:{masked}"


def get_conn() -> sqlite3.Connection:
    if get_database_provider() != "sqlite":
        raise RuntimeError(
            "get_conn() is SQLite-only. Use get_db_conn() for PostgreSQL "
            "(automatic via DATABASE_URL or explicit DB_PROVIDER), "
            "or force SQLite with DB_PROVIDER=sqlite."
        )
    _log_using_database_once("sqlite")
    global _first_sqlite_connection_log_done
    # Nova conexão por uso; Streamlit pode executar código em várias threads.
    try:
        SQLITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        pass
    try:
        conn = sqlite3.connect(
            str(DB_PATH),
            timeout=30.0,
            factory=TimedSqliteConnection,
        )
    except (sqlite3.Error, OSError) as exc:
        _logger.exception("Falha ao abrir SQLite (%s)", DB_PATH)
        raise ConnectionError(
            f"Não foi possível ligar à base SQLite em {DB_PATH}: {exc}"
        ) from exc
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    if not _first_sqlite_connection_log_done:
        _logger.debug("Database connection ready sqlite path=%s", DB_PATH)
        _first_sqlite_connection_log_done = True
    return conn


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
    # ``DATABASE_URL`` é a fonte canónica solicitada para o string de ligação;
    # se ausente, mantém-se a cadeia já suportada (Supabase, secrets, etc.).
    direct = (os.environ.get(DATABASE_URL_ENV) or "").strip()
    if direct:
        return direct
    dsn = get_supabase_db_url() or get_postgres_dsn()
    if not dsn:
        raise RuntimeError(
            "PostgreSQL connection requested but no DSN is configured. "
            "Set DATABASE_URL, SUPABASE_DB_URL (recommended for Supabase), or other fallbacks "
            "documented in database.config."
        )
    return dsn


def get_postgres_conn(*, silent_probe: bool = False) -> psycopg.Connection:
    """Nova ligação Postgres (psycopg 3): ``DATABASE_URL`` / fallbacks, modo pooler-seguro.

    ``autocommit=True``, ``prepare_threshold=0``, ``sslmode`` explícito, ``DISCARD ALL`` na sessão,
    e ``cursor(..., binary=False)`` por defeito. Operações multi-query devem usar ``conn.transaction()``.

    ``silent_probe=True`` omite «Active database backend=…» / «connection ready» e o traceback na falha;
    regista na mesma ``PostgreSQL connection FAILED: <tipo> - <mensagem> | repr=…`` para diagnóstico.
    """
    if not silent_probe:
        _log_using_database_once("postgres")
    global _first_postgres_connection_log_done
    raw_dsn = _require_postgres_dsn()
    dsn, sslmode_label = _ensure_postgres_dsn_sslmode_require(raw_dsn)
    # Supabase / nuvem: ``sslmode=require`` no DSN quando omitido (ver :func:`_ensure_postgres_dsn_sslmode_require`).
    ssl_log = (
        "PostgreSQL SSL mode: require"
        if sslmode_label == "require"
        else f"PostgreSQL SSL mode: {sslmode_label}"
    )
    if silent_probe:
        _logger.debug("%s", ssl_log)
    else:
        _logger.info("%s", ssl_log)
    prep_log = "Prepared statements disabled (prepare_threshold=0)"
    if silent_probe:
        _logger.debug("%s", prep_log)
    else:
        _logger.info("%s", prep_log)
    timeout = _postgres_connect_timeout_seconds()
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
        conn = psycopg.connect(dsn, **connect_kw)
        # Reforço: alguns edge cases com pooler ignoram o kwarg na abertura.
        conn.prepare_threshold = 0
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
    _apply_pgbouncer_safe_session(conn)
    if not silent_probe and not _first_postgres_connection_log_done:
        _logger.debug("Database connection ready %s", describe_active_database())
        _first_postgres_connection_log_done = True
    return conn


def get_db_conn() -> DbConnection:
    """Devolve conexão conforme :func:`~database.config.get_database_provider`."""
    global _primary_database_postgres_logged
    provider = get_database_provider()
    if provider == "sqlite":
        return get_conn()
    if not _primary_database_postgres_logged:
        _logger.info("Primary database: PostgreSQL")
        _primary_database_postgres_logged = True
    try:
        return get_postgres_conn()
    except ConnectionError as exc:
        if should_use_sqlite_fallback_after_postgres_failure():
            _activate_postgres_auto_sqlite_fallback(exc)
            return get_conn()
        raise
