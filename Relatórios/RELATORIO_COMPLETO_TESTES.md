# Relatório completo e detalhado de testes — ALIEH

**Âmbito:** automação de testes no repositório **ALIEH management** — motor Python (`services/`, `database/`), **api-prototype** (FastAPI), **web-prototype** (Next.js), e pacotes de apoio (`tests/`, `tests/api/`, `tests/e2e/`, `tests/factories/`).  
**Data de referência:** 2026-05-03.  
**Tipo de documento:** inventário técnico, comandos, mapeamento a riscos/segurança/UAT e **lacunas**; complementa **`RELATORIO_QA_READINESS.md`** (veredicto GO/NO-GO curto) e **`RELATORIO_SEGURANCA_COMPLETO.md`** (controlos de segurança).

---

## 1. Resumo executivo

| Camada | Ferramenta | Localização | Execução típica | Notas |
|--------|------------|-------------|-----------------|--------|
| Regressão / unitário Python | pytest | `tests/test_*.py` (excl. `tests/api`) | `npm run test:unit` | **Não** exige API nem Next; usa mocks/SQLite conforme teste. |
| Integração Postgres | pytest | `tests/test_postgres_integration.py` | Opt-in: `ALIEH_PG_INTEGRATION=1` + `DATABASE_URL` | Salta por defeito; exige base com schema aplicado. |
| API ao vivo (smoke + contratos) | pytest + `urllib` | `tests/api/` | `npm run test:api` com `ALIEH_API_TEST_URL` | Marcador **`live_api`**; valida *fingerprint* da **api-prototype** via `GET /health`. |
| E2E browser | Playwright | `tests/e2e/*.spec.ts` | `npm run test:e2e` | Pacote Node em **`tests/e2e/package.json`**; config **`tests/e2e/playwright.config.ts`**. |

**Última execução registada (2026-05-03):**

| Comando | Resultado |
|---------|-----------|
| `npm run test:unit` | **72 passed**, **1 skipped** (`test_postgres_integration` sem `ALIEH_PG_INTEGRATION=1` + `DATABASE_URL`), **73** recolhidos, ~13.4 s |
| `npm run test:api` | **7 skipped** (`ALIEH_API_TEST_URL` ausente ou `/health` sem *fingerprint* da api-prototype), ~0.1 s |
| `npm run test:e2e` | **2 passed**, **5 skipped** (`flows.spec.ts` sem `ALIEH_E2E_PASSWORD`); **7** testes no total, ~3.8 s |
| `npm run test:pg` | **1 skipped** (mesmo motivo que o skip na regressão), ~0.6 s |

Com **`ALIEH_API_TEST_URL`** apontando para a **api-prototype** real, esperam-se **7 passed** nos testes `live_api`.

**Regra de isolamento:** testes que **gravam** dados reais de negócio devem usar **base descartável** ou flags documentadas (`ALIEH_PG_INTEGRATION`); **nunca** apontar suites destrutivas à base de produção.

---

## 2. Comandos consolidados (raiz do repositório)

```bash
npm run test:unit      # pytest tests --ignore=tests/api
npm run test:api       # pytest tests/api -m live_api
npm run test:pg        # só tests/test_postgres_integration.py (exige ALIEH_PG_INTEGRATION=1 + DATABASE_URL)
npm run test:qa        # unit + api
npm run test:e2e       # npm --prefix tests/e2e run test
npm run test:qa:full   # test:qa && test:e2e
npm run test:gate      # unit + api + pg + e2e (exige ambiente completo)
```

**Variáveis de ambiente relevantes**

| Variável | Uso |
|----------|-----|
| `ALIEH_API_TEST_URL` | URL base da FastAPI (ex. `http://127.0.0.1:8000`). Sem valor, vários testes `live_api` saltam no primeiro passo. |
| `ALIEH_PG_INTEGRATION` | Definir `1` para activar integração Postgres em `test_postgres_integration.py`. |
| `DATABASE_URL` | DSN para integração Postgres e parte da lógica de configuração testada. |
| `ALIEH_E2E_PASSWORD` / `ALIEH_CI_E2E_PASSWORD` | Credencial para **`flows.spec.ts`** (login e fluxos pós-login). |
| `ALIEH_E2E_USERNAME` / `ALIEH_CI_E2E_USERNAME` | Utilizador de teste (padrão CI: `e2e_ci`). |
| `PLAYWRIGHT_BASE_URL` | Opcional; sobrescreve `baseURL` do Playwright (default `http://127.0.0.1:3000`). |

**Primeira configuração E2E**

```bash
cd tests/e2e
npm install
npx playwright install chromium
```

Índice breve: **`tests/QA_SUITE.md`**.

---

## 3. Configuração pytest (`pytest.ini`)

- **`testpaths`:** `tests`
- **Marcadores declarados:**
  - **`live_api`** — requer processo HTTP e `ALIEH_API_TEST_URL`
  - **`integration`** — Postgres / `ALIEH_PG_INTEGRATION`
  - **`e2e`** — documentação; execução E2E via npm

---

## 4. Regressão Python (`tests/test_*.py`, excluindo `tests/api`)

Estes ficheiros **não** alteram a API nem o Next; validam módulos do monorepo (config, RBAC em funções Python, concorrência simulada, export SQLite, etc.).

| Ficheiro | Foco principal |
|----------|----------------|
| `test_audit_robustness.py` | Cadeia de auditoria, detecção de adulteração, backups periódicos, SQLite full backup. |
| `test_backup_recovery.py` | Restauro após perda de dados, validação de export JSON, integridade. |
| `test_concurrent_sales.py` | Vendas concorrentes, *oversubscribe*, stress — alinhado a **stock** e **race** no motor (não substitui teste de carga em produção). |
| `test_database_config.py` | Selecção de provider (SQLite/Postgres), DSN, variáveis `DATABASE_URL` / Supabase, timeouts e erros de ligação. |
| `test_database_health.py` | `check_database_health`, periodicidade, arranque. |
| `test_manual_stock_write_down.py` | Baixa manual de stock, validação de quantidade, custo, depleção total. |
| `test_postgres_integration.py` | Round-trip produto/cliente/venda em Postgres (**skipped** sem `ALIEH_PG_INTEGRATION`). |
| `test_postgres_probe.py` | Sondas de ligação, logging, threads de *probe*. |
| `test_rbac.py` | Funções `require_role`, `require_admin`, `is_admin`, etc., no **código Python** partilhado (paridade conceptual com RBAC HTTP, mas camada diferente da API FastAPI). |
| `test_sql_compat.py` | Adaptação de SQL entre providers. |
| `test_sqlite_export.py` | Export JSON/CSV/manifest; exige provider SQLite onde aplicável. |

**Observação:** o RBAC em **`test_rbac.py`** valida *gates* Python usados por fluxos legacy (ex. Streamlit); o RBAC **`tests/api/test_rbac_live_api.py`** valida **`deps.py`** e cabeçalhos **`X-Role`** na API protótipo. Ambos são complementares.

---

## 5. API ao vivo (`tests/api/`)

### 5.1 Infraestrutura (`tests/api/conftest.py` + `tests/conftest.py`)

- **`tests/conftest.py`:** em **`CI=true`**, testes com marcador **`live_api`** **falham** se `ALIEH_API_TEST_URL` estiver vazio (evita merges com 7 skips). Desactivar com `ALIEH_REQUIRE_API_URL_IN_CI=0` se necessário.
- **`api_http_get` / `api_http_post_json`:** cliente HTTP mínimo via `urllib`; erros HTTP devolvem `(status, body)` sem excepção não tratada.
- **`is_alieh_prototype_health_payload(body)`:** exige chaves **`sales_paths`** e **`dependencies`** no JSON de `/health` — discrimina **api-prototype ALIEH** de outros serviços na mesma porta.
- Respostas 200 com corpo não-JSON devolvem `{"_non_json": "..."}` truncado para diagnóstico.

### 5.2 `test_smoke_live_api.py` (marcador `live_api`)

| Teste | Comportamento esperado |
|-------|-------------------------|
| `test_health_returns_json_with_status` | `GET /health` → 200; se *fingerprint* ALIEH: `status` ∈ {OK, DEGRADED, FAIL}, `prototype === true`, `sales_paths` lista. |
| `test_health_includes_database_block` | `dependencies.database` e `dependencies.core_tables` presentes quando *fingerprint* válido. |

### 5.3 `test_rbac_live_api.py`

| Teste | Comportamento esperado |
|-------|-------------------------|
| `test_saleable_skus_viewer_can_read` | `GET /sales/saleable-skus` com `actor_headers(role="viewer")` → 200 e `items`; **404** → skip (URL errada). |
| `test_saleable_skus_missing_user_id_rejected` | Sem `X-User-Id` → **400** ou **422**. |
| `test_preview_sale_viewer_forbidden` | `POST /sales/preview` com `viewer` → **403** (mutação reservada a admin/operator). |

**Factory:** `tests/factories/headers.py` — `actor_headers(role=..., user_id=..., tenant_id=...)`.

### 5.4 `test_sales_contract_live_api.py`

| Teste | Comportamento esperado |
|-------|-------------------------|
| `test_submit_without_idempotency_key_rejected` | `POST /sales/submit` **sem** cabeçalho `Idempotency-Key`, corpo `minimal_preview_body()`, actor admin → **400**; `detail` menciona idempotência (variações de texto aceites). |

**Factory:** `tests/factories/sale_payloads.py` — `minimal_preview_body()` (IDs placeholder 1/1 — suficiente para rejeição por cabeçalho antes de efeitos de negócio).

### 5.5 `test_dashboard_live_api.py`

| Teste | Comportamento esperado |
|-------|-------------------------|
| `test_dashboard_panel_has_core_keys` | `GET /dashboard/panel?date_start=...&date_end=...` com actor admin → 200; chaves `kpis`, `low_stock`, `inventory_summary`, `insights`, `daily`, `date_start`, `date_end`; subcampos mínimos em `inventory_summary`. |

---

## 6. E2E Playwright (`tests/e2e/`)

| Ficheiro | Cenários |
|----------|----------|
| `smoke.spec.ts` | (1) `GET /` — resposta OK ou redirect 302/307, `body` visível; (2) `GET /login` — `body` visível. |
| `flows.spec.ts` | Login com redirect ao painel; criar cliente (nome); nova venda (carga de página); inventário (heading); cadeia UAT painel → clientes → nova venda — **saltam** sem `ALIEH_E2E_PASSWORD` (ou `ALIEH_CI_E2E_PASSWORD`). |

**Configuração:** `playwright.config.ts` — `testDir: "."`, project Chromium, relatório HTML em `tests/e2e/playwright-report/`.

**CI:** workflow **`.github/workflows/production-readiness.yml`** — Postgres de serviço, `schema.sql`, seed **`scripts/ci/seed_e2e_user.py`**, API + Next em background, depois pytest + Playwright com env injectada.

**Motivo do pacote isolado:** evitar conflito de duas instâncias de `@playwright/test` (histórico: config em `web-prototype/` + specs na raiz). O **`web-prototype/package.json`** delega `test:e2e` para `tests/e2e`.

---

## 7. Mapeamento: requisitos de QA vs estado

| Requisito (pedido típico de SDET) | Onde está coberto hoje | Lacuna |
|-----------------------------------|------------------------|--------|
| Smoke API (health, BD) | `test_smoke_live_api.py` | Latência abaixo de 500 ms não medida automaticamente. |
| RBAC (admin/operator/viewer) | `test_rbac_live_api.py` (API); `test_rbac.py` (Python) | Matriz completa por **rota** e por **tenant** não automatizada. |
| Idempotência submit | `test_sales_contract_live_api.py` (ausência de chave) | Retry com **mesma** chave e corpo idêntico → uma venda (requer dados descartáveis + teste dedicado). |
| Concorrência / oversell | `test_concurrent_sales.py` | Contra API HTTP simultânea e E2E multi-browser: não. |
| UAT cliente / inventário / venda E2E | `flows.spec.ts` (com credencial) | Subconjunto coberto quando env + serviços no ar; venda end-to-end completa ainda limitada ao smoke de página. |
| **Camada global Next (Zustand / `ClientDataProvider`)** | — | **Sem** testes automáticos dedicados; validar com `npm run build` em `web-prototype` e smoke manual (navegação + Nova venda). |
| API “todas as rotas” | Parcial (`/health`, `/sales/*`, `/dashboard/panel`) | Custos, produtos, pricing, inventory mutações, storage, audit, UAT API. |
| Auth sessão (login/logout) E2E | — | Precisa credenciais de teste e política de secrets em CI. |
| Performance | — | Adicionar thresholds (pytest ou k6) em ambiente controlado. |
| Erro API *down* na UI | — | Playwright com mock ou paragem controlada do servidor. |

---

## 8. Integridade de dados e arredondamento

- **Stock não negativo / updates condicionais:** coberto indirectamente por **`test_concurrent_sales.py`** e **`test_manual_stock_write_down.py`** ao nível do motor Python.
- **Arredondamento monetário na API:** não há assert numérico dedicado nos testes `tests/api/`; a paridade preview/record está descrita em **`RELATORIO_PROTOTIPO_SITUACAO_ATUAL.md`** (comportamento de produto).

---

## 9. Relatórios e decisão de release

| Documento | Função |
|-----------|--------|
| **`RELATORIO_QA_READINESS.md`** | Resumo de corrida, issues críticos/avisos, **GO/NO-GO** da suite de prontidão. |
| **`RELATORIO_SEGURANCA_COMPLETO.md`** | Riscos, trust boundaries, RBAC, idempotência, logs — secção **19** liga controlos a testes automatizados. |
| **`RELATORIO_PROTOTIPO_SITUACAO_ATUAL.md`** | Arquitectura, endpoints, UX; secção **5.1** com comandos npm de QA. |
| **Este ficheiro** | Inventário detalhado e matriz de lacunas para roadmap de testes. |

**Veredicto global (síntese):** **regressão Python + API live + E2E** (smoke + **`flows.spec.ts`** quando há credencial) é **necessária mas não suficiente** para “UAT completo” ou “todas as rotas sem risco”. Ver **`RELATORIO_QA_READINESS.md`** para o veredicto formal da iteração actual.

---

## 10. Próximos passos recomendados (roadmap de testes)

1. **CI:** workflow **`production-readiness`** na raiz (API + Postgres + Next + pytest + Playwright); localmente manter `npm run test:unit` sempre.
2. **Dados descartáveis:** *fixtures* Postgres ou tenant `qa-*` para `POST /sales/submit` com idempotência real e verificação de stock.
3. **Playwright:** fluxos autenticados (login → nova venda → verificar lista) com vídeo/trace em falha.
4. **Cross-tenant:** dois pares de cabeçalhos; garantir que `tenant_id` A não vê dados de B nos endpoints de leitura críticos.
5. **Relatório JUnit:** `pytest --junitxml=...` e `playwright` reporter junit para dashboards.

---

## 11. Registo de execução (sessão 2026-05-03)

| Suite | Ferramenta | Resultado |
|-------|------------|-----------|
| Regressão | pytest `tests/` (exc. `tests/api`) | 72 passed, 1 skipped |
| API live | pytest `-m live_api` | 7 skipped (env) |
| E2E | Playwright `tests/e2e` | 2 passed, 5 skipped (`flows.spec.ts`) |
| Postgres | `npm run test:pg` | 1 skipped (env) |

Nestas corridas **não houve falhas** (`failed = 0`).

---

*Fim do relatório completo de testes.*
