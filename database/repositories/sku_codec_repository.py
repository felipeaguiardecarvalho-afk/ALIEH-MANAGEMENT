"""Geração de corpo de SKU e sequência numérica persistente."""

from __future__ import annotations

import re
from typing import Optional

from database.connection import DbConnection
from database.sql_compat import db_execute, is_sqlite_conn
from database.tenancy import DEFAULT_TENANT_ID, effective_tenant_id_for_request


def _sku_alphanumeric_clean(text: object) -> str:
    # Session/widget state can occasionally be non-str; re.sub requires a string.
    s = "" if text is None else str(text)
    return re.sub(r"[^A-Za-z0-9]", "", s).upper()


def sku_segment_two_chars(source: object) -> str:
    c = _sku_alphanumeric_clean(source)
    if len(c) == 0:
        return "XX"
    if len(c) == 1:
        return c + "X"
    return c[:2]


def sku_color_segment_two_chars(color: object) -> str:
    raw = ("" if color is None else str(color)).strip()
    parts = [p.strip() for p in raw.split("/")]
    parts = [p for p in parts if p]
    if len(parts) >= 2:
        first = _sku_alphanumeric_clean(parts[0])
        second = _sku_alphanumeric_clean(parts[1])
        if first and second:
            return (first[0] + second[0])[:2]
    return sku_segment_two_chars(raw)


def format_sku_sequence_int(n: int) -> str:
    n = int(n)
    if n <= 999:
        return f"{n:03d}"
    return str(n)


def build_product_sku_body(
    product_name: object,
    *args: object,
    frame_color: object = None,
    lens_color: object = None,
    gender: object = None,
    palette: object = None,
    style: object = None,
    color: object = None,
) -> str:
    """
    Corpo do SKU (sem SEQ): [PP]-[FC]-[LC]-[GG]-[PA]-[ST].

    Formas suportadas:
    - Nova: ``(nome, frame_color, lens_color, gender, palette, style)`` (5 valores após o nome);
      ou só keywords ``frame_color=``, ``lens_color=``, etc.
    - Legada: ``(nome, color, gender, palette, style)`` (4 valores após o nome);
      ``color`` vira cor da armação; cor da lente fica ``Transparente``.
    """
    fc = frame_color
    lc = lens_color
    gg = gender
    pa = palette
    seg_st = style

    if color is not None and fc is None:
        fc = color

    n = len(args)
    if n == 5:
        if fc is None:
            fc = args[0]
        if lc is None:
            lc = args[1]
        if gg is None:
            gg = args[2]
        if pa is None:
            pa = args[3]
        if seg_st is None:
            seg_st = args[4]
    elif n == 4:
        if fc is None:
            fc = args[0]
        if lc is None:
            lc = "Transparente"
        if gg is None:
            gg = args[1]
        if pa is None:
            pa = args[2]
        if seg_st is None:
            seg_st = args[3]
    elif n not in (0,):
        raise TypeError(
            "build_product_sku_body: após o nome use 5 valores "
            "(cor armação, cor lente, gênero, paleta, estilo) ou 4 no formato legado "
            "(cor, gênero, paleta, estilo). "
            f"Recebidos {n} argumentos posicionais após o nome."
        )

    if lc is None:
        lc = ""

    pp = sku_segment_two_chars("" if product_name is None else str(product_name))
    fc_seg = sku_color_segment_two_chars(fc)
    lc_seg = sku_color_segment_two_chars(lc)
    g_seg = sku_segment_two_chars("" if gg is None else str(gg))
    pa_seg = sku_segment_two_chars("" if pa is None else str(pa))
    st_seg = sku_segment_two_chars("" if seg_st is None else str(seg_st))
    return f"{pp}-{fc_seg}-{lc_seg}-{g_seg}-{pa_seg}-{st_seg}"


def sku_base_body_after_seq(full_sku: object) -> str:
    """Parte do SKU após o primeiro hífen (corpo sem o segmento SEQ), ou o texto todo se não houver hífen."""
    s = ("" if full_sku is None else str(full_sku)).strip()
    if not s or "-" not in s:
        return s
    return s.split("-", 1)[1]


def sku_base_body_exists(
    conn: DbConnection,
    base_sku: str,
    *,
    exclude_product_id: Optional[int] = None,
    tenant_id: str | None = None,
) -> bool:
    """
    True se já existe produto (não excluído) cujo SKU, ignorando só o primeiro segmento (SEQ),
    coincide exatamente com ``base_sku``.
    """
    base_sku = (base_sku or "").strip()
    if not base_sku:
        return False
    tid = effective_tenant_id_for_request(tenant_id)
    if is_sqlite_conn(conn):
        body_expr = """
            CASE WHEN instr(TRIM(sku), '-') > 0
              THEN substr(TRIM(sku), instr(TRIM(sku), '-') + 1)
              ELSE TRIM(sku)
            END
        """
    else:
        body_expr = """
            CASE WHEN strpos(TRIM(sku), '-') > 0
              THEN substr(TRIM(sku), strpos(TRIM(sku), '-') + 1)
              ELSE TRIM(sku)
            END
        """
    sql = f"""
        SELECT 1 AS ok
        FROM products
        WHERE tenant_id = ?
          AND deleted_at IS NULL
          AND sku IS NOT NULL AND TRIM(sku) != ''
          AND (
            {body_expr}
          ) = ?
    """
    params: list = [tid, base_sku]
    if exclude_product_id is not None:
        sql += " AND id != ?"
        params.append(int(exclude_product_id))
    sql += " LIMIT 1;"
    row = db_execute(conn, sql, params).fetchone()
    return row is not None


def _next_sku_sequence(
    conn: DbConnection, tenant_id: str = DEFAULT_TENANT_ID
) -> int:
    cur = db_execute(
        conn,
        """
        UPDATE sku_sequence_counter
        SET last_value = last_value + 1
        WHERE tenant_id = ? AND id = 1
        RETURNING last_value;
        """,
        (tenant_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("Contador de sequência de SKU não inicializado.")
    return int(row["last_value"])


def sync_sku_sequence_counter_from_skus(
    conn: DbConnection, tenant_id: str = DEFAULT_TENANT_ID
) -> None:
    max_n = 0
    for row in db_execute(
        conn,
        """
        SELECT sku FROM products
        WHERE tenant_id = ? AND sku IS NOT NULL AND TRIM(sku) != '';
        """,
        (tenant_id,),
    ):
        parts = str(row["sku"]).strip().split("-")
        if parts and parts[0].isdigit():
            try:
                max_n = max(max_n, int(parts[0]))
            except ValueError:
                pass
    for row in db_execute(
        conn,
        """
        SELECT sku FROM sku_master
        WHERE tenant_id = ? AND sku IS NOT NULL AND TRIM(sku) != '';
        """,
        (tenant_id,),
    ):
        parts = str(row["sku"]).strip().split("-")
        if parts and parts[0].isdigit():
            try:
                max_n = max(max_n, int(parts[0]))
            except ValueError:
                pass
    row = db_execute(
        conn,
        "SELECT last_value FROM sku_sequence_counter WHERE tenant_id = ? AND id = 1;",
        (tenant_id,),
    ).fetchone()
    cur = int(row["last_value"] or 0) if row else 0
    db_execute(
        conn,
        "UPDATE sku_sequence_counter SET last_value = ? WHERE tenant_id = ? AND id = 1;",
        (max(max_n, cur), tenant_id),
    )
