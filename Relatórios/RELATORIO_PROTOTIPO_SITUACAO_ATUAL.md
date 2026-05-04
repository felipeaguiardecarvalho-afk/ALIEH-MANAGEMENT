# Relatório — situação atual do protótipo ALIEH (web + API)

**Âmbito:** `web-prototype/` (Next.js) e `api-prototype/` (FastAPI), integração com o **motor de negócio** do repositório (`services/`, `database/`, `analytics/`, etc.).  
**Data de referência:** 2026-05-05.  
**Última actualização deste documento:** 2026-05-05 — acrescenta **oitava passagem — validação de ambiente e gate QA** (`web-prototype/instrumentation.ts` + **`lib/env/alieh-runtime.ts`**): tier **produção** (`assertProductionServerEnv`), tier **staging** (`assertStagingServerEnv` — `AUTH_SESSION_SECRET` ≥32, `API_PROTOTYPE_URL`, `DATABASE_URL` / `SUPABASE_DB_URL`), **`assertStrictQaOrchestrationEnv`** quando **`ALIEH_STRICT_QA_ENV=1`** (conjunto alargado incl. `ALIEH_API_TEST_URL`, `ALIEH_E2E_*`, **`ALIEH_PROTOTYPE_OPEN=0`** — **só** em jobs de gate / orquestração, não em servidores de produção reais); validação de **`API_PROTOTYPE_URL`** vs porta do Next via **`getPrototypeApiBase()`** em produção/staging. **API:** `prototype_env.validate_staging_environment()` (DSN obrigatório em **`ALIEH_ENV=staging`**), compose QA com **`ALIEH_ENV=staging`** no serviço **qa-api**. **Pytest:** `ALIEH_QA_GATE=1` em `tests/conftest.py` falha cedo sem `DATABASE_URL` / `ALIEH_PG_INTEGRATION` / `ALIEH_API_TEST_URL`. **Playwright:** `tests/e2e/global-setup.ts` + **`ALIEH_STRICT_E2E=1`** no gate e no workflow CI. **`scripts/qa/validate_deployment_env.py`** (modo `qa-gate`). **Gate:** espera **`/health`** da API até **10 min** (primeira instalação `pip` no contentor). Mantém-se o bloco anterior (2026-05-04): **gate QA Docker** (`npm run test:qa:full:docker`, `scripts/qa/gate-runner.mjs`, `docker-compose.qa.yml` perfil **gate**), portas **36100** / **36101**, **`ALIEH_PROTOTYPE_OPEN=0`** em produção, **`NODE_ENV=production`** na API, password de seed `E2E_ci_change_me_!` (alinhada ao CI). Mantém-se a **segunda passagem de endurecimento** (idempotência com TTL, **`POST /sales/submit`**, cache de leitura na API, rate limits, logs JSON, **`/health`** OK/DEGRADED/FAIL, arranque estrito, deprecação `product-context`, ViaCEP **8 s**), a **terceira passagem de performance** ( **`React.cache`** em leituras RSC, dedupe in-flight de lotes por SKU, **`Promise.allSettled`** em produtos, debounces em vendas/precificação, **`React.memo`** na grelha de inventário, índice **`idx_sales_tenant_id_desc`** em `schema.sql`, nota de **keep-alive** no `fetch` da API), a **quarta passagem — percepção de performance na UI** (optimistic updates, caches em memória no cliente, aquecimento de dados em *layouts*, precificação com SWR/dedupe no cliente, botões de submissão opcionalmente não bloqueantes — **sem** alterar `services/`, contratos de API nem regras de negócio), a **quinta passagem — suite de testes SDET** (regressão **`pytest`** em `tests/` excepto `tests/api`, testes HTTP **`tests/api`** com marcador **`live_api`** e variável **`ALIEH_API_TEST_URL`**, E2E **Playwright** em **`tests/e2e`** com pacote Node dedicado e `playwright.config.ts` na mesma pasta; comandos na raiz `npm run test:unit` / `test:api` / `test:qa` / `test:qa:full` / `test:e2e` — inventário e lacunas em **`RELATORIO_COMPLETO_TESTES.md`**, veredicto resumido em **`RELATORIO_QA_READINESS.md`**) e a **sexta passagem — percepção “instantânea” (Next apenas)** (`lib/sale-batches-client-dedupe.ts` dedupe global in-flight por SKU no browser; **`new-sale-form.tsx`** sem debounce artificial no lote, cache-hit + refresh em segundo plano, prefetch até **24** SKUs + **`onPointerDown`** no select para prefetch de mais SKUs; TTL cliente lotes **120 s** e insight precificação **90 s**; debounce precificação **~40 ms**; **`sales/layout.tsx`** aquece também **`GET /inventory/lots/filter-options`**; **`top-nav.tsx`** prefetch em *cluster* ao pairar/focar **Vendas** (`/sales`, `/sales/new`, `/customers`, `/inventory`); tabela produtos debounce pesquisa **100 ms** — resumo técnico em **`web-prototype/docs/PERCEIVED_PERFORMANCE.md`**). **Segue-se** a **sétima passagem — estado global no cliente** (`zustand`, **`lib/client-data/store.ts`**, **`components/client-data-provider.tsx`**, Server Action **`lib/actions/client-data-bootstrap.ts`** / **`loadGlobalReadBundleAction`**, **`lib/customers-map.ts`**, integração na **Nova venda** e **TopNav**; documentação **`web-prototype/docs/CLIENT_DATA_PHASES.md`**).

**Registo de testes (2026-05-05):** ver **`RELATORIO_QA_READINESS.md`** — sem stack Postgres local: regressão Python **72 passed / 1 skipped** (`test_postgres_integration`). Com **`ALIEH_QA_GATE=1`** (injectado pelo *gate* Docker) o **pytest** falha no arranque se faltar `DATABASE_URL`, `ALIEH_PG_INTEGRATION=1` ou `ALIEH_API_TEST_URL`. O *gate* define **`ALIEH_STRICT_QA_ENV=1`** no build/start Next (validação alargada **só** nesse fluxo) e **`ALIEH_STRICT_E2E=1`** no Playwright. Com **`npm run test:qa:full:docker`** (Docker activo; espera até **10 min** por **`GET /health`** na API após `pip` no contentor) — **alvo: 0 skips**. CI: **`.github/workflows/production-readiness.yml`** (`ALIEH_STRICT_E2E=1` no job E2E, `ALIEH_PROTOTYPE_OPEN=0`, integração PG, seed e credenciais alinhadas).

---

## 1. Visão geral da arquitetura

### 1.1 Duas camadas de aplicação

| Camada | Tecnologia | Papel |
|--------|------------|--------|
| **UI protótipo** | Next.js (App Router), React, Tailwind, TanStack Table, `jose` (JWT na edge), **`zustand`** (estado global cliente) | Autenticação na borda, layouts, formulários, chamadas **server-side** à API; cache em memória entre rotas (`ClientDataProvider`). |
| **API protótipo** | FastAPI + Uvicorn | Expõe REST com cabeçalhos de contexto (`X-User-Id`, `X-Tenant-Id`, `X-Role`, opcionalmente `X-Username`). Delega em **código já existente** do monorepo (`services`, `database.repositories`, leitores em `api-prototype/*.py`). |

### 1.2 Motor de negócio (engine)

A **engine** não está duplicada dentro do protótipo: o `api-prototype/main.py` ajusta `sys.path` para:

1. **`api-prototype/`** — pacote local `routes`, `deps`, `audit_db`, módulos auxiliares (`customers_read.py`, `inventory_lots_read.py`, `pricing_read.py`, …).
2. **Raiz do repositório** — `services`, `database`, `analytics`, `utils`, etc.

Assim, regras de venda, custos, precificação, inventário e clientes **reutilizam** as mesmas funções que a app Streamlit e outros consumidores usam, garantindo paridade funcional quando os endpoints espelham fluxos Streamlit.

### 1.3 Persistência e infraestrutura

- **Postgres:** acesso via camada `database/` (psycopg / repositórios), com **tenant** propagado a partir de `Actor.tenant_id`.
- **Next.js `lib/db.ts`:** cliente `postgres` opcional (`DATABASE_URL` / `SUPABASE_DB_URL`) — **não** é o caminho principal das páginas `(main)` ligadas à API; serve como utilitário legado / possíveis scripts.
- **Supabase Storage:** uploads de imagem de produto via URL assinada (`routes/storage.py`), com variáveis `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, bucket configurável.
- **Auditoria protótipo:** tabela Postgres criada no lifespan (`audit_db.ensure_prototype_audit_table`), eventos via `POST /audit/events` e login pré-sessão via `POST /audit/login-ingest` (segredo `PROTOTYPE_AUDIT_INGEST_SECRET` / `X-Prototype-Audit-Secret`).
- **Idempotência de vendas:** tabela **`sale_idempotency_records`** (`database/sale_idempotency.py`), criada no **lifespan** da API (`ensure_sale_idempotency_table`). Permite retries seguros de `POST /sales/record` (e **`POST /sales/submit`**) com o mesmo **`Idempotency-Key`** (obrigatório no submit orquestrado) e o mesmo corpo lógico, sem duplicar vendas. Cada linha tem **`expires_at`** (TTL configurável, por defeito **24 h** via `SALE_IDEMPOTENCY_TTL_HOURS`); leituras ignoram linhas expiradas; a API executa **limpeza periódica** de linhas expiradas (arranque + tarefa horária em background).

### 1.4 Endurecimento (produção-ready, sem mudar regras de negócio)

| Área | O quê |
|------|--------|
| **Vendas — idempotência** | `Idempotency-Key` + hash do payload; lock consultivo Postgres por tenant+chave; resposta repetida em retry; **TTL** (`expires_at`) e **purge** de linhas expiradas; índice em `expires_at`. |
| **Vendas — submit orquestrado** | **`POST /sales/submit`**: na camada API apenas, chama `preview_record_sale` → monta `expected_*` → `record_sale` (**sem alterar** `services/sales_service.py`). O Next envia **um único** pedido para concluir a venda (com confirmação e validação de formulário vs último preview no cliente). |
| **Vendas — stock sob concorrência** | `SELECT … FOR UPDATE OF p` na leitura do produto na transacção de gravação (Postgres); `UPDATE … AND stock >= qty` com verificação de linha afectada. |
| **Vendas — alinhamento preview/record** | Em `POST /sales/record` continua opcional o trio `expected_*`; no fluxo **`/sales/submit`** o servidor deriva-os do preview interno. |
| **Next — cache de leituras autenticadas** | **Não** se usa `unstable_cache` em chamadas que passam por `apiPrototypeFetchRead` / `cookies()`. Listas no Next usam **`cache: "no-store"`**; **cache TTL curto (30–60 s típico)** aplicado **só na FastAPI** (`safe_read_cache.py`) em `GET /customers`, `GET /sales/saleable-skus`, `GET /inventory/batches` (`PROTOTYPE_READ_CACHE_TTL_SECONDS`, default **45**). **Invalidação** após vendas, mutações de clientes e mutações de inventário afectam esse cache em memória (o stock crítico da venda continua a vir do **preview/submit** no servidor, não desse cache). |
| **Rate limiting** | Janela deslizante em memória por utilizador: vendas (`/sales/preview`, `/sales/submit`, `/sales/record`) e escritos de inventário (`PROTOTYPE_RATE_LIMIT_*`, `PROTOTYPE_RATE_LIMIT_WINDOW_SEC`). Resposta **429** quando excedido. |
| **Observabilidade HTTP** | Middleware `CorrelationAndAccessLogMiddleware`: **`X-Request-Id`**, uma linha de log **JSON** por pedido com `endpoint`, `actor_id`, `tenant_id`, `duration_ms`, `success`, `status_code`, contadores cumulativos (`prototype_metrics.py`). |
| **Contexto actor para logs** | `deps.py` regista actor após `_parse_actor` bem-sucedido (`request_context.py`); limpeza no início de cada pedido no middleware. |
| **Erros não tratados** | Handler global em `main.py` devolve JSON seguro; `HTTPException` continua a ser tratada pelo handler padrão do FastAPI. |
| **Health** | `sales_paths`, **`check_database_health`** com **timeout 5 s** (thread pool), sonda **`core_tables`**; **`status`** agregado **`OK`**, **`DEGRADED`** (latência alta na sonda) ou **`FAIL`** (BD ou sonda a falhar); blocos `database_status` / `core_tables_status` por componente. |
| **Arranque estrito (opcional)** | `API_PROTOTYPE_STRICT_STARTUP=1`: falha ao subir a API se a BD não responder no `validate_prototype_startup`. |
| **Timeouts externos** | ViaCEP no cliente com `AbortController` (**8 s**); cliente Supabase na API com `httpx` e **`SUPABASE_HTTP_TIMEOUT_SECONDS`** (default 15 s). |
| **Clientes API** | Normalização de entradas nos modelos Pydantic (`strip`, CPF/telefone só dígitos) antes de chamar serviços. |

### 1.4.1 Validação de ambiente no arranque (sem alterar `services/`)

| Componente | Comportamento |
|--------------|----------------|
| **Next — `instrumentation.ts`** | Chama `assertStrictQaOrchestrationEnv` (só actua com **`ALIEH_STRICT_QA_ENV=1`**), depois validação por **tier** (`assertProductionServerEnv` / `assertStagingServerEnv`) e **`getPrototypeApiBase()`** (URL da API ≠ porta do Next em **produção** e **staging**). |
| **Next — `lib/env/alieh-runtime.ts`** | `getAliehEnv()` distingue **development** / **staging** / **production**; produção exige **`ALIEH_PROTOTYPE_OPEN=0`** explícito; staging exige segredo de sessão ≥32, DSN e `API_PROTOTYPE_URL`. |
| **API — `prototype_env.py`** | Produção: DSN + **`ALIEH_PROTOTYPE_OPEN=0`** (incl. **`NODE_ENV=production`**); **staging**: DSN obrigatório (`validate_staging_environment`). |
| **Gate Docker — `gate-runner.mjs`** | Exige **`DATABASE_URL`** (Supabase); **`python -m database.schema_apply`** + seed no host; Docker **`qa-api`** + **`qa-web`** (Next com `API_PROTOTYPE_URL=http://qa-api:8000`); **pytest** com **`ALIEH_QA_GATE=1`**. Sem Postgres em Docker. |
| **Operação — `scripts/qa/validate_deployment_env.py`** | Modo `qa-gate`: verifica `DATABASE_URL`, `ALIEH_PG_INTEGRATION`, `ALIEH_API_TEST_URL` antes de correr suites dependentes (opcionalmente invocado a partir de scripts de operação). |

### 1.5 Performance (Next.js + dados, sem alterar engine nem contratos)

| Área | O quê |
|------|--------|
| **Dedupe no mesmo render RSC** | Funções exportadas em `lib/customers-api.ts`, `lib/sales-api.ts`, `lib/inventory-api.ts` (lista de lotes + opções de filtro), `lib/costs-api.ts` (`fetchCostsSkuOptions`) envolvem o `fetch` com **`React.cache`** — chamadas idênticas na mesma árvore de Server Components fazem **um único** pedido HTTP. A lista de lotes usa chave estável `inventoryLotsFetchCacheKey` em `lib/inventory-url.ts`. |
| **Lotes por SKU (vendas)** | `fetchPrototypeBatchesForSkuCached` deduplica pedidos **in-flight** por SKU (mesma `Promise` para concorrência / troca rápida no select). |
| **Produtos `/products`** | `fetchPrototypeProductAttributeOptions` e `fetchPrototypeProductList` em **`Promise.allSettled`** — carregamento paralelo; falha de atributos continua a degradar para `null` no merge (`mergeDomainWithApiAttributeOptions`). |
| **UX / menos rede** | **Nova venda:** carregamento de lotes **sem debounce** no `useEffect` (resposta imediata quando há cache; primeira carga via `useTransition`); dedupe **global no cliente** (`sale-batches-client-dedupe.ts`) além do dedupe RSC em `fetchPrototypeBatchesForSkuCached`. **Precificação:** debounce **~40 ms** antes de `scheduleComputePreview` e antes de `loadInsight` ao mudar SKU (`pricing-workflow.tsx`). **Produtos (tabela):** debounce de pesquisa global **100 ms** (`components/data-table.tsx`). |
| **Inventário — grelha** | `inventory-lots-interactive.tsx`: linhas em componente **`React.memo`** com comparação que limita re-renders ao rádio seleccionado; chave de linha `product_id` + código de entrada. |
| **Índice SQL** | `schema.sql`: **`idx_sales_tenant_id_desc`** em `sales (tenant_id, id DESC)` para alinhar a listagens **ORDER BY id DESC** (vendas recentes); em bases já existentes pode ser necessário aplicar o `CREATE INDEX` manualmente se o ficheiro de schema não for reexecutado. |
| **Rede** | Comentário em `lib/api-prototype.ts`: o **`fetch`** do Node (undici) reutiliza ligações **keep-alive** por defeito para o mesmo host da API. |

### 1.6 Percepção de performance (cliente Next apenas)

Alterações **só** em `web-prototype/` — o motor em `services/` e os contratos REST **não** foram modificados para este efeito.

| Área | O quê |
|------|--------|
| **Cache de lotes para venda (browser)** | `lib/prototype-client-cache.ts`: TTL **~120 s** por SKU; **invalidação** após venda concluída; **prefetch em segundo plano** de até **24** SKUs no mount; **`loadSaleBatchesDeduped`** partilha a mesma *Promise* entre prefetch, `useEffect` e abertura do select. |
| **Nova venda — optimistic** | `new-sale-form.tsx`: **`useOptimistic`** no **submit**; com dados em cache, lotes mostram-se **de imediato** e o refresh vai em **segundo plano** (sem `useTransition` → evita “A sincronizar…” só por revalidar); **`onPointerDown`** no select de SKU dispara prefetch de mais SKUs ainda não cacheados. |
| **Layouts — aquecimento** | `app/(main)/sales/layout.tsx`: `Promise.all` de SKUs vendáveis + clientes + **`fetchPrototypeInventoryLotOptions`** (opções de filtro de lotes — **Estoque** mais rápido após **Vendas**). `customers/layout.tsx`, `inventory/layout.tsx`, `pricing/layout.tsx`: *warm* como antes. |
| **Navegação — prefetch** | `components/top-nav.tsx`: **`router.prefetch(href)`** em `onMouseEnter` e **`onFocus`**; ao apontar **Vendas**, prefetch em *cluster* de `/sales`, `/sales/new`, `/customers`, `/inventory`. |
| **Precificação — insight no cliente** | `lib/pricing-insight-client-cache.ts`: cache TTL **~90 s** + **dedupe in-flight** do trio snapshot / registos / histórico; **`invalidatePricingInsightCache`** após guardar. |
| **Precificação — optimistic e UX** | `pricing-workflow.tsx`: **`useOptimistic`** na mensagem (**«A activar precificação no servidor…»**) e nas linhas **`SkuMasterRow`** (preço de venda mostrado = preço alvo ao submeter); painel de histórico com **stale-while-revalidate** (conteúdo anterior com opacidade, aviso se o SKU do snapshot ainda não corresponde ao seleccionado, fila curta de “A carregar…” só sem dados nenhuns); **`SubmitButton`** com **`blockWhilePending={false}`** no guardar. |
| **Baixa de stock** | `write-down-form.tsx`: **`useOptimistic`** nos lotes (stock desce de imediato na lista local) + mensagem **«A registar baixa no servidor…»**; rollback automático se a API devolver erro. |
| **Clientes (criar / editar)** | `new-customer-form.tsx`, `edit-customer-form.tsx`: **`useOptimistic`** na mensagem (**«A registar…»** / **«A guardar alterações…»**); **`SubmitButton`** com **`blockWhilePending={false}`**. |
| **`SubmitButton`** | `components/form-status.tsx`: prop opcional **`blockWhilePending`** (default **`true`**) — onde está `false`, o botão não fica desactivado durante `pending` (o servidor continua a validar; reduz sensação de UI “congelada”). |

---

## 2. Autenticação, autorização e tenant

### 2.1 Next.js — middleware (`web-prototype/middleware.ts`)

- Rotas protegidas: exige cookie de sessão (`alieh_session`) válido com `AUTH_SESSION_SECRET`, salvo exceções.
- **`ALIEH_PROTOTYPE_OPEN=1`:** desativa a exigência de login no middleware (modo aberto só para desenvolvimento do protótipo). Em **tier produção** (`ALIEH_ENV=production` / `VERCEL_ENV=production` no Next, ou equivalente na API), o valor tem de ser **`0`** explicitamente — caso contrário o arranque **falha** (fail-fast).
- `/login`: se já houver sessão válida, redireciona para `/dashboard`.

### 2.2 Sessão e JWT (`lib/auth/*`)

- Sessão httpOnly; verificação na edge com `jose`.
- Claims usados para resolver utilizador, papel e opcionalmente tenant na camada servidor.

### 2.3 Tenant e papéis (`lib/tenant.ts`, `lib/tenant-env.ts`)

- **Tenant:** sessão → cookie `alieh_tenant` → env (`ALIEH_TENANT_ID` / default).
- **Papel:** sessão → cookie `alieh_role` → em modo aberto `ALIEH_PROTOTYPE_DEFAULT_ROLE` (default `viewer`).
- **`canMutate`:** apenas `admin` e `operator` podem mutações de negócio coerentes com `gateMutation()` em `lib/api-prototype.ts`.

### 2.4 Cabeçalhos para a API (`lib/api-prototype.ts`)

- **`prototypeAuthHeaders()`:** mutações — exige `admin` ou `operator`; monta `X-User-Id`, `X-Tenant-Id`, `X-Role`, `X-Username`. Em excesso de pedidos, a API pode responder **429** (rate limit) em vendas ou escritos de inventário.
- **`prototypeAuthHeadersRead()`:** leituras que podem incluir **`viewer`** (ex.: vendas recentes, clientes, SKUs vendáveis).
- **Modo aberto sem user na sessão:** exige `API_PROTOTYPE_USER_ID` (e opcionalmente `API_PROTOTYPE_USERNAME`).
- **Proteção de configuração:** `API_PROTOTYPE_URL` **não pode** apontar para a mesma porta que o Next em `localhost`/`127.0.0.1` (evita apontar por engano para o próprio Next e receber 404 em rotas de vendas).

### 2.5 FastAPI — `api-prototype/deps.py`

- **`get_actor`:** apenas `admin`, `operator` (mutações).
- **`get_actor_read`:** `admin`, `operator`, `viewer`.
- **`get_admin_actor`:** operações estritamente administrativas em rotas que o utilizem.
- Após autenticação bem-sucedida, **`request_context`** regista `user_id`, `tenant_id` e `role` para os **logs JSON** do middleware (limpos no início de cada pedido).

---

## 3. API protótipo — inventário de domínios

Prefixos montados em `main.py` (ordem de inclusão dos routers). Segue o mapa funcional por área.

### 3.1 Custos — `/costs`

| Método | Caminho | Função resumida |
|--------|---------|-----------------|
| GET | `/costs/sku-masters` | Lista mestres de SKU com stock, CMP, preço de venda, custo estruturado, avaliação. |
| GET | `/costs/sku-options` | Lista de SKUs + picker «por nome» (rótulos nome — armação — lente), paridade Streamlit. |
| GET | `/costs/composition` | Estado da composição de custo por SKU (componentes + total gravado). |
| POST | `/costs/preview-composition` | Pré-visualização de totais por linha (parsing no servidor). |
| GET | `/costs/stock-cost-history` | Histórico de custo de stock. |
| POST | `/costs/parse-quantity-text` | Validação/parse de texto de quantidade. |
| GET | `/costs/stock-entry` | Contexto de entrada de stock: custo unitário estruturado, lotes, componentes (leitura). |

As mutações de composição / persistência de custos expostas neste router limitam-se, neste ficheiro, a **`POST /preview-composition`** e **`POST /parse-quantity-text`**; outras gravações podem estar noutros routers ou serviços invocados pelo Streamlit.

### 3.2 Auditoria — `/audit`

| Método | Caminho | Função resumida |
|--------|---------|-----------------|
| POST | `/audit/events` | Append-only de eventos autenticados (`Actor`). |
| POST | `/audit/login-ingest` | Trilha de login antes de sessão (segredo partilhado). |

### 3.3 Vendas — `/sales`

| Método | Caminho | Função resumida |
|--------|---------|-----------------|
| GET | `/sales/saleable-skus` | SKUs elegíveis para venda (leitura; `get_actor_read`); resposta pode servir-se de **cache TTL** in-process na API (`safe_read_cache`). |
| POST | `/sales/preview` | Pré-visualização de venda (preço, desconto, total, stock, cliente); sujeito a **rate limit**. |
| POST | `/sales/submit` | **Orquestração única** para concluir venda: `preview_record_sale` → `record_sale` com `expected_*` derivados no servidor (**cabeçalho `Idempotency-Key` obrigatório**, até 128 caracteres); **rate limit**; invalidação do cache de leituras seguras; **purge** best-effort de idempotência expirada. |
| POST | `/sales/record` | Gravação directa (`sales_service.record_sale`): **`Idempotency-Key`** opcional; **`expected_*`** opcionais (três em conjunto); **rate limit**; mesmo padrão de erros **409** / `detail` estruturado; mantido para integrações que não usem `/sales/submit`. |
| GET | `/sales/product-context/{product_id}` | Contexto de produto para UI; **deprecado** para o fluxo web — resposta inclui cabeçalhos **`Deprecation: true`** e **`Link`** para `preview`. |
| GET | `/sales/recent` | Lista paginada de vendas recentes para UI (`limit` 1–500). |

**Arredondamento monetário:** o preview aplica arredondamento JSON coerente com o total após gravação (2 casas decimais).

**Contrato de erros em `POST /sales/record` e `POST /sales/submit`:** para falhas de validação / idempotência / preview desactualizado, a resposta pode trazer `detail` como **objecto JSON** (não só string). O protótipo Next (`readApiError`) extrai `detail.message` quando existir.

**`GET /health` — contagem de rotas:** esperam-se **seis** caminhos sob `/sales/*` (incluindo **`/sales/submit`**).

### 3.4 Painel — `/dashboard`

| Método | Caminho | Função resumida |
|--------|---------|-----------------|
| GET | `/dashboard/filters` | Opções de filtros (datas, granularidade, etc.). |
| GET | `/dashboard/panel` | Dados agregados do painel (usa `pandas`, repositórios BI, SQL compat). |

### 3.5 Produtos — `/products`

Inclui: opções de atributos, listagem filtrada/paginada, preview de corpo SKU, imagem (ficheiro / bytes / URL pública), detalhe por id, delete SKU, geração de SKU, atualização de atributos, cost-structure, criação (`POST ""`), validação de URLs Supabase públicas.

### 3.6 Clientes — `/customers`

| Método | Caminho | Função resumida |
|--------|---------|-----------------|
| GET | `/customers` | Lista (leitura ampla); pode usar **cache TTL** in-process na API; invalidado após mutações de clientes ou de dados que afectem listas de venda. |
| GET | `/customers/{id}` | Detalhe. |
| POST | `/customers` | Criação via `customer_service` (invalida cache de listas seguras na API). |
| PUT | `/customers/{id}` | Atualização (invalida cache). |
| DELETE | `/customers/{id}` | Remoção (com políticas do serviço; invalida cache). |

**Normalização na API:** o modelo `CustomerFields` aplica `strip` em vários campos e reduz **CPF** / **telefone** a dígitos (`utils.validators`) antes de persistir — o frontend não é a única fonte de saneamento.

### 3.7 Inventário — `/inventory`

| Método | Caminho | Função resumida |
|--------|---------|-----------------|
| GET | `/inventory/batches` | Lotes com stock > 0 por SKU (paridade vendas / Streamlit); pode usar **cache TTL** in-process por tenant+SKU; invalidado após vendas ou mutações de inventário. |
| GET | `/inventory/lots/filter-options` | Opções de filtro da grelha de lotes. |
| GET | `/inventory/lots` | Busca paginada de lotes com múltiplos filtros CSV e totais. |
| POST | `/inventory/batches/exclude` | Exclusão lógica / exclusão de lotes conforme implementação (**rate limit** em escritos). |
| POST | `/inventory/stock-receipt` | Recebimento de stock (**rate limit**). |
| POST | `/inventory/manual-write-down` | Baixa manual (**rate limit**). |
| GET | `/inventory/product/{product_id}/stock-name-sku` | Síntese stock/nome/SKU por produto. |

### 3.8 Precificação — `/pricing`

Endpoints para lista mestre, snapshot por SKU, histórico de registos e de preços, POST de preço de venda, cálculo de alvos, workflow, linha de produto, batch lock/reset/clear.

### 3.9 UAT — `/uat`

| Método | Caminho | Função resumida |
|--------|---------|-----------------|
| GET | `/uat/records` | Mapa de registos UAT por tenant. |
| POST | `/uat/upsert` | Upsert de estado de teste. |

**Nota UI:** a navegação **Next** do protótipo **não** expõe página UAT dedicada (foi removida do fluxo web); a **API** mantém estes endpoints para integrações ou ferramentas.

### 3.10 Storage — `/storage`

| Método | Caminho | Função resumida |
|--------|---------|-----------------|
| POST | `/storage/signed-upload` | Mint de URL assinada Supabase (tipos MIME de imagem permitidos, path por tenant). |

O cliente Supabase usa **`httpx`** com timeout configurável (**`SUPABASE_HTTP_TIMEOUT_SECONDS`**, por defeito 15 s); se a versão da biblioteca não aceitar `ClientOptions(httpx_client=…)`, faz-se fallback para `create_client` simples.

### 3.11 Saúde — `/health`

Resposta JSON inclui:

- **`status`:** agregado **`OK`**, **`DEGRADED`** ou **`FAIL`** — `FAIL` se a ligação à BD falhar ou a sonda `core_tables` falhar; `DEGRADED` se latências excederem limiar (sondas lentas mas bem-sucedidas); `OK` no caso contrário.
- **`prototype`:** `true`.
- **`sales_paths`:** lista ordenada de rotas registadas sob `/sales/*` (ver secção 3.3 — **seis** entradas esperadas com o submit orquestrado).
- **`dependencies`:** objecto com blocos **`database`** (`ok`, `latency_ms`, `error_type` em falha ou timeout da sonda) e **`core_tables`** (prova de leitura mínima, `latency_ms`, `error_type` se aplicável), mais **`database_status`** e **`core_tables_status`** por componente (`OK` / `DEGRADED` / `FAIL`).

A sonda de **`check_database_health`** corre com **timeout de 5 s** (evita pedidos de health pendurados indefinidamente).

### 3.12 Middleware e logging

- **`CorrelationAndAccessLogMiddleware`:** gera ou propaga **`X-Request-Id`**; emite **uma linha JSON** por pedido (logger `alieh.prototype.http`) com `event`, `request_id`, `endpoint`, `method`, `actor_id`, `tenant_id`, `role`, `duration_ms`, `status_code`, `success`, e contadores cumulativos (`cumulative_requests`, `cumulative_errors`, `cumulative_sales_submit_ok`).
- **`POST /sales/submit` e `POST /sales/record`:** após gravação bem-sucedida, logs `sale_submit_ok` / `sale_record_ok` com tenant, utilizador, `sale_code`, produto, cliente, quantidade e total (logger `alieh.prototype.sales`).
- **Lifespan:** além de `ensure_prototype_audit_table` e `ensure_sale_idempotency_table`, arranque com **`validate_prototype_startup`** opcional e tarefa em background de **purge** de idempotência expirada (aprox. horária).

---

## 4. Web protótipo — funcionalidades por área

Todas as páginas principais em `app/(main)/` descritas abaixo dependem de **`API_PROTOTYPE_URL`** apontando para a instância FastAPI correta (tipicamente porta **8000**, **nunca** a mesma porta do Next).

### 4.1 Navegação global (`components/top-nav.tsx`)

Secções: **Painel**, **Produtos**, **Custos**, **Precificação**, **Estoque**, **Clientes**, **Vendas** — mais **Sair** (server action de logout).  
**Prefetch:** em `onMouseEnter` sobre os destinos principais chama-se **`router.prefetch(href)`** para antecipar rotas antes do clique (complementa `prefetch` em `Link` onde existir).

### 4.2 Painel — `/dashboard`

- Filtros carregados via `fetchPrototypeDashboardFilters` (`lib/dashboard-api.ts` → `GET /dashboard/filters`).
- Dados do painel: `fetchPrototypeDashboardPanel` → `GET /dashboard/panel` com query alinhada aos filtros.
- Componentes: `dashboard-filters.tsx`, `dashboard-data-section.tsx`, `loading.tsx`.

### 4.3 Produtos — `/products`, `/products/new`, detalhe e imagens

- Listagem, filtros, KPIs, galeria, comando de cabeçalho: tipos e dados vindos de `lib/products-api.ts` (`fetchPrototypeProductList`, `fetchPrototypeProductDetail`, opções de atributos, imagem em disco / URL pública).
- **SSR da listagem:** em `page.tsx`, opções de atributos e lista de produtos carregam em **paralelo** (`Promise.allSettled`), reduzindo latência inicial face à sequência anterior.
- **Novo produto:** `new/page.tsx` obtém `fetchPrototypeProductAttributeOptions`; formulário em `new-product-form.tsx`.
- **Edição de lote / foto / SKU:** formulários ligados a server actions em `lib/actions/products.ts` (e upload via `lib/actions/product-image-upload.ts` / Supabase conforme configuração).
- **RBAC:** ações restritas a operadores conforme `lib/rbac.ts` e `gateMutation` onde aplicável.

### 4.4 Custos — `/costs`

- Página orquestra `fetchCostsSkuMasters`, `fetchCostsSkuOptions`, `fetchStockCostHistory` (`lib/costs-api.ts`).
- **`fetchCostsSkuOptions`** está memoizada com **`React.cache`** — se a mesma request do servidor invocar a função mais do que uma vez, o resultado é reutilizado (sem segundo round-trip).
- UI em componentes: abas, painéis laterais, KPIs, formulários de estrutura de custo e recebimento de stock (`costs-tabs.tsx`, `costs-side-panels.tsx`, `stock-receipt-form.tsx`, `cost-structure-form.tsx`, etc.).
- Paridade com fluxos de custos Streamlit (labels, preview de composição, parsing de quantidades).

### 4.5 Precificação — `/pricing`

- Lista mestre: `fetchPrototypeSkuMasterList` + opções de SKU reutilizando `fetchCostsSkuOptions`.
- Workflow interactivo: `pricing-workflow.tsx` com tipos de `lib/pricing-api.ts` (snapshot, registos, histórico, mutações de workflow / preço / batch).
- **Troca de SKU:** `loadInsight` com debounce **~40 ms**; o trio de pedidos passa por **`loadPricingInsightBundleCached`** (`lib/pricing-insight-client-cache.ts`) — cache TTL **~90 s** + dedupe in-flight no **browser**; após **Salvar**, invalidação desse cache e refetch do SKU activo.
- **Optimistic UI:** mensagem imediata ao submeter; **preço ativo** no contexto do SKU actualizado de imediato para o **preço alvo** calculado (reverte se o servidor falhar). Painel de histórico: sincronização em segundo plano sem substituir todo o conteúdo por um ecrã vazio de loading sempre que possível.
- **Layout:** `app/(main)/pricing/layout.tsx` pode aquecer lista mestre + opções de SKU antes das páginas filhas.

### 4.6 Estoque — `/inventory`

- Dados: `fetchPrototypeInventoryLots`, `fetchPrototypeInventoryLotOptions` (`lib/inventory-api.ts`).
- **Lotes por SKU (fluxo vendas):** `fetchPrototypeBatchesForSkuCached` — chamada directa a `GET /inventory/batches` (usada por `loadSaleBatchesAction` / **`loadSaleBatchesDeduped`** no cliente); **sem** `unstable_cache` no Next; a **API** pode servir tenant+SKU a partir de **cache TTL** in-process, invalidado após mutações de inventário ou vendas.
- Grelha interactiva (`inventory-lots-interactive.tsx`): linhas memoizadas com **`React.memo`** e chaves estáveis (`product_id` + código de entrada) para menos re-renders ao seleccionar exclusão de lote.
- Filtros, baixa manual (`write-down-form.tsx` — **optimistic** na lista de lotes e na mensagem; **`SubmitButton`** não bloqueante durante `pending`), acções em `lib/actions/inventory.ts`.
- URLs de estado: `lib/inventory-url.ts` (inclui **`inventoryLotsFetchCacheKey`** para dedupe de `fetchPrototypeInventoryLots` no RSC).
- **Layout:** `app/(main)/inventory/layout.tsx` pode aquecer opções de filtro de lotes.

### 4.7 Clientes — `/customers`, `/customers/new`, `/customers/[id]/edit`

- Lista: `fetchPrototypeCustomersList` — fetch directo no Next (**sem** `unstable_cache`); a **API** pode aplicar **cache TTL** in-process em `GET /customers`, invalidado após POST/PUT/DELETE de clientes ou outras mutações que afectem listas de venda.
- Edição: `fetchPrototypeCustomer` + formulário alinhado a `CustomerApiRow`.
- Criação e mutações: `lib/actions/customers.ts` com `gateMutation` / API.
- **Formulários:** `new-customer-form.tsx` e `edit-customer-form.tsx` usam **`useOptimistic`** na mensagem de estado (**feedback imediato** antes da resposta do servidor) e **`SubmitButton`** com **`blockWhilePending={false}`**.
- **ViaCEP** (`components/customer-cep-block.tsx`): pedido `fetch` com **`AbortController`** e timeout **8 s** (evita bloqueio prolongado em rede lenta).
- **Layout:** `app/(main)/customers/layout.tsx` pode aquecer a lista de clientes para a árvore `/customers/*`.

### 4.8 Vendas — `/sales` e `/sales/new`

**Lista `/sales`**

- Dados: `fetchPrototypeRecentSales` com limite **`STREAMLIT_RECENT_SALES_LIMIT` = 20** (`lib/sales-api.ts` → `GET /sales/recent?limit=…`; função memoizada com **`React.cache`** por limite normalizado).
- Leitura usa **`prototypeAuthHeadersRead`** (permite `viewer`).
- Tabela: formatação defensiva de datas (`lib/format.ts`), chaves estáveis.
- `revalidate = 120` na página.

**Nova venda `/sales/new`**

- SSR: em paralelo `fetchPrototypeSaleableSkus()` e `fetchPrototypeCustomersList()` (ambas com **`React.cache`** no `*-api.ts`; **sem** `unstable_cache` no Next — ver secções 1.4 e 1.5; a API pode cachear leituras seguras por TTL). O **`app/(main)/sales/layout.tsx`** aquece em paralelo SKUs, clientes e **`fetchPrototypeInventoryLotOptions`** para `/sales` e `/sales/new`.
- Formulário cliente (`new-sale-form.tsx`):
  - Passo SKU → **`loadSaleBatchesDeduped`** (cliente) → **`loadSaleBatchesAction`** → **`fetchPrototypeBatchesForSkuCached`** (`GET /inventory/batches`; dedupe **in-flight** no servidor **e** no browser por SKU).
  - **Cache em memória** (`lib/prototype-client-cache.ts`) por SKU com TTL **~120 s**; **prefetch** em segundo plano de até **24** SKUs; ao abrir o dropdown de SKU, prefetch adicional de até **16** SKUs ainda não cacheados.
  - **Sem debounce** no efeito de mudança de SKU: se há cache, UI actualiza na hora e revalida em silêncio; sem cache, **`useTransition`** mostra **«A sincronizar…»** apenas na primeira carga.
  - **`useOptimistic`** no estado do formulário: no **submit** final, mensagem imediata **«A concluir venda no servidor…»** (reconcilia com a resposta real; reverte em erro).
  - Cliente (com busca local), quantidade, desconto (% ou fixo), pagamento (`SALE_PAYMENT_OPTIONS` em `lib/domain.ts`).
  - Botões de submissão: **`useFormStatus`** em `SubmitButton` (default **`blockWhilePending`**) — o botão **«Atualizar resumo»** continua a respeitar `pending` para evitar cliques em cima do preview; o fluxo privilegia feedback otimista na **conclusão**.
  - **`submitSaleForm`** (`lib/actions/sales.ts`):  
    - `requireOperator` + `gateMutation`;  
    - intent **«preview»:** apenas **`POST /sales/preview`** (actualizar resumo);  
    - intent **submit (conclusão):** validação de checkbox, **`previewStaleMatchesForm`** contra o último preview mostrado (sem segundo round-trip de preview no cliente);  
    - **`POST /sales/submit`** com cabeçalho **`Idempotency-Key`** (`crypto.randomUUID()` por tentativa) e corpo alinhado ao preview (producto, quantidade, cliente, desconto, pagamento) — o servidor executa preview + record na mesma orquestração;  
    - após sucesso: `logPrototypeAuditEvent("sales", "record_sale", …)` e **`revalidatePath`** para `/sales`, `/dashboard`, `/inventory`.  
  - O caminho **`POST /sales/record`** com `expected_*` manual permanece na API para outros clientes; o fluxo Next usa **`/sales/submit`**.
- **`readApiError`** (`lib/api-prototype.ts`): suporta `detail` em formato **objecto** (campo `message`) para mensagens legíveis quando a API devolve erros estruturados.

### 4.9 Login — `/login`

- `login-form.tsx`, actions em `lib/actions/auth.ts`, ingestão de auditoria de tentativas via `logPrototypeLoginIngest` quando configurado.

---

## 5. Scripts e ferramentas de desenvolvimento

- **`npm run dev`** — Next na porta **3000** (por defeito).
- **`npm run dev:fresh`** — mata processo na porta 3000 e sobe Next (evita `EADDRINUSE`).
- **`npm run test:customers`** — script Node com `--env-file=.env` para teste de criação de cliente.
- **API:** `python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000` a partir de **`api-prototype/`** (ver `requirements.txt`).

### 5.1 QA / testes automatizados (raiz do repositório)

| Comando | Descrição |
|---------|-----------|
| `npm run test:unit` | `pytest tests` com exclusão de `tests/api` — regressão Python (RBAC, vendas concorrentes, auditoria, backup, config de BD, etc.). |
| `npm run test:api` | `pytest tests/api -m live_api` — smoke e contratos contra API em execução; requer **`ALIEH_API_TEST_URL`** (ex. `http://127.0.0.1:8000`) apontando para a **api-prototype** real (validação via formato de `GET /health`). |
| `npm run test:qa` | `test:unit` seguido de `test:api`. |
| `npm run test:e2e` | Playwright: `npm --prefix tests/e2e run test` — inclui **`smoke.spec.ts`** e **`flows.spec.ts`** (fluxos autenticados com `ALIEH_E2E_PASSWORD`). Config em **`tests/e2e/playwright.config.ts`**. Primeira vez: `cd tests/e2e && npm install && npx playwright install chromium`. |
| `npm run test:pg` | Apenas **`tests/test_postgres_integration.py`** — requer `ALIEH_PG_INTEGRATION=1` e `DATABASE_URL`. |
| `npm run test:gate` | `test:unit` + `test:api` + `test:pg` + `test:e2e` (ambiente completo). |
| `npm run test:qa:full` | `test:qa` + `test:e2e` (Next deve estar acessível na **3000** para o E2E passar). |
| `npm run test:qa:full:docker` | *Gate*: **`DATABASE_URL`** (Supabase = Streamlit); no host **`database.schema_apply`** + seed; Docker só **`qa-api`** (**36101**) + **`qa-web`** (**3000**, build no contentor); `pytest` + Playwright. Ver **`scripts/qa/README.md`**. |

Documentação de apoio: **`tests/QA_SUITE.md`**, **`Relatórios/RELATORIO_COMPLETO_TESTES.md`**, **`Relatórios/RELATORIO_QA_READINESS.md`**, **`docs/DEPLOYMENT_ARCHITECTURE.md`**, **`docs/PRODUCTION_READINESS_CHECKLIST.md`**, **`web-prototype/docs/PERCEIVED_PERFORMANCE.md`**, **`web-prototype/docs/CLIENT_DATA_PHASES.md`**.

---

## 6. Código legado / paralelo no web-prototype

- **`lib/queries.ts`:** camada antiga com `unstable_cache`, SQL directo opcional e **dados mock** de fallback — **não há imports** nas rotas `app/` actuais; o fluxo activo passa pelos módulos `*-api.ts` e actions que chamam `api-prototype`.
- **Página UAT no Next:** removida da navegação e do fluxo principal; a API `/uat/*` permanece disponível.

---

## 7. Riscos, limitações e boas práticas operacionais

1. **Processo FastAPI desactualizado:** se `GET /health` não listar as **seis** rotas esperadas em `sales_paths` (incluindo `/sales/submit`), o binário em execução não corresponde ao código actual — **reiniciar** Uvicorn a partir de `api-prototype/` e garantir que nada mais ocupa a porta com outra versão.
2. **`GET /health` com `status: "FAIL"` ou `"DEGRADED"`:** `FAIL` — BD inacessível, timeout da sonda ou sonda `core_tables` a falhar; `DEGRADED` — sondas lentas mas bem-sucedidas. Rever DSN, rede, permissões e logs JSON do middleware (`alieh.prototype.http`).
3. **`API_PROTOTYPE_URL` incorrecta:** apontar para o Next (mesma porta) quebra vendas e stock; o código falha cedo com mensagem explícita.
4. **Variáveis de ambiente:** tenant por defeito, segredos JWT, Supabase, segredo de audit ingest, modo aberto, **`SUPABASE_HTTP_TIMEOUT_SECONDS`**, **`SALE_IDEMPOTENCY_TTL_HOURS`**, **`PROTOTYPE_READ_CACHE_TTL_SECONDS`**, **`PROTOTYPE_RATE_LIMIT_*`**, **`API_PROTOTYPE_STRICT_STARTUP`** — documentar em `.env.example` do `web-prototype` e env da raiz para a API/Streamlit conforme uso.
5. **Consumidores externos de `POST /sales/record` ou `POST /sales/submit`:** se esperarem `detail` sempre como **string**, actualizar para aceitar **objecto** (`message` / `code` / `context`) nas respostas de erro da api-prototype; o Streamlit que chama **`sales_service.record_sale`** directamente **não** é afectado. O submit orquestrado exige **`Idempotency-Key`** no cabeçalho.
6. **Idempotência:** linhas têm **`expires_at`**; a API remove periodicamente registos **já expirados** (purge seguro). Ajustar **`SALE_IDEMPOTENCY_TTL_HOURS`** conforme política de negócio (1–168 h na implementação actual).
7. **Cache Next:** leituras via API com sessão **não** usam `unstable_cache` (incompatível com `cookies()`); usar cache só em funções puramente estáticas ou passar dados dinâmicos **para fora** do callback cacheado, conforme a [documentação do Next.js](https://nextjs.org/docs/app/api-reference/functions/unstable_cache).
8. **Paridade Streamlit:** endpoints de custos, vendas e inventário foram desenhados para espelhar fluxos da app Streamlit; divergências futuras exigem actualização bilateral.
9. **UAT no browser:** existe **`tests/e2e/flows.spec.ts`** (login, cliente, páginas de venda/inventário, cadeia curta) quando **`ALIEH_E2E_PASSWORD`** e serviços estão configurados; smoke **`/`** e **`/login`** correm sempre. Detalhe em **`RELATORIO_COMPLETO_TESTES.md`**.
10. **`API_PROTOTYPE_STRICT_STARTUP=1`:** a API **não arranca** se `check_database_health` falhar — útil para ambientes com DSN garantido; em desenvolvimento sem base, omitir ou não definir esta variável.
11. **Índice `idx_sales_tenant_id_desc`:** incluído em `schema.sql` para novas instalações; bases Postgres/SQLite já provisionadas podem precisar de migração manual do `CREATE INDEX` se a listagem de vendas recentes for lenta em volume alto.
12. **`ALIEH_STRICT_QA_ENV=1`:** só para *pipelines* de QA / gate Docker — **não** definir em produção real (exigiria credenciais E2E e `ALIEH_API_TEST_URL` no processo Next). **`ALIEH_ENV=staging`** no Next ou na API implica validação mais rígida (DSN e segredo de sessão no Next; DSN na API em staging).

---

## 8. Resumo executivo

O **protótipo** é um **cliente Next.js** autenticado por sessão, que consome uma **API FastAPI fina** a correr junto ao mesmo repositório, reutilizando **services** e **repositórios** Postgres multi-tenant. As áreas **Painel, Produtos, Custos, Precificação, Estoque, Clientes e Vendas** estão ligadas à API de forma coerente.

**Vendas** combinam: preview no cliente quando o utilizador **actualiza o resumo**; na **conclusão**, um único **`POST /sales/submit`** no servidor (preview interno + `expected_*` + gravação), **idempotência** com **TTL e limpeza**, **bloqueio de linha e update condicional de stock** na mesma transacção, **RBAC**, **auditoria**, **rate limits** e **invalidação do cache de leitura** na API após sucesso.

**Operação:** o **`GET /health`** expõe **`OK` / `DEGRADED` / `FAIL`**, latências e estado da **base de dados** (com timeout na sonda), **`sales_paths`** e sonda mínima de tabelas; **`X-Request-Id`** e **logs JSON** por pedido (com actor/tenant e métricas cumulativas) ajudam a correlacionar incidentes. **Timeouts** em ViaCEP (**8 s** na UI) e Supabase (API) reduzem bloqueios por dependências externas lentas.

**Arranque seguro:** validação por **tier** no Next (`instrumentation.ts` + `alieh-runtime.ts`) e na API (`prototype_env.py`); *gate* Docker com **`ALIEH_QA_GATE`** / **`ALIEH_STRICT_QA_ENV`** / **`ALIEH_STRICT_E2E`** para reduzir regressões «verdes» com testes saltados; ver secção **1.4.1** e **`RELATORIO_QA_READINESS.md`**.

**Performance (sem mudar contratos nem `services/`):** **`React.cache`** nas leituras RSC mais partilhadas, **`Promise.allSettled`** na página de produtos, debounce **~40 ms** na **precificação** (troca de SKU / recomputar preview), pesquisa na grelha de produtos **100 ms**, **sem debounce** artificial no carregamento de lotes em **nova venda** (com cache-first e dedupe global no cliente), dedupe in-flight de **lotes por SKU** (servidor + browser), grelha de inventário com **`React.memo`**, índice **`idx_sales_tenant_id_desc`** para vendas recentes, e reutilização de ligações HTTP documentada no cliente da API.

**Percepção de performance (UI):** caches mais longos no browser (**lotes ~120 s**, **insight precificação ~90 s**), prefetch alargado de SKUs e *cluster* de rotas ao focar **Vendas**, aquecimento de **opções de filtro de inventário** no layout de vendas, **`useOptimistic`** em vendas (submit), precificação (guardar), baixa de inventário e clientes, **`router.prefetch`** com **hover + focus**, e **`SubmitButton`** configurável onde aplicável — ver **`web-prototype/docs/PERCEIVED_PERFORMANCE.md`**.

---

*Fim do relatório.*
