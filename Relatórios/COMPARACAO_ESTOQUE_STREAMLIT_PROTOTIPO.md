# Comparação minuciosa: **Estoque** (Streamlit) × **`/inventory`** (protótipo Next)

**Data do relatório (versão inicial):** 2026-05-03  
**Última actualização:** 2026-05-03 — **revisão 3:** paridade estrita em filtros de stock (`int`), ordenação (nome + data como texto + id; stock por inteiro), **sem paginação** na prática (carga até 50 000 linhas), **sem cache ISR** (`revalidate = 0` + `no-store` nas leituras), remoção de **`q`** e **`low_stock_only`** (URL, UI e API).

**Âmbito:** página **Estoque** no `app.py` (`elif page == PAGE_ESTOQUE:`) frente à rota **`/inventory`** em **`web-prototype`**, com dados e mutações via **`api-prototype`** (`routes/inventory.py`, `inventory_lots_read.py`) e *server actions* em **`lib/actions/inventory.ts`**.

**Referências principais**

| Camada | Ficheiros |
|--------|-----------|
| Streamlit | `app.py` (aprox. linhas 2703–3357), `require_admin`, `fetch_products`, `apply_manual_stock_write_down`, `reset_batch_pricing_and_exclude`, `format_money`, `format_qty_display_4` |
| Protótipo UI | `web-prototype/app/(main)/inventory/page.tsx`, `inventory-filters.tsx`, `inventory-lots-interactive.tsx`, `write-down-form.tsx` |
| Protótipo API cliente | `web-prototype/lib/inventory-api.ts`, `lib/inventory-url.ts` |
| Protótipo acções | `web-prototype/lib/actions/inventory.ts` |
| API | `api-prototype/routes/inventory.py`, `api-prototype/inventory_lots_read.py` |

---

## 1. Resumo executivo

| Dimensão | Streamlit | Protótipo `/inventory` (estado actual) |
|----------|-----------|----------------------------------------|
| **Público-alvo** | Só **admin** (`require_admin()`). | **`requireAdminForPricing()`** no SSR de `page.tsx` e nas *server actions* de inventário (`manualWriteDown`, `excludeInventoryBatches`, `addStockReceipt`): com auth configurada, só **admin** (mesma política que `/pricing`); sem auth configurada mantém bypass do protótipo. |
| **Fonte de dados** | `fetch_products()`; `float(stock) > 0`. | `GET /inventory/lots` + `filter-options`; SQL `stock > 0`. |
| **Listagem** | Grelha única, **sem paginação**. | Tabela **sem barra de paginação**; pedido com `page_size` até **50 000** (paridade operacional com «tudo visível»; limite técnico na API). |
| **Filtros** | *Multiselect* por coluna; sem `q`. | Só multiseleção por coluna (CSV na URL); **sem** `q` nem *low stock* — conjunto de funcionalidades alinhado ao Streamlit. |
| **Ordenação** | Nome → `registered_date` → `product_id`; stock por `stock_qty` **int**. | SQL: nome → **`COALESCE(CAST(registered_date AS TEXT), '')`** → **`id`**; stock **por inteiro** (`CAST(COALESCE(stock,0) AS INTEGER)`) + nome. |
| **Baixa manual** | *Expander* fechado; sucesso com **stock restante** (`format_qty_display_4`). | Cartão lateral; sucesso com **`stock_after`** da API e **`formatProductStock`**; reset de formulário após sucesso (*nonce* / remount). |
| **Exclusão** | Uma linha + *dialog* Streamlit; um código. | **Radio** (uma linha com código); «Excluir lote seleccionado» + `window.confirm`; **um** código por pedido (acção + API); **sem** limite 40. |
| **Estado vazio** | Sem stock global: `st.info` + `return`. Filtros sem linhas: info + **sem** grelha nem totais. | **`globalStock.total === 0`**: mensagem Streamlit-equivalente, **sem** resto da UI operacional. **`list.total === 0`** com stock global: *«Nenhuma linha corresponde aos filtros atuais.»* — **sem** tabela nem totais; mantêm-se filtros e baixa manual. |
| **Freshness** | Dados em tempo de execução da sessão. | **`export const revalidate = 0`**; leituras `GET /inventory/lots` e `filter-options` com **`cache: 'no-store'`** (`apiPrototypeFetchRead`). |

---

## 2. Permissões (RBAC)

| Aspecto | Streamlit | Protótipo (actual) |
|---------|-----------|-------------------|
| Ver a página | **Apenas admin.** | **`requireAdminForPricing()`** no SSR antes dos dados; não-admin vê **Acesso negado** (com auth configurada). |
| Baixa manual | Página só admin. | `manualWriteDown` → `requireAdminForPricing` + `gateMutation`; **`POST /inventory/manual-write-down`** → **`get_admin_actor`**. |
| Exclusão de lote | Idem. | `excludeInventoryBatches` → `requireAdminForPricing` + `gateMutation`; **`POST /inventory/batches/exclude`** → `get_admin_actor`; corpo com **um** código validado antes do serviço. |

**Conclusão:** paridade de **acesso à página** e de **barreira admin na baixa** no API alinhadas ao espírito do Streamlit (com a nuance do modo protótipo sem auth).

---

## 3. Fonte de dados e modelo de linha (lote)

### 3.1 Streamlit

- `in_stock_products` com `float(stock) > 0`.
- `stock_qty = int(r["stock"])`, `stock_val = float(r["stock"])` para grelha e totais.

### 3.2 Protótipo / API

- `stock` em **float** na API e na tabela; totais agregados usam **`CAST(COALESCE(p.stock,0) AS INTEGER)`** por linha nas somas (custo, receita, margem, stock total) — **alinhado** ao `int` por linha do Streamlit.

### 3.3 Filtro de stock na listagem

| Tópico | Streamlit | Protótipo |
|--------|-----------|-----------|
| Stock na célula | `%.4f` no *dataframe*. | **`formatProductStock`** (até 4 decimais, estilo pt-BR). |
| Filtro «stock» (valores e correspondência) | Opções e match com **`int(stock_qty)`**. | Opções distintas e cláusula **`CAST(COALESCE(p.stock,0) AS INTEGER) IN (...)`** — **alinhado** ao Streamlit (não `ROUND(..., 4)`). |

---

## 4. Filtros e busca

### 4.1 Streamlit

- Só *multiselect* por coluna; sem busca `q`.
- Filtros vazios → sem grelha nem totais.

### 4.2 Protótipo

- Só multiseleção por coluna (lista **completa** de valores distintos); **removidos** **`q`** e **`low_stock_only`** da UI, da normalização de URL e dos parâmetros da API.
- **`list.total === 0`** com stock existente: mensagem + **sem** tabela nem totais (paridade com o `return` do Streamlit após filtros).

### 4.3 Ligação desde produtos

- O atalho «inventário» no painel de produto usa **`/inventory?skus=…`** quando existe SKU (substitui o antigo `?q=`). Sem SKU, **`/inventory`** sem query (não há no Streamlit busca livre por código de entrada na URL).

---

## 5. Ordenação

| Critério | Streamlit | Protótipo (SQL) |
|----------|-----------|-----------------|
| SKU (A–Z) | `sku`, `product_id` | `sql_order_ci(p.sku) ASC, p.id ASC` |
| Nome (A–Z) | `name`, `registered_date`, `product_id` | `sql_order_ci(p.name) ASC, COALESCE(CAST(p.registered_date AS TEXT), '') ASC, p.id ASC` |
| Stock desc / asc | Por **`stock_qty` (int)** e nome | **`CAST(COALESCE(p.stock,0) AS INTEGER)`** DESC/ASC + nome |

**Nota:** ordenação de data como **texto** aproxima `str(registered_date or "")` no Python; formatos ISO entre PG e Python tendem a ser coerentes para desempates lexicográficos.

---

## 6. Grelha / colunas apresentadas

### 6.1 Streamlit

Colunas: Nome, SKU, Cor armação, Cor lente, Estilo, Paleta, Género, Custo, Preço, Margem, Em estoque. Selecção **uma linha** na grelha.

### 6.2 Protótipo

Colunas: Produto (+ *badges* parciais), SKU, Cód. entrada, Stock, Custo, Preço, Registo. Selecção **um lote** por **radio** + exclusão única.

| Gap residual (UI / densidade de dados, não corrigido como «comportamento» puro) |
|-----|
| **Estilo**, **Paleta**, **Margem** como colunas dedicadas — ainda **ausentes** na tabela (existem nos filtros / API). |
| **Nome + atributos** agregados vs colunas separadas no Streamlit. |

---

## 7. Totais (rodapé)

- **Protótipo:** mesma fórmula conceptual que o Streamlit (**`int(stock)` por linha** × custo/preço/margem; soma de `int(stock)` para stock total), via SQL em `inventory_lots_read.search_inventory_lots`.

---

## 8. Paginação e desempenho

| Streamlit | Protótipo |
|-----------|-----------|
| Todos os registos filtrados numa vista. | **Sem UI de paginação**; `fetchPrototypeInventoryLots` envia **`page_size=50000`** por omissão; API aceita até **50 000** linhas por pedido (`page_size` default elevado na rota). |

**Limite técnico:** catálogos com mais de **50 000** lotes em stock podem ficar truncados na resposta HTTP (diferença vs Streamlit ilimitado pela memória da app). Não é cenário típico.

---

## 9. Baixa manual de stock

| Aspecto | Streamlit | Protótipo (actual) |
|---------|-----------|---------------------|
| Posição | *Expander* `expanded=False`. | Cartão lateral sempre visível (**diferença de UI**). |
| Sucesso | `format_qty_display_4` do stock restante. | Mensagem com **`formatProductStock(stock_after)`** a partir da resposta JSON da API. |
| Confirmação / reset | Nonce na sessão Streamlit. | **`formNonce`** + `key` no `<form>` e na quantidade; *ref* para não duplicar reset na mesma mensagem. |
| Rótulo do lote | Texto longo com cores e `format_qty_display_4`. | `#id · código · nome · em stock: formatProductStock` — **não** idêntico ao rótulo Streamlit. |

---

## 10. Exclusão de lote

| Aspecto | Streamlit | Protótipo (actual) |
|---------|-----------|---------------------|
| Selecção | Uma linha na grelha. | **Radio** — uma linha com código. |
| Confirmação | *Dialog* Streamlit com texto longo. | `window.confirm` + texto dinâmico com código (fluxo bloqueante até o utilizador responder). |
| Serviço | `reset_batch_pricing_and_exclude` (um código). | Idem, **um** código por pedido (validação na acção e na rota). |
| Limite 40 | N/A | **Removido** (e irrelevante com exclusão única). |

---

## 11. Estilos e layout (Streamlit)

- CSS injectado no Streamlit — **só UX**; sem impacto funcional na comparação.

---

## 12. `revalidate` e cache

- **`export const revalidate = 0`** em `page.tsx` (sem ISR de 30 s na listagem).
- Leituras **`GET /inventory/lots`** e **`GET /inventory/lots/filter-options`** com **`cache: 'no-store'`** no *fetch* do servidor.
- **`revalidatePath("/inventory")`** mantido após mutações (baixa / exclusão).

---

## 13. Matriz de paridade (resumo)

| Funcionalidade | Streamlit | Protótipo (actual) |
|----------------|-----------|---------------------|
| Página só admin | ✅ | ✅ (`requireAdminForPricing` + SSR) |
| Lotes com stock > 0 | ✅ | ✅ |
| Filtros por dimensões | ✅ | ✅ (sem extras `q` / low stock) |
| Sem linhas após filtros | Sem grelha/totais | ✅ (sem tabela nem totais) |
| Sem stock em lado nenhum | Info + fim | ✅ (cartão só com mensagem) |
| Ordenação Nome (desempates) | ✅ | ✅ (nome + data como texto + id) |
| Ordenação por stock (inteiro) | ✅ | ✅ |
| Totais com int por linha | ✅ | ✅ (SQL `CAST`) |
| Filtro de stock por inteiro | ✅ | ✅ |
| Colunas estilo / paleta / margem | ✅ | ⚠️ (ainda não na tabela) |
| Paginação na UI | ❌ | ✅ alinhado (lista completa até limite API) |
| Dados «frescos» (sem ISR 30s) | N/A | ✅ |
| Baixa (serviço + stock final + API admin) | ✅ | ✅ |
| Exclusão um lote + confirmação | ✅ | ✅ (modelo radio + confirm) |
| Busca `q` | ❌ | ❌ (removida) |
| Filtro stock ≤ 5 | ❌ | ❌ (removido) |

---

## 14. Conclusão

Após a **revisão 3**, o protótipo aproxima-se ainda mais do Streamlit em **comportamento funcional**: **filtro de stock por inteiro** (opções e `IN`), **ordenação por stock em inteiro**, **desempate de nome com data como texto**, **ausência de paginação na experiência**, **dados sem cache de página de 30 s**, e **remoção** das funcionalidades extra **`q`** e ***low stock***. **Diferenças residuais** concentram-se sobretudo em **UI** (*expander*, *dialog* vs `confirm`, colunas extra na tabela, rótulos da baixa manual) e no **limite técnico** de 50 000 linhas por pedido HTTP.

---

## 15. Sugestões opcionais (baixa prioridade / UX)

1. Colunas **Estilo**, **Paleta**, **Margem** na tabela, se se quiser densidade de dados idêntica ao *dataframe* Streamlit.  
2. *Expander* ou secção colapsável para a baixa manual.  
3. Se no futuro o volume ultrapassar 50 000 lotes, avaliar *streaming*, cursor ou endpoint dedicado (fora do âmbito actual de paridade com Streamlit).

---

## 16. Registo de alterações

### Revisão 3 (paridade estrita)

| Área | Alteração |
|------|-----------|
| `inventory_lots_read.py` | Filtro `stocks` com `CAST(COALESCE(stock,0) AS INTEGER)`; opções de filtro de stock por inteiro; remoção de `q` e `low_stock_only`; ordenação nome com `COALESCE(CAST(registered_date AS TEXT), '')`; stock asc/desc por inteiro; `limit` máx. 50 000. |
| `routes/inventory.py` | Remoção de parâmetros `q` e `low_stock_only`; `page_size` default/máx. 50 000. |
| `inventory-url.ts` | Remoção de `q`, `low_stock_only`, `page`, `page_size` da URL; remoção de `mergeInventoryLotsQuery`. |
| `inventory-api.ts` | `fetchPrototypeInventoryLots` com paging opcional; leituras com `apiPrototypeFetchRead` + `cache: 'no-store'`. |
| `page.tsx` | `revalidate = 0`; sem barra de paginação; contagens globais com `page_size: 1`; lista e baixa com carga completa (omissão 50 000). |
| `inventory-filters.tsx` | Remoção de busca `q`, *low stock*, *por página*, `InventoryPaginationBar`. |
| `product-detail-aside.tsx` | Link para `/inventory?skus=…` em vez de `?q=`. |

### Revisão 2 (resumo)

| Área | Alteração |
|------|-----------|
| `page.tsx` | `requireAdminForPricing`; `globalStock` para deteção de zero stock; ramos sem grelha/totais/paginação; mensagens alinhadas ao Streamlit. |
| `inventory_lots_read.py` | Totais com `CAST(stock AS INTEGER)`; `ORDER BY` nome + `registered_date` + `id`. |
| `routes/inventory.py` | `manual-write-down` com `get_admin_actor`; `batches/exclude` processa **um** código após validação. |
| `inventory-filters.tsx` | Remoção do limite 120; `formatProductStock` no total de stock. |
| `inventory-lots-interactive.tsx` | Radio + um código; `formatProductStock`; reset da selecção após sucesso. |
| `write-down-form.tsx` | `formatProductStock` nos rótulos; reset pós-sucesso com *nonce* / *ref*. |
| `lib/actions/inventory.ts` | `requireAdminForPricing`; mensagem de baixa com `stock_after`; exclusão só um código. |

---

*Fim do relatório.*
