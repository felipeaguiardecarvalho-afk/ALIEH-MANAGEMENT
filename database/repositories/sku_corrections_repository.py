"""Exclusão definitiva de SKU permitida só sem estoque, custo, preço ou vendas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from database.repositories.support import use_connection
from database.sql_compat import db_execute
from database.product_images import delete_product_image_file
from database.tenancy import effective_tenant_id_for_request
from database.transactions import transaction
from utils.critical_log import log_critical_event

_MONEY_EPS = 0.005
_STOCK_EPS = 1e-9


def _money_nonzero(x) -> bool:
    return abs(float(x or 0)) >= _MONEY_EPS


def _stock_nonzero(x) -> bool:
    return abs(float(x or 0)) > _STOCK_EPS


def sku_correction_block_reason(
    sku: str, tenant_id: str | None = None
) -> Optional[str]:
    """
    Se retorna texto, o SKU não pode ser excluído (cadastro já usado em estoque/custo/preço/vendas).
    """
    sku = (sku or "").strip()
    if not sku:
        return "SKU inválido."

    tid = effective_tenant_id_for_request(tenant_id)
    reasons: list[str] = []

    with use_connection(None) as conn:
        row = db_execute(conn,
            """
            SELECT COALESCE(SUM(stock), 0) AS st,
                   COALESCE(MAX(CASE WHEN pricing_locked = 1 THEN 1 ELSE 0 END), 0) AS pl,
                   COALESCE(MAX(CASE WHEN ABS(COALESCE(cost, 0)) >= ? THEN 1 ELSE 0 END), 0) AS pc,
                   COALESCE(MAX(CASE WHEN ABS(COALESCE(price, 0)) >= ? THEN 1 ELSE 0 END), 0) AS pp
            FROM products
            WHERE tenant_id = ? AND sku = ? AND deleted_at IS NULL;
            """,
            (_MONEY_EPS, _MONEY_EPS, tid, sku),
        ).fetchone()
        if row:
            if _stock_nonzero(row["st"]):
                reasons.append("há estoque em um ou mais lotes deste SKU")
            if int(row["pl"] or 0) == 1:
                reasons.append("há lote com precificação travada")
            if int(row["pc"] or 0) == 1:
                reasons.append("há custo de lote em `products.cost`")
            if int(row["pp"] or 0) == 1:
                reasons.append("há preço de lote em `products.price`")

        sm = db_execute(conn,
            """
            SELECT avg_unit_cost, selling_price, structured_cost_total, deleted_at
            FROM sku_master WHERE tenant_id = ? AND sku = ?;
            """,
            (tid, sku),
        ).fetchone()
        if sm and not sm["deleted_at"]:
            if _money_nonzero(sm["avg_unit_cost"]):
                reasons.append("há custo médio ponderado (CMP) no mestre de SKU")
            if _money_nonzero(sm["selling_price"]):
                reasons.append("há preço de venda no mestre de SKU")
            if _money_nonzero(sm["structured_cost_total"]):
                reasons.append("há composição de custo planejada (total estruturado)")

        n = int(
            db_execute(conn,
                "SELECT COUNT(*) AS c FROM stock_cost_entries WHERE tenant_id = ? AND sku = ?;",
                (tid, sku),
            ).fetchone()["c"]
        )
        if n > 0:
            reasons.append(
                f"há {n} registro(s) de entrada de estoque (custo de recebimento)"
            )

        n = int(
            db_execute(conn,
                "SELECT COUNT(*) AS c FROM price_history WHERE tenant_id = ? AND sku = ?;",
                (tid, sku),
            ).fetchone()["c"]
        )
        if n > 0:
            reasons.append("há histórico de alteração de preço para este SKU")

        n = int(
            db_execute(conn,
                "SELECT COUNT(*) AS c FROM sku_pricing_records WHERE tenant_id = ? AND sku = ?;",
                (tid, sku),
            ).fetchone()["c"]
        )
        if n > 0:
            reasons.append("há registro(s) na precificação por workflow para este SKU")

        lt = db_execute(conn,
            """
            SELECT COALESCE(SUM(line_total), 0) AS t
            FROM sku_cost_components WHERE tenant_id = ? AND sku = ?;
            """,
            (tid, sku),
        ).fetchone()
        if lt and _money_nonzero(lt["t"]):
            reasons.append("há linhas de composição de custo com valor")

        n = int(
            db_execute(conn,
                """
                SELECT COUNT(*) AS c FROM sales
                WHERE tenant_id = ?
                  AND (TRIM(COALESCE(sku, '')) = ?
                   OR product_id IN (SELECT id FROM products WHERE tenant_id = ? AND sku = ?));
                """,
                (tid, sku, tid, sku),
            ).fetchone()["c"]
        )
        if n > 0:
            reasons.append(f"há {n} venda(s) vinculada(s) a este SKU")

    if reasons:
        return (
            "Não é possível excluir este SKU porque "
            + "; ".join(reasons)
            + "."
        )
    return None


def hard_delete_sku_catalog(
    sku: str,
    *,
    note: str = "",
    user_id: Optional[str] = None,
    tenant_id: str | None = None,
) -> int:
    """
    Remove do banco todos os lotes (`products`) e o mestre (`sku_master`) deste SKU,
    além das linhas de composição de custo. Só permitido se `sku_correction_block_reason` for vazio.
    Retorna quantos registros em `products` foram apagados.
    """
    sku = sku.strip()
    tid = effective_tenant_id_for_request(tenant_id)
    block = sku_correction_block_reason(sku, tenant_id=tid)
    if block:
        raise ValueError(block)
    now = datetime.now().isoformat(timespec="seconds")
    note_txt = (note or "").strip()[:500]
    deleted_by = (user_id or "").strip() or "app"
    with use_connection(None) as conn:
        with transaction(conn, immediate=True):
            for r in db_execute(conn,
                "SELECT product_image_path FROM products WHERE tenant_id = ? AND sku = ?;",
                (tid, sku),
            ).fetchall():
                delete_product_image_file(r["product_image_path"])
            db_execute(conn,
                "DELETE FROM sku_cost_components WHERE tenant_id = ? AND sku = ?;",
                (tid, sku),
            )
            cur = db_execute(conn,
                "DELETE FROM products WHERE tenant_id = ? AND sku = ?;",
                (tid, sku),
            )
            n = int(cur.rowcount or 0)
            if n < 1:
                raise ValueError("Nenhum produto encontrado para este SKU.")
            db_execute(conn,
                "DELETE FROM sku_master WHERE tenant_id = ? AND sku = ?;",
                (tid, sku),
            )
            db_execute(conn,
                """
                INSERT INTO sku_deletion_audit (tenant_id, sku, deleted_at, deleted_by, note)
                VALUES (?, ?, ?, ?, ?);
                """,
                (tid, sku, now, deleted_by, note_txt or "hard_delete_sku_catalog"),
            )
        log_critical_event(
            "data_deletion",
            user_id=user_id,
            entity="sku_catalog_hard_delete",
            sku=sku,
            products_removed=n,
            note=note_txt or "hard_delete_sku_catalog",
        )
        return n
