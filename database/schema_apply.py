"""Aplicar :file:`schema.sql` ao PostgreSQL (ex.: Supabase) numa única transacção.

:func:`reset_postgres_schema` limpa ``public`` (CASCADE) e permissões mínimas antes de um
apply + migração completa.

Não altera SQLite. Usa :func:`database.connection.get_postgres_conn`. Cada instrução do
script corre dentro de :meth:`psycopg.Connection.transaction` com **cursor novo** por
instrução (sem reuso), para o pooler Supabase / ``DuplicatePreparedStatement``.

O ficheiro SQL já utiliza ``CREATE TABLE IF NOT EXISTS`` / ``CREATE INDEX IF NOT EXISTS`` /
``ON CONFLICT`` onde aplicável para idempotência.

Executar manualmente quando necessário, por exemplo::

    python -m database.schema_apply
"""

from __future__ import annotations

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


def reset_postgres_schema() -> None:
    """
    Elimina o schema ``public`` (CASCADE), recria-o e restaura permissões mínimas padrão.

    Usar antes de :func:`apply_schema_to_postgres` + migração de dados para uma base limpa.
    Executa numa única transacção (rollback em caso de erro).
    """
    _logger.info(
        "PostgreSQL: a executar DROP SCHEMA public CASCADE; CREATE SCHEMA public; …"
    )
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
                        cur.execute(stmt)
    except Exception:
        _logger.exception("reset_postgres_schema falhou (rollback)")
        raise

    _logger.info("Postgres schema resetado com sucesso")


def list_public_base_tables(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        rows = cur.fetchall()
    names: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            names.append(str(row["table_name"]))
        else:
            names.append(str(row[0]))
    return names


def apply_schema_to_postgres(*, schema_path: Path | None = None) -> list[str]:
    """
    Lê ``schema.sql`` da raiz do projecto, executa no Postgres dentro de uma transacção.

    Em caso de erro: *rollback* completo e log com traceback.

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
    _logger.info("Applying schema to PostgreSQL...")
    try:
        with get_postgres_conn() as conn:
            with conn.transaction():
                for stmt in statements:
                    _logger.info("Executing statement with isolated cursor")
                    with conn.cursor() as cur:
                        cur.execute(stmt)
            tables = list_public_base_tables(conn)
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    apply_schema_to_postgres()
