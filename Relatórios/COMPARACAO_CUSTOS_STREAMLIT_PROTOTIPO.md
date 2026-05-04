# Comparação minuciosa: **Custos** (Streamlit produção) × **`/costs`** (protótipo Next)

**Data do relatório:** 2026-05-03  
**Última actualização:** 2026-05-03 — alinhamento de textos e títulos ao `app.py`; tabela de valorização com **Atualizado** e rótulos Streamlit; guia sem SKUs com link **Produtos**; **Etapas 1–5** na entrada de stock (cartão + rótulos no formulário); componentes de entrada em **tabela**; formulários em `app/(main)/costs/components/`.

**Âmbito:** página **Custos** no `app.py` (bloco `elif page == PAGE_CUSTOS:`) frente à rota **`/costs`** em **`web-prototype`**, consumindo **`api-prototype`** (`/costs/*`, `/inventory/stock-receipt`, `POST /products/sku/cost-structure`).

**Referências principais**

| Camada | Ficheiros |
|--------|-----------|
| Streamlit | `app.py` (aprox. linhas 1593–1972), constantes `COSTING_STRUCT_PICK_*`, `SKU_COST_COMPONENT_DEFINITIONS` via `services.domain_constants` / `database.constants` |
| Protótipo UI | `web-prototype/app/(main)/costs/page.tsx`, `web-prototype/app/(main)/costs/components/cost-structure-form.tsx`, `web-prototype/app/(main)/costs/components/stock-receipt-form.tsx`, `format-qty.ts`, `loading.tsx` |
| Protótipo dados | `web-prototype/lib/costs-api.ts`, `lib/actions/costs.ts`, `lib/actions/inventory.ts`, `lib/domain.ts`, `lib/costs-types.ts` |
| API | `api-prototype/routes/costs.py`, `api-prototype/routes/inventory.py` (`POST /stock-receipt`) |

---

## 1. Resumo executivo

| Dimensão | Streamlit (produção) | Protótipo `/costs` |
|----------|----------------------|---------------------|
| **Objetivo** | Definir **composição de custo planeada** por SKU; **entrada de stock** ao custo unitário estruturado persistido; ver **valorização** por SKU; **histórico** de movimentos de custo de stock. | Idem: mesma origem de regras na API Python e nos mesmos repositórios. |
| **Paridade de regras** | Alta: parsers (`parse_cost_quantity_text`, `parse_cost_unit_price_value`), componentes, custo unitário estruturado, `add_stock_receipt`. | **Alta no servidor**; validação de quantidade de entrada também exposta via **`POST /costs/parse-quantity-text`** para feedback ao vivo sem duplicar lógica em TS. |
| **Paridade visual / fluxo** | Página vertical: composição → valorização → entrada → histórico. | **Mesma ordem** (cartões empilhados); *copy* de títulos e *captions* principais alinhados ao Streamlit (ver §3). |
| **RBAC** | Botões «Salvar composição» e «Finalizar entrada» **desactivados** para não-admin; `require_admin()` na submissão. | **Igual:** `SubmitButton` **desactivado** quando `!isAdmin` (com *title* «Apenas administradores.»); *server actions* com `requireAdmin()` + `gateMutation()`. |

---

## 2. Arquitectura e fluxo de dados

### 2.1 Streamlit

- O código Python chama directamente: `fetch_sku_master_rows`, `fetch_product_triple_label_by_sku`, `fetch_sku_cost_components_for_sku`, `save_sku_cost_structure`, `fetch_product_batches_for_sku`, `get_persisted_structured_unit_cost`, `add_stock_receipt`, `fetch_recent_stock_cost_entries`, etc.
- Toda a persistência e validação ocorrem **no processo Streamlit** com acesso à base.

### 2.2 Protótipo

- O **SSR** do Next obtém listas via `GET /costs/sku-masters`, `GET /costs/sku-options`, `GET /costs/stock-cost-history`.
- O cliente chama *server actions* que por sua vez chamam `apiPrototypeFetch` / `apiPrototypeFetchRead` sobre **`/costs/composition`**, **`/costs/preview-composition`**, **`/costs/parse-quantity-text`**, **`/costs/stock-entry`**, **`POST /products/sku/cost-structure`**, **`POST /inventory/stock-receipt`**.
- A lógica de negócio de escrita continua em **`services.product_service`** / repositórios, invocados pela FastAPI — **não** duplicada em TypeScript além de montagem de payloads e formatação de apresentação.

### 2.3 `hasDatabaseUrl` nas *server actions* (resolvido)

- No ficheiro **`web-prototype/lib/actions/inventory.ts`** **já não existe** referência a `hasDatabaseUrl`: `addStockReceipt`, `manualWriteDown` e `excludeInventoryBatches` passam **directamente** pela API (`apiPrototypeFetch`), como a composição em **`lib/actions/costs.ts`** (`saveCostStructure`).

### 2.4 Ambiente local (protótipo)

- Para o SSR e as *server actions* alcançarem a FastAPI, **`API_PROTOTYPE_URL`** (ex.: `http://127.0.0.1:8000`) deve estar definido em **`web-prototype/.env.local`**, em linha com **`npm run dev:api`** na raiz do repositório. Sem isso, as páginas que leem custos via API mostram erro de configuração.

---

## 3. Ordem e estrutura da página

| Secção | Streamlit (ordem no ecrã) | Protótipo `/costs` |
|--------|---------------------------|---------------------|
| Título | `### Custos` | *Page hero* «Custos» |
| Texto introdutório global | `st.caption` (composição / CMP / Precificação) | `PageHero.description` — texto equivalente ao *caption* inicial do Streamlit |
| **Composição** | `#### Composição de custo do SKU (componentes planejados)` + *caption* de quantidades | Cartão com título alinhado; `CardDescription` com *caption* de quantidades + link para **`/pricing`** («Preço de venda fica em Precificação») |
| **Valorização** | `#### Valorização atual do estoque por SKU` | **Mesmo título** (grafia «actual» no UI do protótipo, alinhada ao resto da app) |
| **Entrada de stock** | `#### Entrada de estoque (fluxo por SKU)` + *caption* Etapas 1–5 | **Mesmo título** + `CardDescription` com **Etapas 1–5** (texto do `st.caption` do Streamlit) |
| **Histórico** | `#### Histórico de custos de estoque (auditoria)` | **Mesmo título**; mensagem vazia: «Nenhuma entrada de estoque registada ainda.» |

**Conclusão:** ordem **composição → valorização → entrada → histórico**; títulos e blocos introdutórios principais **alinhados** ao Streamlit.

---

## 4. Composição de custo do SKU

### 4.1 Ausência de SKUs

- **Streamlit:** `st.info` com remissão a **Produtos** / estoque / `sku_master`.
- **Protótipo:** mensagem equivalente em **`components/cost-structure-form.tsx`**, com link **`/products`** («Produtos») e menção a `sku_master` — **paridade funcional** com o guia do Streamlit.

### 4.2 Modo de localização («Por SKU» / «Por nome»)

| Aspecto | Streamlit | Protótipo |
|---------|-----------|-----------|
| Rótulos | «Por SKU» / «Por nome do produto» | Idem. |
| *Select* por nome | «Nome — cor da armação — cor da lente» | Idem. |
| Duplicados no nome | Sufixo ` — [SKU]` | Construído em `GET /costs/sku-options` com a **mesma** regra. |

### 4.3 Carregamento ao mudar SKU

- **Streamlit:** *marker* em `session_state`, recarrega componentes e preenche quantidades formatadas e preço.
- **Protótipo:** `loadCostCompositionAction` → `GET /costs/composition?sku=`; estado `rows` e **«Último total salvo»** via `last_saved_structured_total`.

### 4.4 Linhas de componente

- **Streamlit:** `text_input` + `number_input` + totais locais com parsers.
- **Protótipo:** `Input` texto + número + **`POST /costs/preview-composition`** (debounce ~320 ms). Erros por linha da API (`quantity_error`, `price_error`).

### 4.5 Total global e erros agregados

- **Streamlit:** *metric* + aviso «Corrija os erros acima antes de salvar.»; botão **não** fica desactivado só por erros de parsing.
- **Protótipo:** bloco análogo com aviso se `preview.has_errors`; botão **Salvar** desactivado **apenas** quando `!isAdmin`.

### 4.6 Gravar composição

- **Streamlit:** `st.success("Composição de custo salva.")` + `st.rerun()`.
- **Protótipo:** mensagem **exacta** *«Composição de custo salva.»*; `revalidatePath("/costs")` + `router.refresh()` após sucesso.

### 4.7 Chave técnica do componente

- **Streamlit:** só rótulo humano.
- **Protótipo:** **alinhado** — chaves (`glasses`, …) **não** aparecem na UI.

---

## 5. Valorização do estoque por SKU

### 5.1 Streamlit (`st.dataframe`)

Colunas: **SKU**, **Estoque total**, **Custo médio (CMP)**, **Custo estruturado**, **Atualizado** (`format_qty_display_4` / `format_money`; «Atualizado» = `updated_at` ou «—»).

### 5.2 Protótipo (`GET /costs/sku-masters` + `page.tsx`)

Colunas **iguais em nome e ordem**: **SKU**, **Estoque total** (`formatQtyDisplay4` em `total_stock`, paridade com `format_qty_display_4`), **Custo médio (CMP)** e **Custo estruturado** (`formatProductMoney`, paridade com `format_money` a 2 decimais), **Atualizado** (`formatDate` sobre `updated_at` ou «—»).

- **Removido** desta tabela o par extra que o protótipo tinha antes (**Valorização** / **Preço actual**), para coincidir com o *dataframe* do Streamlit nesta secção (valorização financeira agregada e preço de venda tratados noutras páginas / *copy* do *caption* geral).

---

## 6. Entrada de stock (fluxo por SKU)

### 6.1 Texto das etapas

- **Streamlit:** *caption* com **Etapas 1–5** (localizar, lote, quantidade, custo = composição, confirmar / CMP).
- **Protótipo:** o mesmo texto nas **`CardDescription`** do cartão de entrada; no **`stock-receipt-form.tsx`**, linhas de apoio **«Etapa 1 — …»** até **«Etapa 5 — …»** nos rótulos / blocos (incl. «Etapa 4 — Custo unitário (estrutura salva)» e subtítulo «Custo unitário calculado» alinhado ao *metric* do Streamlit).

### 6.2 Etapa 1 — Localização

- Paridade forte (Por SKU / Por nome, mesmas listas via API).

### 6.3 Componentes somente leitura

- **Streamlit:** *expander* + *dataframe* (colunas Componente, Preço unit., Qtd, Linha).
- **Protótipo:** `<details>` + **tabela** (`Table`): **Componente**, **Quantidade**, **Custo unitário**, **Total** — mesmos dados da API; formatação de quantidade com **`formatQtyDisplay4`**; valores monetários com **`formatProductMoney`**.

### 6.4 Etapa 2 — Lote destinatário

- Atributos no *label*: **armação · lente · estilo · paleta · género** — API `GET /costs/stock-entry` (`costs.py` alinhado a `app.py`).
- **Stock no *label*:** `format_qty_display_4` no servidor.

### 6.5 Etapa 3 — Quantidade

- **Streamlit:** *text_input*; limpa ao mudar SKU.
- **Protótipo:** campo **controlado**; **limpa ao mudar SKU**; validação ao vivo **`POST /costs/parse-quantity-text`**.

### 6.6 Etapa 4 — Custo unitário e custo total da entrada

- **Streamlit:** *metric* unitário; aviso se zero; **custo total da entrada** se qtd válida e `unit_cost > 0`.
- **Protótipo:** bloco «Custo total da entrada» com **`Number((parsed × unit_cost).toFixed(2))`** quando parse **positivo**, quantidade **> 0** e `unit_cost > 0`.

### 6.7 Resumo e confirmação

- **Streamlit:** «Resumo da confirmação»; *checkbox* «Confirmo que esta entrada de estoque está correta.»; `can_finalize` inclui **`psku == stock_entry_sku.strip()`**.
- **Protótipo:** resumo antes da *checkbox*; mesma lógica de desactivação + **`onSubmit`** / `preventDefault`; mensagem se lote ≠ SKU.

### 6.8 Submissão e feedback

- **Streamlit:** `st.success("Entrada registrada. Custo médio (CMP) do SKU atualizado.")` + `rerun`.
- **Protótipo:** mensagem **exacta**; `revalidatePath` + `router.refresh()`; *audit* opcional.

### 6.9 Erros de quantidade em tempo real

- Mensagens da API de parse; vazio com texto alinhado a `addStockReceipt` (*«Indique a quantidade (texto, até 4 decimais).»*).

### 6.10 Mudança rápida de SKU

- `setCtx(null)` antes do novo `GET /costs/stock-entry` para evitar lotes do SKU anterior.

### 6.11 Sem SKUs para entrada

- **Streamlit:** *info* curta.
- **Protótipo:** mensagem + link **`/products`** para cadastro (equivalente ao encaminhamento do Streamlit).

---

## 7. Histórico de custos de stock (auditoria)

### 7.1 Limite

- Ambos: **75** entradas.

### 7.2 Colunas

| Coluna Streamlit | Protótipo |
|------------------|-----------|
| ID | **ID** |
| SKU | SKU |
| ID produto | **ID produto** |
| Qtd | **Qtd** (`formatQtyDisplay4`) |
| Custo unit. | Custo unit. (`formatProductMoney`) |
| Custo total entrada | Custo total entrada |
| Estoque antes / depois | **Presentes** |
| CMP antes / depois | **Presentes** (`cmp_before` / `cmp_after` no JSON) |
| Em | **Em** (`formatDate` em `created_at`) |

---

## 8. Permissões (RBAC) e operadores

- **Streamlit:** botões de gravação **desactivados** para não-admin.
- **Protótipo:** **igual na UI** (`disabled={!isAdmin}` + *title*); servidor com `requireAdmin()`.

---

## 9. Cache e actualização

- **Streamlit:** `st.rerun()` após sucesso.
- **Protótipo:** **`revalidate = 0`**; `revalidatePath` + **`router.refresh()`** após mutações.

---

## 10. Mapeamento rápido API ↔ secções

| Secção UI | Método / rota |
|-----------|----------------|
| Opções SKU / nomes | `GET /costs/sku-options` |
| Valorização tabela | `GET /costs/sku-masters` |
| Carregar composição | `GET /costs/composition` |
| Pré-visualizar totais | `POST /costs/preview-composition` |
| Validar texto de quantidade (entrada stock) | `POST /costs/parse-quantity-text` |
| Salvar composição | `POST /products/sku/cost-structure` |
| Contexto entrada stock | `GET /costs/stock-entry` |
| Finalizar entrada | `POST /inventory/stock-receipt` |
| Histórico | `GET /costs/stock-cost-history?limit=75` |

---

## 11. Matriz de paridade (resumo)

| Funcionalidade | Streamlit | Protótipo |
|----------------|-----------|-----------|
| Definições de componentes de custo | ✅ | ✅ (`lib/domain.ts` espelhado) |
| Modo Por SKU / Por nome | ✅ | ✅ |
| Pré-visualização totais / erros de parsing | ✅ | ✅ (via API) |
| Salvar composição (admin) | ✅ | ✅ |
| Mensagem sucesso composição | ✅ | ✅ (texto exacto) |
| UI sem chave técnica do componente | ✅ | ✅ |
| *Caption* global + Precificação | ✅ | ✅ (*PageHero* + link `/pricing` no cartão composição) |
| Tabela valorização (5 colunas + Atualizado) | ✅ | ✅ |
| Entrada stock + CMP | ✅ | ✅ |
| Validação SKU lote = SKU | ✅ | ✅ API + UI |
| Histórico auditoria completa | ✅ | ✅ |
| Resumo / etapas 1–5 / componentes em tabela | ✅ | ✅ |
| Limpar quantidade ao mudar SKU | ✅ | ✅ |
| Ordem das secções | ✅ | ✅ |
| Desactivar botões não-admin | ✅ | ✅ |
| Custo total entrada (preview) | ✅ | ✅ |
| Erros quantidade em tempo real | ✅ | ✅ |
| Stock no *label* do lote | ✅ | ✅ |
| Actualização imediata | *rerun* | ✅ |
| `hasDatabaseUrl` | N/A | ✅ Removido (`costs.ts` + `inventory.ts`) |

---

## 12. Conclusão

O protótipo **`/costs`** aproxima-se de **paridade estrita** com a página Custos do Streamlit em **textos introdutórios**, **títulos de secção**, **tabela de valorização** (cinco colunas, **Atualizado**, rótulos e formatação equivalentes), **guia quando não há SKUs** (com link a **Produtos**), **fluxo em cinco etapas** na entrada de stock, **componentes somente leitura em formato tabular**, e mantém o comportamento já descrito: RBAC, parse ao vivo, resumo, histórico completo, cache sem ISR longo, e API como única fonte de regras. **Diferenças residuais:** composição continua em grelha de cartões por componente (em vez de três colunas Streamlit por linha), *PageHero* não usa Markdown bold nativo (texto plano equivalente), e o *dataframe* do Streamlit na valorização não inclui colunas extra que o protótipo já não mostra.

---

*Fim do relatório.*
