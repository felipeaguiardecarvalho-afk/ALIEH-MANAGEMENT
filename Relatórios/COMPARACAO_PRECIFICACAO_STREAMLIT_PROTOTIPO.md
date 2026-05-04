# Comparação minuciosa: **Precificação** (Streamlit produção) × **`/pricing`** (protótipo Next)

**Data do relatório (versão inicial):** 2026-05-03  
**Última actualização:** 2026-05-03 — **revisão 2:** endurecimento funcional (preview só via API, RBAC estrito em Precificação, validação dupla no `POST /workflow`, coerência de *snapshot*, anti-*race* no cálculo).

**Âmbito:** página **Precificação** no `app.py` (bloco `elif page == PAGE_PRECIFICACAO:`) frente à rota **`/pricing`** em **`web-prototype`**, com dados via **`api-prototype`** (`/pricing/*`) e *server actions* em **`lib/actions/pricing.ts`**.

**Referências principais**

| Camada | Ficheiros |
|--------|-----------|
| Streamlit | `app.py` (aprox. linhas 1974–2257), `PRICING_MODE_PCT` / `PRICING_MODE_ABS`, `COSTING_STRUCT_PICK_*`, `compute_sku_pricing_targets`, `save_sku_pricing_workflow`, `fetch_active_sku_pricing_record`, `fetch_sku_pricing_records_for_sku`, `fetch_price_history_for_sku` |
| Protótipo UI | `web-prototype/app/(main)/pricing/page.tsx`, `pricing-workflow.tsx`, `loading.tsx` |
| Protótipo cálculo (referência) | `web-prototype/lib/pricing.ts` (`computePricingTargets` — espelho documental de `compute_sku_pricing_targets`; **a UI de precificação não usa esta função para o preview**) |
| Protótipo dados / acções | `web-prototype/lib/pricing-api.ts`, `lib/actions/pricing.ts`, `lib/rbac.ts` (`requireAdminForPricing`), `lib/types` (`SkuMasterRow`) |
| API | `api-prototype/routes/pricing.py` |

---

## 1. Resumo executivo

| Dimensão | Streamlit (produção) | Protótipo `/pricing` (estado actual) |
|----------|----------------------|--------------------------------------|
| **Objetivo** | Por **SKU**: ver CMP e preço actual; definir **margem, impostos e encargos** em % ou R$; ver **três degraus** de preço (pré-impostos, com impostos, alvo); **gravar** novo registo em `sku_pricing_records` e activar; consultar **histórico de workflow** e **histórico de preço (legado)**. | Mesmo fluxo de negócio: gravação via **`POST /pricing/sku/workflow`**; leituras `GET /pricing/sku-master`, snapshot, `pricing-records`, `price-history`. |
| **Paridade de regras de cálculo** | `compute_sku_pricing_targets` no Python (execução síncrona na sessão). | **Preview e persistência** passam pelo **mesmo** `compute_sku_pricing_targets` no servidor: **`POST /pricing/sku/compute-targets`** (preview com *debounce*) e **`POST /pricing/sku/workflow`** (após validação com *snapshot* + *compute* no *server action*). |
| **Paridade funcional (comportamento)** | `require_admin()`; hidratação ao mudar SKU; botão salvar condicionado; aviso CMP ≤ 0; lista vazia interrompe o fluxo; histórico workflow completo; `price_history` limite **50**; gravação só com lógica de domínio no backend. | **Alinhado**; acrescentam-se **validação explícita na rota** `workflow` (CMP > 0, alvo > 0), **RBAC de Precificação** sem bypass `ALIEH_PROTOTYPE_OPEN` quando há auth configurada, **preview API-only** (sem deriva TS na UI), e **guardas de coerência** do *snapshot* / *active_pricing* / *SKU*. |
| **Paridade de UX / cópia** | Textos «Etapa 1…4», rótulos «Margem / Impostos / Encargos», *metrics* em três colunas. | Cartão «Workflow» + *hero* técnico; rótulos **Markup / Taxas / Juros**; secções extra de *insight*; mensagem de sucesso **diferente**; captions longos das etapas **não** replicados na mesma forma. |

---

## 2. Arquitectura e fluxo de dados

### 2.1 Streamlit

- Chama directamente `fetch_sku_master_rows`, `fetch_product_triple_label_by_sku`, `fetch_active_sku_pricing_record`, `compute_sku_pricing_targets`, `save_sku_pricing_workflow`, `fetch_sku_pricing_records_for_sku(sel_sku, 100)`, `fetch_price_history_for_sku(sel_sku, 50)`.
- Ao **mudar SKU**, repõe `session_state` dos parâmetros a partir do registo **activo** (`markup_pct`, `taxes_pct`, `interest_pct`, `*_kind` / modo % vs R$). Se **não** existir registo activo, usa **0 / 0 / 0** em modo **%**.

### 2.2 Protótipo

- **SSR:** `fetchPrototypeSkuMasterList()` → `GET /pricing/sku-master`; opções de nome → `GET /costs/sku-options` (reutiliza a mesma lista «por nome» que Custos).
- **Cliente:** `loadPricingSnapshot`, `loadPricingRecords`, `loadPriceHistory` (*server actions* → `GET /pricing/sku/{sku}/snapshot`, `.../pricing-records`, `.../price-history?limit=50`).
- **Preview numérico:** **`POST /pricing/sku/compute-targets`** via *server action* `computeSkuPricingPreview` (corpo alinhado a `ComputeTargetsBody`: `avg_cost`, `markup_val`, `taxes_val`, `interest_val`, flags absolutas). *Debounce* (~160 ms) após parâmetros estáveis e **só** após a primeira carga de *insight* (`loadingInsight` inicial `true` evita corrida com hidratação).
- **Gravar:** `saveSkuPricing` — `requireAdminForPricing` + `gateMutation` → `GET` *snapshot* do SKU → valida **`sku_master.sku`** e **`avg_unit_cost` > 0** → **`postComputeTargetsApi`** (mesmo endpoint que o preview) com CMP **do servidor** → se `target <= 0`, erro antes do *workflow* → **`POST /pricing/sku/workflow`**. **Sem** `hasDatabaseUrl` — apenas API.
- **`lib/pricing.ts`:** `computePricingTargets` mantém-se como **documento de paridade** / uso eventual em testes; **não** alimenta os três *summaries* da página.

### 2.3 Sincronização, *race* e integridade (protótipo)

- **`insightRequestIdRef`:** respostas obsoletas de *snapshot* / históricos não sobrescrevem estado nem hidratação.
- **`computeRequestIdRef`:** respostas obsoletas de **`compute-targets`** não actualizam o preview.
- *Snapshot* só aplica-se se **`snap.sku_master.sku`** coincide com o SKU pedido; caso contrário limpa *insight* sem hidratar com dados cruzados.
- Hidratação de formulário a partir de **`active_pricing`** só se **`active_pricing.sku`** coincide com **`sku_master.sku`**; caso contrário repõe **0 / 0 / 0** em **%** (evita hidratar dados inconsistentes).
- Secção «Workflow activo»: se o registo activo existir mas o **SKU** não bater com o mestre, mostra mensagem de **inconsistência** em vez de detalhes do registo.

---

## 3. Permissões (RBAC)

| Aspecto | Streamlit | Protótipo (actual) |
|---------|-----------|-------------------|
| Quem vê a página | Só **admin** (`require_admin()` antes de qualquer UI). | **`requireAdminForPricing()`** no SSR em `page.tsx`: com **auth configurada** (utilizadores ou credenciais legadas), exige **admin** **mesmo** com `ALIEH_PROTOTYPE_OPEN=1` (alinhado ao Streamlit em produção). Sem auth configurada, mantém bypass do protótipo. |
| Quem grava | `require_admin()` no handler do botão Salvar. | **`requireAdminForPricing()`** + `gateMutation()` em `saveSkuPricing`. |

**Conclusão:** Precificação **não** herda o bypass de `requireAdmin()` para modo aberto quando já existe autenticação configurada; noutras páginas do protótipo o `requireAdmin()` clássico pode continuar mais permissivo.

---

## 4. Estado vazio (sem SKUs no mestre)

- **Streamlit:** `st.info("Ainda não há SKUs. Cadastre produtos em **Produtos** primeiro.")` e **`return`** — não renderiza o resto do fluxo.
- **Protótipo:** se a lista mestre vier vazia (sem erro de rede), mostra um **Card** com mensagem equivalente e **ligação a `/products`**; o componente **`PricingWorkflow` não é montado**.

---

## 5. Ordem e estrutura da página

### 5.1 Streamlit (fluxo vertical único)

1. Título `### Precificação (por SKU)` + *caption* das **Etapas 1–4** (localizar, parâmetros, rever preços, salvar).
2. **Etapa 1** — *radio* Por SKU / Por nome + *select*; três **métricas**: Estoque total, CMP, Preço de venda actual; *warning* se CMP ≤ 0.
3. **Etapa 2** — *caption* sobre bases % vs R$; três **colunas** (Margem, Impostos, Encargos) com *radio* modo + `number_input`.
4. **Etapa 3** — *caption* da cascata 1→2→3; três **métricas** de preços calculados (ou *info* se CMP zero).
5. **Etapa 4** — botão salvar (desactivado se `not (avg_cost > 0 and tgt > 0)`).
6. **Histórico de precificação** — *dataframe* com muitas colunas.
7. **Auditoria de preço de venda (legado)** — *dataframe* (`Anterior`, `Novo`, `Em`, `Obs.`).

### 5.2 Protótipo

- **PageHero** «Precificação» + descrição técnica (API, `sku_pricing_records`, etc.) — **não** replica o *caption* longo das Etapas 1–4 do Streamlit.
- Um único **Card** «Workflow» com `PricingWorkflow`:
  - *Radio* Por SKU / Por nome + *select* (opções SKU com texto extra «· CMP · estoque»).
  - Painel resumido «CMP actual (lista)» / «Preço activo (lista)» — **não** são as três *metrics* Streamlit (falta **Estoque total** como *metric* isolada no mesmo formato; estoque no *select* ou na secção *insight*).
  - **Aviso** quando CMP ≤ 0 (mesmo sentido que `st.warning` no Streamlit).
  - Três blocos **ParameterRow** (Markup, Taxas, Juros) com modo % / R$.
  - Três **Summary** alimentados pelo **resultado da API** `compute-targets` (arredondamento **Python** `round(..., 2)` — mesmo que o registo persistido).
  - Botão **Salvar precificação** com **`disabled`** quando CMP da lista ≤ 0 ou **preço alvo do preview** ≤ 0; durante `pending` do formulário o botão permanece inactivo (`SubmitButton` + `useFormStatus`).
  - **Secções adicionais:** «Precificação activa (registo)», «Histórico de precificação (workflow)», «Histórico de preço».

**Conclusão:** a **ordem lógica** e os **guardas funcionais** estão alinhados; o preview **numérico** do protótipo está **ligado ao mesmo motor** que o Streamlit usa no servidor. **Hierarquia visual** e **rótulos** continuam **diferentes**.

---

## 6. Etapa 1 — Localização do SKU e contexto

| Detalhe | Streamlit | Protótipo (actual) |
|---------|-----------|-------------------|
| Modo Por SKU / Por nome | `COSTING_STRUCT_PICK_SKU` / `…_NAME` | «Por SKU» / «Por nome do produto» — equivalente. |
| Duplicados no nome | Sufixo ` — [SKU]` | Via `GET /costs/sku-options` — mesma origem que Custos. |
| Após escolher SKU / recarga | Carrega **registo activo** para preencher margem/impostos/encargos e modos. | Após `loadPricingSnapshot` + validações de SKU / `active_pricing`: hidratação ou **0 / 0 / 0** em **%**. |
| Métricas de contexto | Três *metrics*: Estoque total (`format_qty_display_4`), CMP (`format_money`), Preço actual (`format_money`). | Duas *summaries*: CMP e preço (`formatCurrency`); estoque no *select* ou na secção *insight*. |
| CMP zero | `st.warning` com texto sobre Custos. | **Alerta** com o mesmo sentido (CMP indisponível; entrada em Custos). |

---

## 7. Etapa 2 — Parâmetros (margem, impostos, encargos)

| Detalhe | Streamlit | Protótipo |
|---------|-----------|-----------|
| *Caption* explicativo | Texto longo sobre % vs R$ e bases (margem sobre CMP; impostos sobre pré-impostos; encargos sobre com impostos). | **Ausente** no mesmo nível de detalhe (só descrição genérica no cartão da página). |
| Rótulos dos três parâmetros | «Margem», «Impostos», «Encargos / juros» (*number_input* alterna rótulo «… em %» vs «… em R$»). | «Markup», «Taxas», «Juros / adicional» — **semântica semelhante**, cópia **diferente**. |
| Modo | *Radio* horizontal: `Percentual (%)` vs `Valor fixo (R$)` (constantes `PRICING_MODE_*`). | Botões «Percentual (%)» / «Valor fixo (R$)» — equivalente funcional. |
| Entrada numérica | `number_input` `min=0`, `step=0.01`, `format="%.2f"`. | `Input type="number"` `min=0` `step=0.01` — equivalente. |

---

## 8. Etapa 3 — Preços calculados

| Detalhe | Streamlit | Protótipo |
|---------|-----------|-----------|
| *Caption* da cascata | Fórmula em três passos (pré-impostos, com impostos, alvo). | **Ausente** no protótipo junto aos três preços. |
| Rótulos das métricas | «Preço antes de impostos e encargos», «Preço com impostos», «Preço alvo (usado em Vendas)». | «Preço antes de impostos», «Preço com impostos», «Preço alvo» — **ligeiramente abreviado** (falta explicitar «usado em Vendas»). |
| Formatação | `format_money` | `formatCurrency` (Intl) — pode haver **nuances** de formatação vs `format_money` pt-BR. |
| Origem dos números | Python na mesma *run* que a UI. | **API** `compute-targets` (mesma função de serviço que o *workflow*); entre pedidos mostra **0** até haver resposta válida. |

---

## 9. Etapa 4 — Salvar

| Detalhe | Streamlit | Protótipo |
|---------|-----------|-----------|
| Texto do botão | «Salvar precificação (novo registro e ativar)». | «Salvar precificação». |
| `disabled` | `not (avg_cost > 0 and tgt > 0)`. | **`disabled`** quando `avgCost` (lista) ≤ 0 ou **alvo do preview API** ≤ 0; também durante `pending`. |
| Sucesso | «Precificação salva. Novo registro criado; histórico preservado. Preço alvo ativo para Vendas.» | «Nova precificação ativada.» — **texto diferente**. |
| Pós-sucesso | `st.rerun()` | `revalidatePath` (`/pricing`, `/products`, `/inventory`) + *bridge* que recarrega *snapshot* / históricos no cliente. |
| Validação servidor | Implícita em `save_sku_pricing_workflow` / *validators*. | *Server action* revalida com *snapshot* + *compute*; rota **`POST /sku/workflow`** valida **CMP > 0** e **alvo > 0** antes de persistir (mensagens `MSG_CMP_NOT_AVAILABLE` / `MSG_TARGET_PRICE_MUST_BE_POSITIVE` onde aplicável). |

---

## 10. Histórico de precificação (workflow)

### 10.1 Limite

- **Streamlit:** `fetch_sku_pricing_records_for_sku(sel_sku, 100)`.
- **Protótipo:** `GET .../pricing-records` com *default* **100** na API — alinhado.

### 10.2 Colunas do *dataframe* Streamlit vs tabela Next

| Coluna Streamlit | Protótipo (`pricing-workflow.tsx`) |
|------------------|-------------------------------------|
| ID | ID |
| Ativo («Sim» / «—») | Activo (Badge «Sim» / «Não») |
| CMP (instantâneo) | CMP snap. |
| Margem (% ou R$ conforme *kind*) | Markup (valor + «R$ fixo» / «%») |
| Impostos | Taxas |
| Encargos | Juros |
| Preço pré-impostos | **Preço pré-impostos** (`price_before_taxes`) |
| Preço c/ impostos | **Preço c/ impostos** (`price_with_taxes`) |
| Preço alvo | Alvo |
| Salvo em | Criado |

**Conclusão:** colunas de preços intermédios **alinhadas** com o *dataframe* Streamlit (nomes equivalentes).

---

## 11. Auditoria de preço de venda (legado)

| Coluna Streamlit | Protótipo |
|------------------|-----------|
| ID | ID |
| Anterior | Preço anterior |
| Novo | Preço novo |
| Em | Data |
| Obs. | Nota |

- **Limites:** Streamlit **50** entradas; o protótipo chama **`.../price-history?limit=50`**; a API usa *default* **50** em `Query` — **alinhado**.
- **Título:** Streamlit «#### Auditoria de preço de venda (legado)» + *caption*; protótipo «Histórico de preço» + texto sobre `price_history`.

---

## 12. Formatação monetária e quantidades

- Streamlit usa **`format_money`** e **`format_qty_display_4`** nas métricas e tabelas.
- O protótipo usa **`formatCurrency`** / **`formatDate`** na maior parte do fluxo de precificação; quantidades no *select* aparecem como número simples de `totalStock`, **não** com `format_qty_display_4`.

---

## 13. Mapeamento API ↔ UI (protótipo)

| Uso | Rota |
|-----|------|
| Lista mestre SKU | `GET /pricing/sku-master` |
| Nomes (triplo) | `GET /costs/sku-options` |
| *Snapshot* activo + mestre | `GET /pricing/sku/{sku}/snapshot` |
| Histórico workflow | `GET /pricing/sku/{sku}/pricing-records` |
| Histórico preço | `GET /pricing/sku/{sku}/price-history` (**`?limit=50`**) |
| **Preview (três preços)** | **`POST /pricing/sku/compute-targets`** |
| Gravar workflow | `POST /pricing/sku/workflow` |

---

## 14. Matriz de paridade (resumo)

| Funcionalidade | Streamlit | Protótipo (actual) |
|----------------|-----------|-------------------|
| Só admin na página inteira | ✅ | ✅ (`requireAdminForPricing` quando auth configurada; sem bypass `PROTOTYPE_OPEN` para Precificação) |
| Etapas 1–4 descritas no topo | ✅ | ⚠️ (texto técnico no *hero*, não o *caption* longo) |
| Sincronizar parâmetros ao mudar SKU (registo activo) | ✅ | ✅ (+ coerência `active_pricing.sku` / `sku_master.sku`) |
| Três métricas de contexto (estoque, CMP, preço) | ✅ | ⚠️ (layout diferente) |
| Aviso CMP zero | ✅ | ✅ |
| *Caption* bases % / R$ (Etapa 2) | ✅ | ❌ |
| Rótulos Margem / Impostos / Encargos | ✅ | ⚠️ (Markup / Taxas / Juros) |
| *Caption* cascata (Etapa 3) | ✅ | ❌ |
| Rótulos completos dos três preços | ✅ | ⚠️ |
| Cálculo alinhado a `compute_sku_pricing_targets` | ✅ | ✅ (**API** para preview + persistência; TS só referência) |
| Botão salvar desactivado se inválido | ✅ | ✅ (preview API + `pending`) |
| Backend rejeita CMP ≤ 0 / alvo ≤ 0 no *workflow* | ✅ (via serviço) | ✅ (rota + serviço) |
| Mensagem de sucesso exacta | ✅ | ❌ |
| Histórico workflow com todas as colunas | ✅ | ✅ |
| Histórico legado (50) | ✅ | ✅ |
| Sem SKUs — *info* + saída | ✅ | ✅ |
| Gravação só com API (sem `DATABASE_URL`) | N/A | ✅ |

---

## 15. Conclusão

O protótipo **`/pricing`** está **funcionalmente alinhado** ao Streamlit e, na **revisão 2**, reforçou **paridade numérica** (preview = mesmo motor Python que o *workflow*), **defesa em profundidade** no **`POST /sku/workflow`**, **validação pré-gravação** na *server action* com CMP **servidor**, **RBAC** de Precificação **estrito** quando existe autenticação configurada, e **robustez** a *races* e dados **inconsistentes** no *snapshot*.

**Diferenças residuais** concentram-se em **UX e cópia** (captions, rótulos, mensagem de sucesso, *metrics* vs painel, formatação de moeda e quantidades).

---

## 16. Registo de alterações — paridade inicial (revisão 1)

| Área | Alteração |
|------|-----------|
| `page.tsx` | `requireAdmin()` / lista vazia / `PricingWorkflow` condicional. |
| `pricing-workflow.tsx` | Hidratação `active_pricing`; `insightRequestIdRef`; defaults **0/0/0**; `SubmitButton disabled={!canSave}`; aviso CMP; colunas de preços intermédios no histórico. |
| `lib/actions/pricing.ts` | Remoção de `hasDatabaseUrl`; `price-history?limit=50`. |
| `api-prototype/routes/pricing.py` | *Default* `price-history` **50**. |

---

## 17. Registo de alterações — endurecimento (revisão 2)

| Área | Alteração |
|------|-----------|
| `lib/rbac.ts` | `requireAdminForPricing()` — com auth configurada, exige admin **mesmo** com `ALIEH_PROTOTYPE_OPEN=1`. |
| `page.tsx`, `saveSkuPricing` | Uso de `requireAdminForPricing`. |
| `lib/actions/pricing.ts` | `computeSkuPricingPreview` + `postComputeTargetsApi` (`POST .../compute-targets`); `saveSkuPricing` valida *snapshot* + *compute* com CMP do servidor antes do *workflow*. |
| `pricing-workflow.tsx` | Preview só via API; `computeRequestIdRef`; `loadingInsight` inicial `true`; *debounce*; validação `sku_master.sku` / `active_pricing.sku`; mensagem se registo activo inconsistente. |
| `api-prototype/routes/pricing.py` | `post_sku_pricing_workflow`: validação explícita **CMP > 0** e **alvo > 0** antes de `save_sku_pricing_workflow`. |
| `lib/pricing.ts` | Comentário: UI não usa TS para preview; função mantida como referência de paridade. |

---

*Fim do relatório.*
