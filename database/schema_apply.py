"""Aplicar :file:`schema.sql` ao PostgreSQL (ex.: Supabase) numa única transacção.

:func:`reset_postgres_schema` limpa ``public`` (CASCADE) e permissões mínimas antes de um
apply + migração completa.

Não altera SQLite. Usa :func:`database.connection.get_postgres_conn`. Cada instrução do
script corre dentro de :meth:`psycopg.Connection.transaction` com **cursor novo** por
instrução (sem reuso), para o pooler Supabase / ``DuplicatePreparedStatement``.

O ficheiro SQL já utiliza ``CREATE TABLE IF NOT EXISTS`` / ``CREATE INDEX IF NOT EXISTS`` /
``ON CONFLICT`` onde aplicável para idempotência.

CLI exemplos::

    python -m database.schema_apply
    python -m database.schema_apply --full-reset          # DROP public + aplicar schema.sql
    python -m database.schema_apply --full-reset --supabase  # força grants API (anon/authenticated/service_role)

**Supabase:** use ligação com utilizador ``postgres`` (porta **5432** directa) no ``DATABASE_URL`` para DDL
pesado; o reset evita ``GRANT CREATE ON SCHEMA public TO PUBLIC`` (bloqueado nas políticas actuais).
Após ``schema.sql``, são aplicados grants aos roles da API. **Apaga todos os dados** em ``public``.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Raiz do repositório (app.py está um nível acima de database/); não sobrescreve env existente.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
logging.getLogger(__name__).info(
    "DATABASE_URL detected: %s",
    "yes" if (os.environ.get("DATABASE_URL") or "").strip() else "no",
)

from database.config import BASE_DIR
from database.connection import get_postgres_conn

_logger = logging.getLogger(__name__)

_SCHEMA_FILENAME = "schema.sql"

_SUPABASE_DSN_MARKERS = (
    "supabase.co",
    "pooler.supabase.com",
)


def _dsn_env_hints_supabase() -> bool:
    for key in ("DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_DSN", "ALIEH_DATABASE_URL"):
        v = (os.environ.get(key) or "").lower()
        if any(m in v for m in _SUPABASE_DSN_MARKERS):
            return True
    return False


def _try_parse_dollar_delimiter(sql: str, pos: int) -> tuple[str, int] | None:
    """Se ``sql[pos]`` inicia ``$tag$`` (tag opcional), devolve ``(tag, pos_após_fecho)``."""
    n = len(sql)
    if pos >= n or sql[pos] != "$":
        return None
    j = pos + 1
    while j < n and sql[j] != "$":
        j += 1
    if j >= n:
        return None
    tag = sql[pos + 1 : j]
    return (tag, j + 1)


def _split_postgres_sql_statements(sql: str) -> list[str]:
    """Divide o script em instruções terminadas em ``;``, respeitando comentários e ``$$``.

    Evita partir no ``;`` interior a blocos PL/pgSQL dollar-quoted.
    """
    n = len(sql)
    i = 0
    stmt_start = 0
    in_line_comment = False
    in_block_comment = False
    in_single = False
    in_double = False
    dollar_tag: str | None = None
    statements: list[str] = []

    while i < n:
        c = sql[i]
        if in_line_comment:
            if c == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if c == "*" and i + 1 < n and sql[i + 1] == "/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_single:
            if c == "'" and i + 1 < n and sql[i + 1] == "'":
                i += 2
            elif c == "'":
                in_single = False
                i += 1
            else:
                i += 1
            continue
        if in_double:
            if c == '"' and i + 1 < n and sql[i + 1] == '"':
                i += 2
            elif c == '"':
                in_double = False
                i += 1
            else:
                i += 1
            continue
        if dollar_tag is not None:
            if c == "$":
                parsed = _try_parse_dollar_delimiter(sql, i)
                if parsed is not None:
                    tag, endpos = parsed
                    if tag == dollar_tag:
                        dollar_tag = None
                        i = endpos
                        continue
            i += 1
            continue

        if c == "-" and i + 1 < n and sql[i + 1] == "-":
            in_line_comment = True
            i += 2
            continue
        if c == "/" and i + 1 < n and sql[i + 1] == "*":
            in_block_comment = True
            i += 2
            continue
        if c == "'":
            in_single = True
            i += 1
            continue
        if c == '"':
            in_double = True
            i += 1
            continue
        if c == "$":
            parsed = _try_parse_dollar_delimiter(sql, i)
            if parsed is not None:
                dollar_tag, i = parsed
                continue

        if c == ";":
            piece = sql[stmt_start:i].strip()
            if piece:
                statements.append(piece)
            stmt_start = i + 1
        i += 1

    tail = sql[stmt_start:].strip()
    if tail:
        statements.append(tail)
    return statements


def reset_postgres_schema(*, supabase: bool | None = None) -> None:
    """
    Elimina o schema ``public`` (CASCADE), recria-o e restaura permissões mínimas.

    Usar antes de :func:`apply_schema_to_postgres` para uma base limpa.
    ``supabase=None`` detecta pelo DSN no ambiente (host Supabase).

    Executa numa única transacção (rollback em caso de erro).
    """
    use_sb = _dsn_env_hints_supabase() if supabase is None else supabase
    _logger.info(
        "PostgreSQL: DROP/CREATE public (modo supabase=%s)…",
        use_sb,
    )
    if use_sb:
        # Evita GRANT CREATE TO PUBLIC — frequentemente rejeitado nas instâncias Supabase.
        statements = (
            "DROP SCHEMA IF EXISTS public CASCADE",
            "CREATE SCHEMA public",
            "ALTER SCHEMA public OWNER TO CURRENT_USER",
            "GRANT USAGE ON SCHEMA public TO postgres",
            "GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role",
        )
    else:
        statements = (
            "DROP SCHEMA IF EXISTS public CASCADE",
            "CREATE SCHEMA public",
            "GRANT USAGE ON SCHEMA public TO PUBLIC",
            "GRANT CREATE ON SCHEMA public TO PUBLIC",
            "ALTER SCHEMA public OWNER TO CURRENT_USER",
        )
    try:
        with get_postgres_conn() as conn:
            with conn.transaction():
                for stmt in statements:
                    _logger.info("Executing statement with isolated cursor")
                    with conn.cursor() as cur:
                        cur.execute(stmt, prepare=False)
    except Exception:
        _logger.exception("reset_postgres_schema falhou (rollback)")
        raise

    _logger.info("Postgres schema resetado com sucesso")


def _supabase_api_grant_sql() -> tuple[str, ...]:
    """Grants para PostgREST / clientes Supabase após criar objectos em ``public``."""
    # DEFAULT PRIVILEGES scoped ao dono dos objectos criados (ligação actual).
    return (
        "GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role",
        "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO anon, authenticated, service_role",
        "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated, service_role",
        "GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO anon, authenticated, service_role",
        (
            "ALTER DEFAULT PRIVILEGES FOR ROLE CURRENT_USER IN SCHEMA public "
            "GRANT ALL ON TABLES TO anon, authenticated, service_role"
        ),
        (
            "ALTER DEFAULT PRIVILEGES FOR ROLE CURRENT_USER IN SCHEMA public "
            "GRANT ALL ON SEQUENCES TO anon, authenticated, service_role"
        ),
        (
            "ALTER DEFAULT PRIVILEGES FOR ROLE CURRENT_USER IN SCHEMA public "
            "GRANT ALL ON FUNCTIONS TO anon, authenticated, service_role"
        ),
    )


def _apply_supabase_api_grants(conn) -> None:
    _logger.info("A aplicar grants Supabase (anon, authenticated, service_role) em public…")
    with conn.transaction():
        for stmt in _supabase_api_grant_sql():
            with conn.cursor() as cur:
                cur.execute(stmt, prepare=False)
    _logger.info("Grants Supabase aplicados.")


def list_public_base_tables(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            prepare=False,
        )
        rows = cur.fetchall()
    names: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            names.append(str(row["table_name"]))
        else:
            names.append(str(row[0]))
    return names


def apply_schema_to_postgres(
    *,
    schema_path: Path | None = None,
    supabase_grants: bool | None = None,
) -> list[str]:
    """
    Lê ``schema.sql`` da raiz do projecto, executa no Postgres dentro de uma transacção.

    Em caso de erro: *rollback* completo e log com traceback.
    Com ``supabase_grants`` (ou detecção automática de DSN Supabase), aplica grants API após o DDL.

    Returns:
        Lista ordenada de nomes de tabelas base em ``public`` após o sucesso.

    Raises:
        FileNotFoundError: se ``schema.sql`` não existir.
        ConnectionError / psycopg.Error: falha de ligação ou SQL.
    """
    path = schema_path if schema_path is not None else (BASE_DIR / _SCHEMA_FILENAME)
    if not path.is_file():
        raise FileNotFoundError(f"Schema file not found: {path}")

    script = path.read_text(encoding="utf-8")
    statements = _split_postgres_sql_statements(script)
    do_grants = _dsn_env_hints_supabase() if supabase_grants is None else supabase_grants
    _logger.info("Applying schema to PostgreSQL…")
    try:
        with get_postgres_conn() as conn:
            with conn.transaction():
                for stmt in statements:
                    _logger.info("Executing statement with isolated cursor")
                    with conn.cursor() as cur:
                        cur.execute(stmt, prepare=False)
            tables = list_public_base_tables(conn)
            if do_grants:
                _apply_supabase_api_grants(conn)
    except Exception:
        _logger.exception("Schema apply failed (transaction rolled back)")
        raise

    _logger.info("Schema applied successfully")
    _logger.info(
        "PostgreSQL public schema: %d base table(s): %s",
        len(tables),
        ", ".join(tables) if tables else "(none)",
    )
    return tables


def full_reset_and_apply_schema(
    *,
    schema_path: Path | None = None,
    supabase: bool | None = None,
    supabase_grants: bool | None = None,
) -> list[str]:
    """``reset_postgres_schema`` + ``apply_schema_to_postgres`` — base ``public`` vazia + DDL completo."""
    reset_postgres_schema(supabase=supabase)
    return apply_schema_to_postgres(
        schema_path=schema_path,
        supabase_grants=supabase if supabase_grants is None else supabase_grants,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Aplicar schema.sql ao PostgreSQL (Supabase). Cuidado: --full-reset apaga dados em public."
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="Apenas DROP SCHEMA public + recriar (sem aplicar schema.sql)",
    )
    p.add_argument(
        "--full-reset",
        action="store_true",
        help="Reset completo + aplicar schema.sql (+ grants Supabase se DSN ou --supabase)",
    )
    p.add_argument(
        "--supabase",
        action="store_true",
        help="Tratar como Supabase: reset sem GRANT … TO PUBLIC; aplicar grants API após schema",
    )
    p.add_argument(
        "--no-supabase-grants",
        action="store_true",
        help="Não executar grants anon/authenticated/service_role após o DDL",
    )
    return p


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    args = _build_arg_parser().parse_args()
    sb = True if args.supabase else None
    grants: bool | None = False if args.no_supabase_grants else sb

    if args.full_reset:
        full_reset_and_apply_schema(supabase=sb, supabase_grants=grants)
    elif args.reset:
        reset_postgres_schema(supabase=sb)
    else:
        apply_schema_to_postgres(supabase_grants=grants)
