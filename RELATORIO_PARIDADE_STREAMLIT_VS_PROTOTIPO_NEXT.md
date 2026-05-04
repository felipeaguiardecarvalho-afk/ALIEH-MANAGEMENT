# Relatório de paridade: app Streamlit (produção) vs protótipo Next.js (`web-prototype` + `api-prototype`)

**Data do relatório:** 2026-05-02  

**Escopo “produção”:** aplicação Streamlit descrita pelo código em `app.py` e `utils/painel_dashboard.py`, correspondente ao repositório implantado em `https://aliehmanagement.streamlit.app/`.  

**Escopo “protótipo”:** aplicação Next.js em `web-prototype/`, com mutações e leituras principais via `api-prototype/`.  

**Nota sobre acesso à URL:** não foi possível obter HTML ao vivo da URL de produção (timeout na ferramenta de fetch). Este documento é **exaustivo em relação ao código-fonte** do Streamlit no repositório; se o deploy público divergir do `main` local, apenas essa divergência não aparece aqui.

---

## 1. Arranque global, infraestrutura e shell (só Streamlit)

| # | Função / comportamento | Onde no código | Protótipo Next |
|---|------------------------|----------------|----------------|
| 1.1 | `load_dotenv` na raiz do projeto | `app.py` (início) | Variáveis via `.env` / Vercel / ambiente — não aplica o mesmo `Path` |
| 1.2 | Log “DATABASE_URL detected” | `app.py` | Não equivalente na UI |
| 1.3 | **`st.subheader("DB Connection Debug")` + `st.write(test_db_connection())`** — exibe resultado de `SELECT current_database(), current_user` ou erro Postgres via `st.secrets["DATABASE_URL"]` | `main()` em `app.py` | **Ausente** (não expor debug de BD na UI) |
| 1.4 | `run_database_init()` | `main()` | Inicialização de schema é responsabilidade do backend/ops, não da UI Next |
| 1.5 | `register_sqlite_full_backup_atexit`, `run_startup_sqlite_full_backup_once` | `main()` | **Ausente** (específico SQLite local) |
| 1.6 | `maybe_run_periodic_maintenance_backups`, `maybe_run_periodic_database_health` | `main()` | **Ausente** |
| 1.7 | `ensure_authenticated_or_stop()` — bloqueia app sem sessão | `main()` | Auth própria (JWT / cookies; fluxo em `lib/actions/auth` e layout) |
| 1.8 | CSS global Montserrat + layout wide + regras de sidebar | `st.markdown` em `main()` | Tailwind / layout em `web-prototype/app/(main)/layout.tsx` — estilo diferente |
| 1.9 | `st.set_page_config(page_title="ALIEH — Gestão", layout="wide")` | `main()` | Metadados Next (`layout`, metadata) |
| 1.10 | Título `ALIEH — Gestão comercial` + legenda “(banco SQLite local)” | `main()` | Branding ALIEH no `TopNav`; texto não menciona SQLite |
| 1.11 | Botão **Sair** na sidebar se auth configurada + `logout()` | `main()` | `logout` em `TopNav` → `lib/actions/auth` |
| 1.12 | Caption **Inquilino:** `get_session_tenant_id()` | `main()` | Tenant/role resolvido no servidor (`resolveRole`, headers para API) — não replica caption literal |
| 1.13 | **Navegação** por `st.sidebar.radio`: Painel, Produtos, Custos, Precificação, Estoque, Clientes, Vendas, Checklist UAT | `main()` | `web-prototype/components/top-nav.tsx` — mesma ordem lógica de rotas |
| 1.14 | **`_maybe_sidebar_database_export()`** — se `DB_PROVIDER=sqlite` e secret `allow_database_export`, expander “Backup do banco (admin)” + `st.download_button` do ficheiro `.db` (só admin) | `app.py` | **Ausente** |
| 1.15 | Página **Produtos** não chama `require_admin` globalmente; operações sensíveis chamam `require_admin()` pontualmente | Várias secções | RBAC por ação/API |

---

## 2. Painel executivo (`PAGE_PAINEL` → `render_painel_executivo`)

Implementação Streamlit: `utils/painel_dashboard.py` (`render_painel_executivo` + caches `_cached_*`).  
Implementação protótipo: `GET /dashboard/panel` (`api-prototype`) + `web-prototype/app/(main)/dashboard/` (`dashboard-filters.tsx`, `dashboard-data-section.tsx`, `lib/dashboard-url.ts`, `lib/dashboard-api.ts`).

| # | Função / elemento | Streamlit | Protótipo |
|---|-------------------|-----------|-----------|
| 2.1 | Hero BI “Intelligence · ALIEH” + subtítulo | `bi_hero` | `PageHero` + copy própria — **texto/branding diferente**, função equivalente |
| 2.2 | Limites de datas de vendas para defaults | `fetch_sales_date_bounds` | `normalizeDashboardQuery`: presets 7/30/90 ou personalizado; default ~30 dias — **não** usa explicitamente os bounds da BD na URL |
| 2.3 | Presets **7 / 30 / 90 dias** + **Personalizado** | `st.selectbox` | Botões de atalho + datas manuais quando “Personalizado” — **paridade** |
| 2.4 | **Clientes ativos (dias)** 7–365 (default 90) | `st.number_input` | Campo numérico em `DashboardFilters` — **paridade** |
| 2.5 | Filtros **SKU**, **Produto (lote)**, **Cliente** | `st.selectbox` | Selects + query string — **paridade** |
| 2.6 | Datas personalizadas + validação início ≤ fim | Sim | Período custom + API — **paridade** |
| 2.7 | KPIs + **deltas** vs período anterior (%, margem em p.p.) | `st.metric` + `kpi_delta_pct` | `KpiCard` com deltas a partir de `kpi_deltas` — **paridade** |
| 2.8 | Top clientes (gráfico) | Plotly | `CustomerBreakdownChart` — **mesma métrica**, visual **HTML/CSS** (não Plotly) |
| 2.9 | Caixa **Insights** | `render_insight_box` | `InsightsCard` com linhas da API — **paridade** de conteúdo |
| 2.10 | Receita diária + **MM7** | Plotly | `DailyRevenueMaChart` (`revenue_ma7`) — **paridade** |
| 2.11 | Top SKUs por receita | Plotly | `SkuBreakdownChart` — paridade métrica, visual leve |
| 2.12 | **Margem por SKU** | Plotly | `MarginSkuChart` — **paridade** |
| 2.13 | **Cohort** primeira compra | Plotly | `CohortChart` — **paridade** |
| 2.14 | **Giro de stock (proxy)** | `_cached_turnover` | **Ausente** no painel Next (sem bloco equivalente na UI) |
| 2.15 | Forma de pagamento | Plotly donut | `PaymentBreakdownChart` — paridade métrica, visual diferente |
| 2.16 | Stock crítico (≤ 5) + prioridade ≤ 2 | `st.dataframe` | `LowStockTable` — **paridade** |
| 2.17 | Inventário envelhecido + **15–180 dias** (default 45) | `st.slider` | Campo **Stock parado (dias mín.)** no formulário de filtros — **paridade** (input em vez de slider) |
| 2.18 | Resumo inventário: **valor CMP**, unidades, críticos | `fetch_inventory_stock_summary` | Bloco “Valor inventário (CMP)” + `inventory_summary` da API — **paridade** |
| 2.19 | Caches `@st.cache_data` | Sim | `revalidate = 120` na página + cache da API |
| 2.20 | CSS/cards BI Streamlit | `inject_bi_dashboard_css` | Design system Tailwind / cards do protótipo — **visual diferente** |

**Resumo painel:** paridade **funcional** muito alta (filtros, presets, KPIs com deltas, insights, MM7, margem SKU, cohort, stock crítico, aging, CMP, breakdowns). Lacunas principais: **giro de stock**; **Plotly** e peças de **branding/hero** idênticas ao Streamlit; defaults de datas **sem** leitura explícita dos bounds de vendas na URL.

---

## 3. Produtos (`PAGE_PRODUTOS`)

| # | Função | Streamlit | Protótipo |
|---|--------|-----------|-----------|
| 3.1 | Secção “Busca por SKU e lote” em **expander** | Sim | Busca + ordenação + tamanho de página sempre visíveis; **filtros por atributo** em `<details>` colapsável — UX diferente, mesma função |
| 3.2 | Busca texto SKU ou nome | `st.text_input` | Paridade via `GET /products` |
| 3.3 | Ordenar: sku, name, stock_desc, stock_asc | `st.selectbox` | `products-filters` / URL — **paridade** |
| 3.4 | Linhas por página 25/50/100/200 | `st.selectbox` | Select na página — **paridade** |
| 3.5 | Cinco filtros atributo | `fetch_product_search_attribute_options` | `GET /products/attribute-options` + filtros — **paridade** |
| 3.6 | Paginação, total, tabela | Sim | `ProductsTable` (TanStack) + paginação — **paridade** |
| 3.7 | Detalhe de produto | `st.selectbox` | Painel lateral `product-detail-aside.tsx` (`?detail=id`) |
| 3.8 | Detalhe: imagem, atributos, stock, custo, preço, identificação | Sim | Secções **Imagem**, **Identificação**, **Atributos**, **Stock e precificação** — **paridade** |
| 3.9 | Upload foto lote (admin) | Sim | Conforme integração/API do protótipo |
| 3.10 | Selects atributo com **“Outro”** + texto + valor na lista após gravar | `dropdown_with_other` | `AttributeSelectWithOther` em `new-product-form` e `product-lot-edit-form`; listas do novo produto = listas do domínio **∪** `GET /products/attribute-options` (`mergeDomainWithApiAttributeOptions`) — **paridade** |
| 3.11 | Bloqueio edição com mensagem | Sim | API / mensagens de erro |
| 3.12 | `update_product_lot_attributes` | Sim | `updateProductLotAttributes` + API |
| 3.13 | Exclusão SKU | Fluxo dois passos | `product-sku-delete-form` + API |
| 3.14 | **Pré-visualização SKU ao vivo** no cadastro | `_maybe_preview_product_sku` | **Ausente** no browser (SKU só após submissão) |
| 3.15 | Placeholder “Selecione” | Streamlit | Select / “Outro” HTML |
| 3.16 | `add_product` + código de entrada na mensagem | Sim | `createProduct` + API — **paridade** |

---

## 4. Vendas (`PAGE_VENDAS`)

| # | Função | Streamlit | Protótipo |
|---|--------|-----------|-----------|
| 4.1 | Etapa 1: SKUs vendáveis `fetch_skus_available_for_sale`; label com nome amostra e estoque SKU | Sim | `NewSaleForm` + lista `skus` |
| 4.2 | Lotes: um lote auto; vários → `selectbox` por código/estoque/nome | Sim | `fetch /api/batches?sku=` + select |
| 4.3 | Métricas: estoque lote, estoque total SKU, preço unitário ativo | `st.metric` | Resumo após preenchimento / preview |
| 4.4 | Etapa 2: busca cliente + `selectbox` | Sim | Mesmo padrão |
| 4.5 | Etapa 3: quantidade **inteira** `floor(available_stock)`, min 1 max estoque | `st.number_input` | `Input type=number` min/max/step 1 |
| 4.6 | Etapa 4: desconto % ou fixo; cálculo `discount_amount`, métricas subtotal/desconto/total | Sim | Radio + campo único + **intent preview** no servidor |
| 4.7 | Etapa 5: `SALE_PAYMENT_OPTIONS` | Sim | `SALE_PAYMENT_OPTIONS` em domain |
| 4.8 | Conferência + checkbox + `record_sale` | Um passo Streamlit | **Dois passos** mantidos: **Atualizar resumo** (`intent=preview`) e **Concluir venda** (`intent=submit`); resumo alargado com cliente, quantidade, modo de desconto, pagamento e totais (`SalePreviewPanel`) |
| 4.9 | **Vendas recentes** (20 linhas) `fetch_recent_sales_for_ui` | Sim | `GET /sales/recent?limit=20` (`lib/sales-api.ts`); colunas **data**, **SKU**, **cliente** (`customer_label`), **quantidade**, **total**, **pagamento** — **paridade** |

---

## 5. Custos (`PAGE_CUSTOS`)

| # | Função | Streamlit | Protótipo |
|---|--------|-----------|-----------|
| 5.1 | Composição: **localizar por SKU OU por nome** (rótulo triplo + desambiguação duplicados) | `st.radio` + dois `selectbox` | **Só SKU** em `cost-structure-form.tsx` (`Select` de `skus`) |
| 5.2 | Quantidade por componente como **texto** com até 4 decimais (`parse_cost_quantity_text`) | Sim | **Inputs numéricos** `step 0.01` — comportamento de parsing diferente |
| 5.3 | Preço unitário `number_input`; **total linha ao vivo** + erros inline | Sim | Grid qty/price sem métrica “Total linha” por linha como Streamlit |
| 5.4 | Métrica **Custo total (SKU, ao vivo)** + caption último total salvo | Sim | **Ausente** (só feedback pós-submit) |
| 5.5 | Botão salvar → `save_sku_cost_structure` (admin) | Sim | `saveCostStructure` action |
| 5.6 | Tabela **Valorização atual do estoque por SKU** (dataframe) | Sim | Tabela em `costs/page.tsx` com colunas SKU, Estoque, CMP, Total estruturado, Valorização, Preço atual — **paridade próxima** |
| 5.7 | **Entrada de estoque** em 5 etapas: localizar SKU/nome; expander componentes read-only; select lote com label rico; qty texto; **custo unitário só lido** (`get_persisted_structured_unit_cost`); resumo; **checkbox confirmação**; `add_stock_receipt` | Sim | `StockReceiptForm`: SKU, lote, qty (**min 1 step 1**), **custo unitário manual** — **sem** confirmação checkbox; **sem** modo “por nome”; **sem** custo bloqueado ao CMP estruturado automático |
| 5.8 | **Histórico de custos de estoque** (75 entradas) `fetch_recent_stock_cost_entries` | `st.dataframe` completo | **Ausente** na UI de custos |

---

## 6. Precificação (`PAGE_PRECIFICACAO`)

**Streamlit:** página inteira `require_admin()`.

| # | Função | Streamlit | Protótipo |
|---|--------|-----------|-----------|
| 6.1 | Localizar **SKU ou nome** (mesmo padrão de Custos) | Sim | **Só seleção por SKU** (`PricingWorkflow` + `fetchPrototypeSkuMasterList`) |
| 6.2 | Métricas: estoque total SKU, CMP, preço venda atual | Sim | Paridade no workflow |
| 6.3 | Aviso CMP ≤ 0 | Sim | Equivalente |
| 6.4 | Etapa 2: margem/impostos/encargos cada um com **radio % vs R$** + `number_input` | Sim | `markupKind` / `taxesKind` / `interestKind` + inputs |
| 6.5 | Etapa 3: `compute_sku_pricing_targets` + 3 métricas explicadas | Sim | `computePricingTargets` client-side + exibição |
| 6.6 | Etapa 4: `save_sku_pricing_workflow` | Sim | `saveSkuPricing` action + API |
| 6.7 | Histórico workflow `fetch_sku_pricing_records_for_sku` (100) | `st.dataframe` | Tabela via `loadPricingRecords` |
| 6.8 | **Auditoria legado** `fetch_price_history_for_sku` (50) | Sim | `loadPriceHistory` |

---

## 7. Clientes (`PAGE_CLIENTES`)

| # | Função | Streamlit | Protótipo |
|---|--------|-----------|-----------|
| 7.1 | Abas **Cadastrar** / **Editar cliente** | `st.tabs` | Rotas `/customers/new` e `/customers/[id]/edit` + listagem `/customers` |
| 7.2 | ViaCEP no cadastro: CEP + botão Buscar → preenche rua/bairro/cidade/UF | Sim | `CustomerCepBlock` |
| 7.3 | Form cadastro: nome*, CPF, RG, telefone, email, instagram, endereço completo | Sim | Paridade |
| 7.4 | Validações: CEP 8 dígitos se preenchido; CPF `validate_cpf_br`; email `validate_email_optional` | Sim | Actions servidor |
| 7.5 | `insert_customer_row` + limpeza session + mensagem código | Sim | `createCustomer` |
| 7.6 | Tabela **Todos os clientes** (código, nome, CPF, telefone, cidade, atualizado) | Na aba Cadastrar | Página `/customers`: tabela completa com **código**, **nome**, **CPF** (formatação visual quando 11 dígitos), **telefone**, **cidade**, **atualizado** (`updated_at` via API; fallback `created_at` se necessário) + **Ações**; `GET /customers` inclui `updated_at` (`customers_read` + serialize) |
| 7.7 | Editar: select cliente, init session, ViaCEP edição, form update, `update_customer_row` | Sim | `edit-customer-form.tsx` |
| 7.8 | **Excluir cliente** (admin): dois passos, `delete_customer_row`, bloqueio se houver vendas | Sim | `ConfirmDeleteForm` + `deleteCustomerForm` (só admin) |

---

## 8. Estoque (`PAGE_ESTOQUE`)

**Streamlit:** `require_admin()` no início da página; **CSS dedicado** forte (fonte ~49% escala) para grid compacto.

| # | Função | Streamlit | Protótipo |
|---|--------|-----------|-----------|
| 8.1 | Lista apenas produtos com **stock &gt; 0** | `fetch_products` filtrado | API `GET /inventory/lots` — alinhado ao modelo de lotes |
| 8.2 | Diálogo `@st.dialog` **Confirmar exclusão** antes de `reset_batch_pricing_and_exclude` | Sim | Fluxo de confirmação em `excludeInventoryBatches` / `ConfirmDeleteForm` |
| 8.3 | **Baixa manual**: qty **decimal** step 0.0001, checkbox confirmação, `apply_manual_stock_write_down` | Sim | `WriteDownForm`: `step={0.0001}`, checkbox + verificação em `manualWriteDown` — **paridade** |
| 8.4 | **Filtros** 11 dimensões **multiselect** (nome, SKU, atributos, custo, preço, margem, stock) | Sim | `inventory-filters.tsx`: checkboxes por dimensão + CSV na URL; `GET /inventory/lots` com listas CSV — **paridade** |
| 8.5 | **Ordenar** sku / name / stock_desc / stock_asc | `st.selectbox` | Select + query `sort` na API — **paridade** |
| 8.6 | **Totais** filtrados (stock total, valor custo, receita, margem) | Linha `total_row` | `InventoryTotalsBar` + campo `totals` na resposta de `GET /inventory/lots` — **paridade** sobre o conjunto filtrado |
| 8.7 | **Dataframe com seleção de linha única** para “Excluir lote selecionado” | `st.dataframe` `on_select` | **Checkboxes** por código de entrada + exclusão em lote — UX **diferente**, objetivo similar |
| 8.8 | Cálculo **markup** por linha (preço − custo) no grid | Sim | Colunas na tabela API — verificar se “margem” é coluna filtravel no protótipo |

---

## 9. Checklist UAT (`PAGE_UAT`)

| # | Função | Streamlit | Protótipo |
|---|--------|-----------|-----------|
| 9.1 | `require_operator_or_admin()` | Início `_render_uat_manual_checklist_page` | API: leitura com viewer; escrita com actor autenticado |
| 9.2 | Texto explicativo (formalização UAT, auditoria) | Sim | `PageHero` + copy |
| 9.3 | Hidratação session a partir de `fetch_map_for_tenant` | Sim | `fetchPrototypeUatRecords` |
| 9.4 | **Barra de progresso** “n de N casos não pendentes” | `st.progress` | **Ausente** |
| 9.5 | **Tabela resumo** global (ID, Caso, Estado BD, Data registo, Actualizado, Utilizador, Perfil) | `st.dataframe` | **Ausente** (só cards por caso) |
| 9.6 | Por caso: expander com descrição; select estado; notas; gravar → `upsert_uat_record` + `log_critical_event` | Sim | `UatCaseCard` com form + metadados “Último registro” |
| 9.7 | Casos e estados de `UAT_MANUAL_CASES` / `UAT_STATUS_*` | `services.uat_checklist_service` | `lib/domain.ts` — mesma origem documentada |

---

## 10. Funções auxiliares só Streamlit (não são “páginas”, mas fazem parte do produto)

| Função | Papel |
|--------|--------|
| `test_db_connection` | Debug Postgres na UI |
| `attribute_selectbox` | Select com placeholder |
| `fetch_viacep_address` | Também usado no protótipo indiretamente? No Next está no componente CEP — paridade de integração |
| `init_cust_edit_session` | Sincroniza session Streamlit |
| `_maybe_preview_product_sku` | Preview SKU cadastro |
| `_maybe_sidebar_database_export` | Download SQLite |
| `_render_uat_manual_checklist_page` | Página UAT |

---

## 11. Matriz rápida: área → paridade

| Área | Cobertura no protótipo | Lacunas principais vs Streamlit |
|------|------------------------|----------------------------------|
| Shell / ops | Parcial | Debug DB, backups SQLite, export DB, init/health na UI |
| Painel | **Forte** | **Giro de stock**; gráficos **Plotly** vs HTML; hero/cópia BI idênticos; bounds de datas na URL |
| Produtos | **Forte** | Pré-visualização **SKU ao vivo** no cadastro; expander único Streamlit vs filtros colapsáveis |
| Vendas | **Forte** | Passo extra de pré-visualização (aceite); resto alinhado |
| Custos | Médio | Por nome, qty texto 4 dec, totais ao vivo, entrada estoque amarrada ao custo estruturado + checkbox, histórico 75 linhas |
| Precificação | Forte | Localização por nome |
| Clientes | **Forte** | Modelo **abas** Streamlit vs **rotas** (`/new`, `/[id]/edit`); CEP não coluna na tabela principal (detalhe no formulário) |
| Estoque | **Forte** | **CSS** densidade / dataframe Streamlit vs tabela Next; seleção **checkbox** vs linha única — objetivo equivalente |
| UAT | Médio | Barra progresso + tabela resumo |

---

## 12. Referências de ficheiros (protótipo)

- Navegação: `web-prototype/components/top-nav.tsx`
- Dashboard: `web-prototype/app/(main)/dashboard/page.tsx`, `dashboard-filters.tsx`, `dashboard-data-section.tsx`, `lib/dashboard-url.ts`, `lib/dashboard-api.ts`
- Produtos: `web-prototype/app/(main)/products/*`, `lib/actions/products`, `components/attribute-select-with-other.tsx`, `lib/product-attribute-presets.ts`
- Vendas: `web-prototype/app/(main)/sales/new/new-sale-form.tsx`, `lib/actions/sales.ts`, `app/(main)/sales/page.tsx`, `lib/sales-api.ts`
- Custos: `web-prototype/app/(main)/costs/page.tsx`, `cost-structure-form.tsx`, `stock-receipt-form.tsx`
- Precificação: `web-prototype/app/(main)/pricing/page.tsx`, `pricing-workflow.tsx`
- Clientes: `web-prototype/app/(main)/customers/*`, `components/customer-cep-block`, `lib/customers-api.ts`
- Estoque: `web-prototype/app/(main)/inventory/page.tsx`, `inventory-filters.tsx`, `inventory-lots-interactive.tsx`, `write-down-form.tsx`, `lib/inventory-api.ts`, `lib/inventory-url.ts`
- UAT: `web-prototype/app/(main)/uat/page.tsx`, `uat-case-card.tsx`, `lib/uat-api.ts`, `api-prototype/routes/uat.py`

---

## 13. Conclusão

O **protótipo Next.js** cobre o **núcleo operacional** com paridade **alta** em **painel** (filtros avançados, KPIs com deltas, MM7, insights, margem por SKU, cohort, stock crítico, aging, valor CMP, breakdowns), **produtos** (lista TanStack, detalhe, “Outro” nos atributos, edição/exclusão), **vendas** (desconto %/fixo, pré-visualização em dois passos, tabela de 20 vendas recentes via API), **clientes** (tabela principal com colunas pedidas, ViaCEP, edição, exclusão com confirmação), **estoque** (multiselect por coluna, totais filtrados, baixa decimal + confirmação, exclusão em lote) e restantes módulos já descritos.

Para **paridade extrema** com o Streamlit, as diferenças que mais pesam são: **giro de stock** no painel; **Plotly** e peças de **marketing/hero** idênticos ao BI Streamlit; **Custos** (localizar por nome, histórico de entradas, fluxo de entrada de stock alinhado ao CMP + checkbox); **cadastro de produto** com **pré-visualização SKU ao vivo**; **shell** (debug DB / backups / export SQLite na UI); **UAT** (barra de progresso + tabela resumo global).
