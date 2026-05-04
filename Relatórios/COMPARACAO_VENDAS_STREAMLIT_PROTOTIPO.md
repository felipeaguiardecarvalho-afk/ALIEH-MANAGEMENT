# Comparação minuciosa: **Vendas** (Streamlit) × **`/sales`** (protótipo Next)

**Data do relatório:** 2026-05-03  
**Atualizações:** (1) alinhamento API-only em vendas; (2) endurecimento funcional — preview/submit, paridade de passo opcional, limites e respostas monetárias.

**Âmbito:** página **Vendas** no `app.py` (`elif page == PAGE_VENDAS:`) frente às rotas **`/sales`** (lista + vendas recentes) e **`/sales/new`** (fluxo de nova venda) em **`web-prototype`**, com **todas** as leituras e gravações de negócio via **`api-prototype`** e *server actions* em **`lib/actions/sales.ts`**. O fluxo de vendas no Next **não** depende de **`DATABASE_URL`**: SKUs vendáveis, clientes e lotes vêm da API; desconto e totais são calculados em **`services/sales_service.py`** (`preview_record_sale` + `record_sale`).

**Referências principais**

| Camada | Ficheiros |
|--------|-----------|
| Streamlit | `app.py` (aprox. linhas 1297–1585); `fetch_skus_available_for_sale`, `fetch_product_batches_in_stock_for_sku`, `fetch_product_stock_name_sku`, `fetch_customers_ordered`, `filter_customers_by_search`, `record_sale`, `fetch_recent_sales_for_ui`; `SALE_PAYMENT_OPTIONS`; `require_operator_or_admin`; `format_money` |
| Protótipo — lista | `web-prototype/app/(main)/sales/page.tsx` |
| Protótipo — nova venda | `web-prototype/app/(main)/sales/new/page.tsx`, `new-sale-form.tsx` |
| Protótipo — dados SSR (API) | `web-prototype/lib/sales-api.ts` (`fetchPrototypeSaleableSkus`, `STREAMLIT_RECENT_SALES_LIMIT`, `fetchPrototypeRecentSales`), `web-prototype/lib/customers-api.ts` (`fetchPrototypeCustomersList`) |
| Protótipo — lotes (accão servidor) | `loadSaleBatchesAction` em `web-prototype/lib/actions/sales.ts` → `GET /inventory/batches?sku=` |
| Protótipo — regras de desconto / totais | `services/sales_service.py` (`compute_sale_discount_amount`, `preview_record_sale`, `_record_sale_validate_row_and_compute_totals`, `record_sale`) |
| Protótipo — domínio | `web-prototype/lib/domain.ts` (`SALE_PAYMENT_OPTIONS`) |
| Protótipo — acção | `web-prototype/lib/actions/sales.ts` (`submitSaleForm`, `loadSaleBatchesAction`; `gateMutation`, `hasPrototypeApiUrl`; comparação preview vs estado actual) |
| Protótipo — API cliente (lista) | `web-prototype/lib/sales-api.ts` (`fetchPrototypeRecentSales` com `apiPrototypeFetchRead`) |
| Serviço partilhado | `services/sales_service.py` (`record_sale`, `preview_record_sale`, `fetch_recent_sales_for_ui`) |
| API protótipo | `api-prototype/routes/sales.py` e `api-prototype/routes/inventory.py` (ver secção 11) |
| SQL vendas recentes | `database/repositories/sales_repository.py` (`get_recent_sales_rows`) |

**Nota:** `lib/queries.ts` ainda expõe `getSaleableSkus` / `getBatchesForSku` para outros usos legados, mas **o fluxo `/sales/new` do `web-prototype` já não os utiliza**.

---

## 1. Resumo executivo

| Dimensão | Streamlit | Protótipo Next |
|----------|-----------|----------------|
| **Arquitectura de UI** | **Uma única página:** fluxo de venda (etapas 1–5 + conferência) **e** tabela «Vendas recentes» no **mesmo** *scroll*. | **Duas rotas:** **`/sales`** só com **vendas recentes** + botão **Nova venda**; **`/sales/new`** com o **formulário** completo. |
| **Descrição do fluxo** | *Caption* em 5 passos + confirmação; explica **ID de venda** `#####V` e baixa no **lote**. | *PageHero* em `/sales/new` descreve fluxo alinhado; texto do formulário indica que o **servidor revalida sempre** ao concluir; **«Atualizar resumo»** é **opcional** (conferência na tela), alinhado ao facto de no Streamlit não haver botão separado de preview. |
| **Elegibilidade de SKU** | `fetch_skus_available_for_sale`: `selling_price > 0`, `total_stock > 0`, `ORDER BY` **`sql_order_ci(sm.sku)`**. | **`GET /sales/saleable-skus`** chama o **mesmo** `read_queries.fetch_skus_available_for_sale` — **ordenação e critérios idênticos** ao Streamlit. |
| **Lotes por SKU** | `fetch_product_batches_in_stock_for_sku` — stock &gt; 0, `ORDER BY id`. | **`GET /inventory/batches?sku=`** → **`fetch_product_batches_in_stock_for_sku`** (mesma query). |
| **Um único lote** | *Caption* «Único lote… usado automaticamente.» | Primeiro lote pré-seleccionado no `<Select>` após carregar (equivalente). |
| **Cliente** | `filter_customers_by_search` + *selectbox*; aviso se não há clientes. | `Input` de filtro + `<Select name="customer_id">`; lista via **`GET /customers`**; rótulos `código · nome` (Streamlit: `código — nome`). |
| **Quantidade** | `number_input` com `min=1`, `max=floor(stock)`; aviso se stock &lt; 1 unidade inteira. | `input type=number` `min`/`max`; validação forte no **`POST /sales/preview`** / `record_sale` (stock, `EPS` 1e-9 no serviço Python). |
| **Desconto** | Percentual 0–100 ou valor fixo; `discount_amount = min(base_price, …)`; métricas *subtotal / desconto / total*. | **`preview_record_sale`** aplica `compute_sale_discount_amount` + **`_record_sale_validate_row_and_compute_totals`** — mesma base que **`record_sale`**; o cliente envia `discount_amount` já acordado com o preview; **`record_sale`** revalida na transacção. |
| **Pagamento** | `SALE_PAYMENT_OPTIONS` (tupla Python). | `SALE_PAYMENT_OPTIONS` em `lib/domain.ts` — **mesmos quatro valores** que `database/constants.py`. |
| **Conferência e gravação** | Checkbox + botão **desactivado** sem confirmar; `require_operator_or_admin()` no clique; `record_sale` → sucesso + `rerun`. | Checkbox `confirm_sale`; **cada** submissão de **«Concluir venda»** chama **`POST /sales/preview`** (validação actual) antes de gravar; **`intent=preview`** só actualiza o painel; antes de **`POST /sales/record`**: segundo **`POST /sales/preview`** e comparação com o primeiro resultado do mesmo pedido; se existir **`_prev.preview`**, comparação com formulário e com totais para detectar **mudança de estado** (stock/preço) entre resumo mostrado e servidor; **`requireOperator()`** + **`gateMutation()`**; **`SubmitButton`** + `pending` reduzem double-submit no cliente. |
| **Mensagem de sucesso** | `Venda **{code}** registrada. Total: **{format_money(total)}**` | `formatProductMoney(total)` em **`lib/format.ts`** (BRL, 2 casas). Resposta JSON de **`POST /sales/record`** com **`final_total`** arredondado a 2 casas na API. |
| **Vendas recentes** | `st.dataframe` com colunas: ID venda, SKU, **Produto**, Cliente, Qtd, **Unit.**, **Desconto**, Total, Pagamento, **Data/Hora**. | Tabela: **Data** (+ `sale_code` secundário), SKU, Cliente, Qtd, Total, Pagamento — **sem** colunas dedicadas a produto, preço unitário nem desconto; o tipo **`RecentSaleRow`** e o JSON da API **mantêm** `product_name`, `unit_price`, `discount_amount` (paridade de dados). |
| **Ordenação das recentes** | Dados de `fetch_recent_sales_for_ui` → `get_recent_sales_rows` → **`ORDER BY s.id DESC`**. | `GET /sales/recent` usa o **mesmo** serviço/SQL. |
| **Limite da lista** | Até 20 linhas na página Vendas. | Constante **`STREAMLIT_RECENT_SALES_LIMIT = 20`** em `sales-api.ts`; página usa este valor explicitamente. |
| **Pré-requisito técnico** | App Python com acesso à BD. | **`API_PROTOTYPE_URL`** no Next (e sessão / cabeçalhos). **Sem** exigência de **`DATABASE_URL`**. Lista recente: **`apiPrototypeFetchRead`** + **`get_actor_read`** (**viewer** pode ler). |

---

## 2. Modelo de navegação e fluxo de trabalho

### 2.1 Streamlit

- Título **«### Vendas»** e *caption* longa (passos 1–5 + confirmação + ID de venda + lote).
- **Bloco superior:** etapas 1 a 5 e conferência **sequenciais na mesma vista** (sem sub-rota).
- **Bloco inferior:** **«#### Vendas recentes»** com até 20 linhas.

### 2.2 Protótipo

- **`/sales`:** *PageHero* + tabela (ou estado vazio) + link **Nova venda**.
- **`/sales/new`:** cartão «Execução de venda» com `NewSaleForm`.

**Conclusão:** o **conteúdo funcional** (SKU → lote → cliente → quantidade → desconto → pagamento → confirmar → lista recente) existe nos dois sistemas; a **decomposição em rotas** permanece uma diferença estrutural. O botão **«Atualizar resumo»** é **opcional** para **concluir** a venda (o servidor **sempre** reexecuta o equivalente a um preview na *action*), aproximando a **paridade funcional** do Streamlit (totais sempre coerentes com o estado actual ao gravar).

---

## 3. Etapa 1 — SKU e lote

### 3.1 Lista de SKUs elegíveis

| Aspecto | Streamlit | Protótipo |
|---------|-----------|-----------|
| Critério | `sku_master` não apagado, `selling_price > 0`, `total_stock > 0` | **Idêntico** (`fetch_skus_available_for_sale` na API) |
| Rótulo | SKU + nome exemplo + estoque agregado `:g` | SKU + nome + `formatCurrency(sellingPrice)` + «estoque {totalStock}» |
| Ordenação | `sql_order_ci("sm.sku")` | **Mesma** (`fetch_skus_available_for_sale` via **`GET /sales/saleable-skus`**) |

**Gap residual:** nenhum na **ordenação / elegibilidade** de SKU entre Streamlit e protótipo (mesmo código Python).

### 3.2 Selecção de lote

- **Streamlit:** se um lote → usa-o e *caption*; se vários → *selectbox* com `product_enter_code`, stock `:g`, nome.
- **Protótipo:** **`loadSaleBatchesAction(selectedSku)`** (accão servidor, `apiPrototypeFetchRead`) → **`GET /inventory/batches?sku=…`**; *select* `name="product_id"`; primeiro lote por omissão após carregar.

**Removido:** rota interna Next **`/api/batches`** (evita duplicar a camada de dados).

### 3.3 Painel de contexto (stock, preço, nome)

- **Streamlit:** `fetch_product_stock_name_sku` + `batch_row` para nome, código entrada, atributos, *metrics* (estoque lote, estoque total SKU, preço unitário `format_money`).
- **Protótipo:** painel opcional após **«Atualizar resumo»** (`intent=preview`) com dados de **`POST /sales/preview`** (inclui `customer_id` no payload para alinhar comparações na *action*). Totais **não** são calculados no browser.

**`GET /sales/product-context/{id}`:** mantido na API; **documentado como deprecado** para o fluxo `web-prototype` (o preview cobre stock/preço/validações no mesmo serviço). Útil para integrações externas.

---

## 4. Etapa 2 — Cliente

- **Streamlit:** *text_input* de busca + `filter_customers_by_search`; *selectbox* com `customer_code — name`; `cust_id` obrigatório para *ready*.
- **Protótipo:** filtro em memória (`includes` em nome e código); `<select name="customer_id" required>` com opção vazia inicial; dados de **`GET /customers`**.

**Paridade:** filtro por nome/código. **Diferença cosmética:** separador `—` vs `·` nos rótulos.

---

## 5. Etapa 3 — Quantidade

- **Streamlit:** `max_sale_qty = floor(available_stock + 1e-9)`; *number_input* inteiro entre 1 e max; avisos se sem etapa 1 ou stock insuficiente para 1.
- **Protótipo:** `max` no HTML alinhado ao stock do lote carregado da API; validação definitiva em **`sales_service`** no preview e na transacção de `record_sale`.

---

## 6. Etapa 4 — Desconto

- **Streamlit:** *radio* «Percentual (%)» / «Valor fixo»; cálculo `base_price = quantity * unit_price`; `discount_amount` limitado ao subtotal; três *metrics*.
- **Protótipo:** *radio* `discount_mode` `percent` / `fixed`; cálculo e teto ao subtotal em **`compute_sale_discount_amount`** (Python), aplicado dentro de **`preview_record_sale`** e revalidado em **`record_sale`**.

---

## 7. Etapa 5 — Forma de pagamento

- Lista **idêntica** em constantes (`Dinheiro`, `Pix`, `Débito`, `Crédito`).
- **Streamlit:** *selectbox* sem `required` HTML mas *ready* exige fluxo completo.
- **Protótipo:** `<select required>` + validação no serviço (`normalize_and_require_sale_payment_method`).

---

## 8. Conferência, confirmação e gravação

### 8.1 Streamlit

- `ready`: `product_id`, `cust_id`, `unit_price > 0`, `quantity >= 1`, `quantity <= stock + 1e-9`.
- Tabela-resumo (*st.table*); checkbox de confirmação; botão **Concluir venda** desactivado sem checkbox.
- `record_sale(product_id, quantity, customer_id, discount_amount, payment_method)` → `insert_sale_and_decrement_stock` + validações em `sales_service`.

### 8.2 Protótipo

- **`POST /sales/preview`** → **`preview_record_sale`** (só leitura; devolve também **`customer_id`**).
- Em **qualquer** submissão com dados completos, a *action* chama **preview** com o formulário actual (incl. **submit** sem ter clicado antes em «Atualizar resumo»).
- No **submit** com confirmação: (1) se existir **`state.preview`** de uma sessão anterior, valida se o formulário ainda coincide com esse resumo e se **preço unitário / desconto / total** do resumo antigo ainda batem com uma recomputação imediata (mensagens explícitas se o utilizador alterou campos ou se **stock/preço** mudaram); (2) **segundo** `POST /sales/preview` em cadeia antes de **`POST /sales/record`** — se divergir do primeiro resultado **do mesmo pedido**, erro (*estado mudou entre validação e gravação*); (3) **`POST /sales/record`** com `discount_amount` / quantidade / pagamento alinhados ao último preview; **`record_sale`** relê o produto na **transacção** (lote existe, stock suficiente, desconto ≤ subtotal).
- Respostas JSON: **`api-prototype/routes/sales.py`** arredonda **`base_price`**, **`discount_amount`**, **`final_total`**, **`unit_price`** no JSON do preview (2 casas) e **`final_total`** na resposta de **`/sales/record`**, para consistência de apresentação com o total mostrado.
- **`logPrototypeAuditEvent`** após sucesso; **`revalidatePath`** em `/sales`, `/dashboard`, `/inventory`.

### 8.3 Diferenças de fluxo

| Tópico | Streamlit | Protótipo |
|--------|-----------|-----------|
| Pré-visualização na tela | Totais quando `ready`, sem botão dedicado. | **Opcional:** «Atualizar resumo» preenche o painel; **não** é obrigatório para gravar — a *action* **sempre** chama preview no servidor antes de `record`. |
| `gateMutation` | N/A | **Presente** em `submitSaleForm`. |
| `DATABASE_URL` no Next | N/A | **Ausente** do fluxo de vendas — dados e mutações via **API**. |
| Double-submit | Um clique típico | `useFormStatus` / `SubmitButton` desactivam botões durante `pending` (salvaguarda no cliente; sem idempotency key na API). |

---

## 9. Vendas recentes (tabela)

### 9.1 Origem dos dados

- **Streamlit e API `GET /sales/recent`:** `fetch_recent_sales_for_ui` → `get_recent_sales_rows` (limite por defeito **20** no Streamlit).
- **Protótipo:** `fetchPrototypeRecentSales(STREAMLIT_RECENT_SALES_LIMIT)` com **`STREAMLIT_RECENT_SALES_LIMIT = 20`** (`sales-api.ts`); query param `limit` na API até 500.

### 9.2 Colunas e apresentação

| Coluna / dado | Streamlit | Protótipo `/sales` |
|----------------|-------------|---------------------|
| Identificador | `sale_code` ou `#id` | Data formatada + `sale_code` em texto pequeno |
| SKU | Sim | *Badge* |
| **Produto** | Nome (`product_name`) | **Não** na tabela (campo **presente** no JSON / tipo `RecentSaleRow`) |
| Cliente | `customer_label` | Sim (*line-clamp*) |
| Quantidade | Sim | `formatNumber` |
| **Preço unitário** | `format_money(unit_price)` | **Não** na tabela (campo **presente** na API / tipo) |
| **Desconto** | `format_money(discount_amount)` | **Não** na tabela (campo **presente** na API / tipo) |
| Total | Sim | `formatCurrency` |
| Pagamento | Sim | Sim |
| Data/hora | `sold_at` bruto na célula | `formatDate(sold_at)` — `sold_at` em ISO na mesma base que na inserção da venda |

**Nota:** omitir colunas na UI **não altera** a regra de negócio da venda já gravada; é **densidade de informação** na listagem. **Completude de dados:** o cliente **não descarta** campos extra ao mapear a resposta.

---

## 10. RBAC e perfis

| Operação | Streamlit | Protótipo |
|----------|-----------|-----------|
| Ver página Vendas / lista recente | Qualquer utilizador com sessão no menu | **`/sales`:** `fetchPrototypeRecentSales` usa **`apiPrototypeFetchRead`**; API **`GET /sales/recent`** com **`get_actor_read`** — **viewer** pode ver a lista. |
| Ver formulário nova venda (dados) | Mesmo | SSR com **`get_actor_read`** nas rotas de listagem de SKUs e clientes; lotes via accão com cabeçalhos de leitura. |
| Gravar venda | `require_operator_or_admin()` | **`requireOperator()`** + **`gateMutation()`** na *action* + API **`get_actor`** em **`POST /sales/preview`** e **`POST /sales/record`**. |

---

## 11. API REST (`api-prototype` — vendas e lotes)

| Método | Rota | Actor | Função / notas |
|--------|------|-------|----------------|
| POST | `/sales/record` | `get_actor` | `record_sale`; resposta com **`final_total`** arredondado a 2 casas decimais. |
| POST | `/sales/preview` | `get_actor` | `preview_record_sale`; JSON com **`customer_id`** e valores monetários arredondados a 2 casas. |
| GET | `/sales/recent` | **`get_actor_read`** | `fetch_recent_sales_for_ui` |
| GET | `/sales/saleable-skus` | **`get_actor_read`** | `fetch_skus_available_for_sale` |
| GET | `/sales/product-context/{id}` | `get_actor` | **Deprecado** para o fluxo `web-prototype` (docstring na rota); preview cobre o caso de uso interno. |
| GET | **`/inventory/batches`** | **`get_actor_read`** | `fetch_product_batches_in_stock_for_sku` |

---

## 12. Matriz de paridade (resumo)

| Funcionalidade | Streamlit | Protótipo |
|----------------|-----------|-----------|
| SKU elegível (preço + stock agregado) | Sim | Sim (mesmo código de query) |
| Lotes em stock por SKU | Sim | Sim (mesmo código de query) |
| Busca de cliente por nome/código | Sim | Sim |
| Quantidade inteira ≤ stock lote | Sim | Sim |
| Desconto % ou fixo limitado ao subtotal | Sim | Sim (serviço Python) |
| Opções de pagamento | Sim | Sim |
| `record_sale` / stock / `sale_code` | Sim | Sim |
| Lista recentes (mesmo SQL base) | Sim | Sim |
| Colunas completas na tabela de recentes | Sim | Parcial na **UI**; dados completos no **JSON** / tipo |
| Mesma página venda + recentes | Sim | Não (rotas separadas) |
| Preview antes de gravar (lógica) | Implícito (`ready`) | **Sempre** no servidor na *action*; botão «Atualizar resumo» só para **painel** opcional |
| Ordenação SKUs case-insensitive | Sim | Sim |
| `DATABASE_URL` / `gateMutation` na venda | N/A | **`DATABASE_URL`** não usado; **`gateMutation`** presente |
| Limite 20 vendas recentes | Sim | Sim (`STREAMLIT_RECENT_SALES_LIMIT`) |
| Detecção de mudança de estado entre resumo e gravação | Implícito (mesma sessão) | Mensagens explícitas + duplo preview no mesmo submit |

---

## 13. Conclusão

A **espinha dorsal** da venda permanece **alinhada** com o Streamlit (`sales_service`, mesmo SQL de recentes). O protótipo **reforçou** a **consistência** entre o que o utilizador viu no resumo (se usou «Atualizar resumo») e o que o servidor grava: **revalidação** com segundo preview no mesmo pedido de conclusão, **comparação** com `state.preview` quando existe, e **mensagens** claras se o formulário ou o **stock/preço** mudaram. A **paridade funcional** com o Streamlit no sentido «não é obrigatório carregar um resumo antes de vender» foi aproximada: o **preview lógico** corre **sempre** na *action*. **RBAC**, **API-only**, **`formatProductMoney`**, **limite 20 explícito** e **depreciação documentada** de `product-context` para o fluxo web completam o estado actual.

---

## 14. Sugestões opcionais (melhorias de UI)

1. Colunas **Produto**, **Unit.** e **Desconto** na tabela de `/sales` usando campos já presentes em `RecentSaleRow` / API (apenas UI, sem mudar regras).

---

*Fim do relatório.*
