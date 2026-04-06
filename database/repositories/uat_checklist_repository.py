"""Persistência do checklist UAT manual (secção A.4) por inquilino."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from database.repositories.support import use_connection
from database.sql_compat import db_execute

# IDs e textos alinhados ao relatório UAT (formalização de negócio).
UAT_MANUAL_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "UAT-M-01",
        "Login administrador",
        "Login **admin** — sucesso; sidebar e páginas visíveis.",
    ),
    (
        "UAT-M-02",
        "Login operador e restrição de páginas",
        "Login **operator** — sucesso; páginas **Precificação** e **Estoque** bloqueadas ou "
        "inacessíveis conforme política.",
    ),
    (
        "UAT-M-03",
        "Venda completa como operador",
        "Como **operator**: registar **venda** completa (SKU, cliente, quantidade, pagamento) — "
        "sucesso e stock coerente.",
    ),
    (
        "UAT-M-04",
        "Operador sem permissões sensíveis",
        "Como **operator**: **não** conseguir gravar precificação, entrada de custos definitiva, "
        "nem cadastro de produto (botões desactivados ou acesso negado).",
    ),
    (
        "UAT-M-05",
        "Cadastro de produto (admin)",
        "Como **admin**: cadastrar produto mínimo; confirmar aparição na busca por SKU.",
    ),
    (
        "UAT-M-06",
        "Custos e entrada de stock (admin)",
        "Como **admin**: fluxo **Custos** — gravar composição; entrada de stock com confirmação — "
        "CMP actualizado.",
    ),
    (
        "UAT-M-07",
        "Precificação e preço em vendas (admin)",
        "Como **admin**: **Precificação** — salvar registo; **Vendas** usar preço alvo activo.",
    ),
    (
        "UAT-M-08",
        "Clientes — exclusão e regra de vendas (admin)",
        "Como **admin**: **Clientes** — exclusão com confirmação; tentativa com venda associada deve "
        "falhar (regra de negócio).",
    ),
    (
        "UAT-M-09",
        "Estoque — exclusão de lote (admin)",
        "Como **admin**: **Estoque** — exclusão de lote com diálogo de confirmação.",
    ),
    (
        "UAT-M-10",
        "Logout e sessão",
        "Logout; tentativa de acção sem sessão — comportamento esperado (`ensure_authenticated_or_stop`).",
    ),
    (
        "UAT-M-11",
        "Modo sem autenticação (dev aberto)",
        "Ambiente **sem** autenticação configurada: confirmar com equipa se é aceite; documentar risco "
        "(todas as operações disponíveis).",
    ),
)

UAT_STATUS_ORDER: tuple[str, ...] = ("pending", "pass", "fail", "blocked", "na")

UAT_STATUS_LABELS: dict[str, str] = {
    "pending": "Pendente",
    "pass": "Passou",
    "fail": "Falhou",
    "blocked": "Bloqueado",
    "na": "N/A",
}


def fetch_map_for_tenant(tenant_id: str) -> dict[str, dict[str, Any]]:
    """Devolve ``test_id`` → linha mais recente persistida."""
    tid = (tenant_id or "").strip() or "default"
    with use_connection(None) as conn:
        rows = db_execute(conn,
            """
            SELECT test_id, status, notes, result_recorded_at,
                   recorded_by_username, recorded_by_user_id, recorded_by_role, updated_at
            FROM uat_manual_checklist
            WHERE tenant_id = ?;
            """,
            (tid,),
        ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        out[str(r["test_id"])] = {k: r[k] for k in r.keys()}
    return out


def upsert_uat_record(
    tenant_id: str,
    test_id: str,
    status: str,
    notes: str,
    *,
    username: str,
    user_id: str,
    role: str,
) -> None:
    tid = (tenant_id or "").strip() or "default"
    tid_key = (test_id or "").strip()
    st = (status or "pending").strip().lower()
    if st not in UAT_STATUS_ORDER:
        st = "pending"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rec_at = now if st != "pending" else None
    notes_clean = (notes or "").strip() or None
    uname = (username or "").strip() or None
    uid = (user_id or "").strip() or None
    rrole = (role or "").strip() or None

    with use_connection(None) as conn:
        db_execute(conn,
            """
            INSERT INTO uat_manual_checklist (
                tenant_id, test_id, status, notes, result_recorded_at,
                recorded_by_username, recorded_by_user_id, recorded_by_role, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, test_id) DO UPDATE SET
                status = excluded.status,
                notes = excluded.notes,
                result_recorded_at = excluded.result_recorded_at,
                recorded_by_username = excluded.recorded_by_username,
                recorded_by_user_id = excluded.recorded_by_user_id,
                recorded_by_role = excluded.recorded_by_role,
                updated_at = excluded.updated_at;
            """,
            (tid, tid_key, st, notes_clean, rec_at, uname, uid, rrole, now),
        )
