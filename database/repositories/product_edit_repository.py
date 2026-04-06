"""Edição de lote (produto): regras de negócio para atributos e foto."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Union

from database.repositories.support import use_connection
from database.sql_compat import db_execute
from database.constants import DUPLICATE_SKU_BASE_ERROR_MSG
from database.product_codes import make_product_enter_code
from database.product_images import save_product_image_file
from database.sku_codec import build_product_sku_body, sku_base_body_exists
from database.sku_corrections import sku_correction_block_reason
from database.sku_master_repo import sync_sku_master_totals
from database.transactions import transaction
from utils.validators import require_non_empty_product_name

_MONEY_EPS = 0.005
_STOCK_EPS = 1e-9


def product_lot_edit_block_reason(product_id: int) -> Optional[str]:
    """
    Se retorna texto, nome / data / atributos deste lote não podem ser alterados.

    Inclui dados do **próprio lote** e do **SKU** (composição de custo, CMP, preço no
    mestre, estoque total do SKU, histórico de preço / precificação).
    A foto pode ser alterada mesmo quando esta regra bloqueia os demais campos.
    """
    pid = int(product_id)
    reasons: list[str] = []
    with use_connection(None) as conn:
        row = db_execute(conn,
            """
            SELECT stock, cost, price, pricing_locked, deleted_at, sku, tenant_id
            FROM products WHERE id = ?;
            """,
            (pid,),
        ).fetchone()
        if row is None or row["deleted_at"]:
            return "Produto não encontrado ou inativo."
        tid = row["tenant_id"]
        sku = (row["sku"] or "").strip()

        if abs(float(row["cost"] or 0)) >= _MONEY_EPS:
            reasons.append("há custo registrado no lote")
        if abs(float(row["price"] or 0)) >= _MONEY_EPS:
            reasons.append("há preço registrado no lote")
        if int(row["pricing_locked"] or 0) == 1:
            reasons.append("o lote está com precificação travada")
        sales_count = int(
            db_execute(conn,
                "SELECT COUNT(*) AS c FROM sales WHERE tenant_id = ? AND product_id = ?;",
                (tid, pid),
            ).fetchone()["c"]
        )
        if sales_count > 0:
            reasons.append(f"há {sales_count} venda(s) deste lote")
        stock_entry_count = int(
            db_execute(conn,
                """
                SELECT COUNT(*) AS c FROM stock_cost_entries
                WHERE tenant_id = ? AND product_id = ?;
                """,
                (tid, pid),
            ).fetchone()["c"]
        )
        if stock_entry_count > 0:
            reasons.append(
                f"há {stock_entry_count} entrada(s) de estoque custeada(s) ligada(s) a este lote"
            )

        if sku:
            stock_total = float(
                db_execute(conn,
                    """
                    SELECT COALESCE(SUM(stock), 0) FROM products
                    WHERE tenant_id = ? AND sku = ? AND deleted_at IS NULL;
                    """,
                    (tid, sku),
                ).fetchone()[0]
            )
            if stock_total > _STOCK_EPS:
                reasons.append("há estoque em um ou mais lotes deste SKU")

            sku_master_row = db_execute(conn,
                """
                SELECT structured_cost_total, avg_unit_cost, selling_price, deleted_at
                FROM sku_master WHERE tenant_id = ? AND sku = ?;
                """,
                (tid, sku),
            ).fetchone()
            structured_cost_total = 0.0
            if sku_master_row and not sku_master_row["deleted_at"]:
                structured_cost_total = float(
                    sku_master_row["structured_cost_total"] or 0
                )
                if abs(float(sku_master_row["avg_unit_cost"] or 0)) >= _MONEY_EPS:
                    reasons.append("há custo médio ponderado (CMP) neste SKU")
                if abs(float(sku_master_row["selling_price"] or 0)) >= _MONEY_EPS:
                    reasons.append("há preço de venda no cadastro mestre deste SKU")

            components_line_total_sum = float(
                db_execute(conn,
                    """
                    SELECT COALESCE(SUM(line_total), 0) FROM sku_cost_components
                    WHERE tenant_id = ? AND sku = ?;
                    """,
                    (tid, sku),
                ).fetchone()[0]
            )
            if (
                abs(components_line_total_sum) >= _MONEY_EPS
                or abs(structured_cost_total) >= _MONEY_EPS
            ):
                reasons.append("há composição de custo salva para este SKU")

            price_history_count = int(
                db_execute(conn,
                    "SELECT COUNT(*) AS c FROM price_history WHERE tenant_id = ? AND sku = ?;",
                    (tid, sku),
                ).fetchone()["c"]
            )
            if price_history_count > 0:
                reasons.append("há histórico de alteração de preço para este SKU")
            pricing_records_count = int(
                db_execute(conn,
                    """
                    SELECT COUNT(*) AS c FROM sku_pricing_records
                    WHERE tenant_id = ? AND sku = ?;
                    """,
                    (tid, sku),
                ).fetchone()["c"]
            )
            if pricing_records_count > 0:
                reasons.append("há registro de precificação (workflow) para este SKU")
        else:
            if abs(float(row["stock"] or 0)) > _STOCK_EPS:
                reasons.append("há estoque neste lote")
    if reasons:
        return (
            "Não é possível alterar **nome, data de registro ou atributos** deste lote porque "
            + "; ".join(reasons)
            + ". A **foto** pode ser atualizada abaixo."
        )
    return None


def update_product_lot_photo(product_id: int, data: bytes, filename: str) -> None:
    """Substitui a foto do lote (sempre permitido se o produto existir)."""
    pid = int(product_id)
    with use_connection(None) as conn:
        row = db_execute(conn,
            """
            SELECT id, tenant_id FROM products
            WHERE id = ? AND deleted_at IS NULL;
            """,
            (pid,),
        ).fetchone()
        if row is None:
            raise ValueError("Produto não encontrado.")
        tid = row["tenant_id"]
    rel = save_product_image_file(pid, data, filename)
    with use_connection(None) as conn:
        db_execute(conn,
            "UPDATE products SET product_image_path = ? WHERE tenant_id = ? AND id = ?;",
            (rel, tid, pid),
        )


def _registered_date_to_text(registered_date: Union[date, str]) -> str:
    if isinstance(registered_date, date):
        return registered_date.isoformat()
    s = str(registered_date).strip()
    if not s:
        return datetime.now().date().isoformat()
    try:
        return datetime.fromisoformat(s[:10]).date().isoformat()
    except ValueError:
        return s


def _registered_date_to_date(registered_date: Union[date, str]) -> date:
    if isinstance(registered_date, date):
        return registered_date
    return datetime.fromisoformat(_registered_date_to_text(registered_date)).date()


def update_product_lot_attributes(
    product_id: int,
    name: str,
    registered_date: Union[date, str],
    frame_color: str,
    lens_color: str,
    style: str,
    palette: str,
    gender: str,
) -> None:
    """Atualiza dados do lote; pode ajustar o SKU se o corpo codificado mudar (regras rígidas)."""
    block = product_lot_edit_block_reason(product_id)
    if block:
        raise ValueError(block)

    pid = int(product_id)
    name = (name or "").strip()
    frame_color = (frame_color or "").strip()
    lens_color = (lens_color or "").strip()
    style = (style or "").strip()
    palette = (palette or "").strip()
    gender = (gender or "").strip()
    registered_date_text = _registered_date_to_text(registered_date)
    rd_date = _registered_date_to_date(registered_date)

    require_non_empty_product_name(name)

    with use_connection(None) as conn:
        with transaction(conn, immediate=True):
            row = db_execute(conn,
                """
                SELECT id, sku, tenant_id FROM products
                WHERE id = ? AND deleted_at IS NULL;
                """,
                (pid,),
            ).fetchone()
            if row is None:
                raise ValueError("Produto não encontrado.")
            tid = row["tenant_id"]
            old_sku = (row["sku"] or "").strip()
            if not old_sku or "-" not in old_sku:
                raise ValueError("SKU inválido para edição deste cadastro.")
            seq, _old_body_rest = old_sku.split("-", 1)
            new_body = build_product_sku_body(
                name, frame_color, lens_color, gender, palette, style
            )
            new_sku = f"{seq}-{new_body}"

            duplicate_attrs_row = db_execute(conn,
                """
                SELECT id FROM products
                WHERE tenant_id = ? AND name = ? AND registered_date = ?
                  AND COALESCE(frame_color, '') = ?
                  AND COALESCE(lens_color, '') = ?
                  AND COALESCE(style, '') = ?
                  AND COALESCE(palette, '') = ?
                  AND COALESCE(gender, '') = ?
                  AND deleted_at IS NULL AND id != ?;
                """,
                (
                    tid,
                    name,
                    registered_date_text,
                    frame_color,
                    lens_color,
                    style,
                    palette,
                    gender,
                    pid,
                ),
            ).fetchone()
            if duplicate_attrs_row is not None:
                raise ValueError(DUPLICATE_SKU_BASE_ERROR_MSG)

            if sku_base_body_exists(
                conn, new_body, exclude_product_id=pid, tenant_id=tid
            ):
                raise ValueError(DUPLICATE_SKU_BASE_ERROR_MSG)

            sku_taken_row = db_execute(conn,
                """
                SELECT id FROM products
                WHERE tenant_id = ? AND sku = ? AND deleted_at IS NULL AND id != ?;
                """,
                (tid, new_sku, pid),
            ).fetchone()
            if sku_taken_row is not None:
                raise ValueError(
                    f"O código resultante `{new_sku}` já está em uso noutro lote."
                )

            if new_sku != old_sku:
                sku_block = sku_correction_block_reason(old_sku, tenant_id=tid)
                if sku_block:
                    raise ValueError(
                        "Alterar estes dados mudaria o **SKU**. Isso não é permitido enquanto "
                        "existir custo, preço, estoque ou venda associados a este código no sistema. "
                        + sku_block
                    )
                n_other = int(
                    db_execute(conn,
                        """
                        SELECT COUNT(*) AS c FROM products
                        WHERE tenant_id = ? AND sku = ? AND deleted_at IS NULL AND id != ?;
                        """,
                        (tid, old_sku, pid),
                    ).fetchone()["c"]
                )
                if n_other > 0:
                    raise ValueError(
                        "Existem **outros lotes** com o mesmo SKU; não é possível alterar "
                        "atributos que mudam o código enquanto o SKU for partilhado."
                    )
                master_rows_updated = db_execute(conn,
                    "UPDATE sku_master SET sku = ? WHERE tenant_id = ? AND sku = ?;",
                    (new_sku, tid, old_sku),
                ).rowcount
                if int(master_rows_updated or 0) < 1:
                    raise ValueError(
                        "Mestre de SKU não encontrado; não é possível concluir a alteração do código."
                    )
                db_execute(conn,
                    """
                    UPDATE sku_cost_components SET sku = ?
                    WHERE tenant_id = ? AND sku = ?;
                    """,
                    (new_sku, tid, old_sku),
                )

            new_enter = make_product_enter_code(
                product_name=name, registered_date=rd_date
            )
            db_execute(conn,
                """
                UPDATE products SET
                    name = ?, sku = ?, registered_date = ?, product_enter_code = ?,
                    frame_color = ?, lens_color = ?, style = ?, palette = ?, gender = ?
                WHERE tenant_id = ? AND id = ?;
                """,
                (
                    name,
                    new_sku,
                    registered_date_text,
                    new_enter,
                    frame_color,
                    lens_color,
                    style,
                    palette,
                    gender,
                    tid,
                    pid,
                ),
            )
            sync_sku_master_totals(conn, new_sku, tenant_id=tid)

