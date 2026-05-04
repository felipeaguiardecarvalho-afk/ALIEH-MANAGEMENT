# Relatório de prontidão QA — ALIEH (protótipo Next + API)

**Data da corrida documentada:** 2026-05-04  
**Âmbito:** regressão Python, testes HTTP `live_api`, integração Postgres, E2E Playwright, *gate* Docker opcional.  
**Detalhe alargado:** ver **`RELATORIO_COMPLETO_TESTES.md`** (inventário ficheiro a ficheiro e matriz de lacunas).

---

## 1. Resumo (execuções de referência)

### 1.1 Máquina de desenvolvimento — só `pytest` (sem Postgres de integração)

| Categoria | Total | Passou | Falhou | Saltou |
|-----------|-------|--------|--------|--------|
| **Regressão Python** (`npm run test:unit` → `pytest tests`, exceto `tests/api`) | 73 | **72** | **0** | **1**† |
| **API live** (`npm run test:api`) | 7 | — | — | **7**\* |
| **E2E Playwright** (`npm run test:e2e`) | 7 | **2**‡ | **0** | **5**‡ |
| **Integração Postgres** (`npm run test:pg`) | 1 | — | — | **1**† |

† `tests/test_postgres_integration.py` — requer `ALIEH_PG_INTEGRATION=1` e `DATABASE_URL` para uma base com **`schema.sql`** aplicado (nunca produção).

\* Sem **`ALIEH_API_TEST_URL`** a apontar para uma **api-prototype** real, os testes marcados **`live_api`** saltam de propósito.

‡ **`smoke.spec.ts`** (`/` e `/login`) passam com Next na **3000**. **`flows.spec.ts`** (login, cliente, venda, inventário, UAT) exige **`ALIEH_E2E_USERNAME`** / **`ALIEH_E2E_PASSWORD`** (no CI alinhados ao seed: utilizador **`e2e_ci`**, password **`E2E_ci_change_me_!`**) e stack (Next + API + BD).

**Comando registado (raiz):**

```text
pytest tests --ignore=tests/api -q  →  72 passed, 1 skipped (~13 s)
```

*(Os restantes comandos `test:api` / `test:e2e` / `test:pg` sem env completo reproduzem os skips da tabela.)*

### 1.2 *Gate* completo — `npm run test:qa:full:docker`

Orquestração em **`scripts/qa/gate-runner.mjs`**:

1. **`DATABASE_URL`** no ambiente (Supabase — hostname com `supabase`, salvo `ALIEH_ALLOW_NON_SUPABASE_DB=1`).
2. No host: **`python -m database.schema_apply`** (sem `--full-reset`) e **`scripts/ci/seed_e2e_user.py`**.
3. `docker compose -f docker-compose.qa.yml --profile gate` — contentores **`qa-api`** (**36101**) e **`qa-web`** (**3000**; `API_PROTOTYPE_URL=http://qa-api:8000`). **Sem** Postgres em Docker.
4. `pytest tests` (exceto `tests/api`) com **`ALIEH_PG_INTEGRATION=1`** e o mesmo `DATABASE_URL`.
5. `pytest tests/api -m live_api` com **`ALIEH_API_TEST_URL=http://127.0.0.1:36101`**.
6. `npm run test:e2e` com `PLAYWRIGHT_BASE_URL` e credenciais E2E (Next servido pelo contentor **qa-web**).

**Alvo:** **0 falhas**, **0 skips** em pytest + API live + E2E.

**Requisitos:** Docker Desktop a correr; portas **36101** (API) e **3000** (Next) livres no anfitrião.

**Documentação:** **`scripts/qa/README.md`**.

---

## 2. Por categoria

### Smoke / regressão (Python)

- Cobre auditoria, backup, vendas concorrentes, config de BD, RBAC Python, export SQLite, stock manual, sondas Postgres, etc.
- **72 passed** confirma estabilidade da regressão **sem** dependência de API ao vivo na mesma corrida.

### API ao vivo

- Smoke `/health`, RBAC em cabeçalhos, contrato `Idempotency-Key` em `/sales/submit`, forma mínima de `/dashboard/panel`.
- **Requer:** `ALIEH_API_TEST_URL` apontando para **uvicorn** com **`api-prototype`** (validação do formato de `GET /health`). No *gate* Docker usa-se automaticamente **`http://127.0.0.1:36101`**.

### E2E

- **`smoke.spec.ts`:** rotas públicas — passam com Next no ar.
- **`flows.spec.ts`:** fluxos autenticados — precisam de credenciais e dados de seed; o *gate* Docker define **`ALIEH_E2E_USERNAME`** / **`ALIEH_E2E_PASSWORD`** coerentes com **`scripts/ci/seed_e2e_user.py`**.

### CI remoto

- **`.github/workflows/production-readiness.yml`:** secret **`ALIEH_CI_DATABASE_URL`** (Supabase) exportado como `DATABASE_URL`; **sem** serviço Postgres local; `ALIEH_PG_INTEGRATION=1`, `ALIEH_API_TEST_URL`, `ALIEH_PROTOTYPE_OPEN=0`, **`ALIEH_E2E_*`** alinhadas ao seed (**`E2E_ci_change_me_!`**).

---

## 3. Issues críticos (bloqueio produção)

| ID | Descrição | Estado |
|----|-----------|--------|
| C1 | **Produção** não deve partilhar BD com testes destrutivos / integração | Operacional |
| C2 | Veredicto **GO** de UAT exige corrida **sem skips** (`test:qa:full:docker` ou CI verde com PG + API + E2E) | Depende de execução |
| C3 | **`npm run test:qa:full:docker`** sem Docker, sem `DATABASE_URL`, ou portas bloqueadas → *gate* não corre | Mitigar: Docker activo; `DATABASE_URL` Supabase; portas 36101/3000 |
| C4 | Arranque em **produção** sem **`ALIEH_PROTOTYPE_OPEN=0`** (e API sem DSN quando aplicável) → **fail-fast** (Next + `prototype_env.py`; API também com **`NODE_ENV=production`**) | Comportamento intencional |

---

## 4. Avisos (não bloqueantes)

- `npm run test:api` sem URL → **7 skipped** (esperado em dev isolado).
- `flows.spec.ts` sem **`ALIEH_E2E_PASSWORD`** → **5 skipped** (esperado).
- Primeira vez Playwright: `cd tests/e2e && npm install && npx playwright install chromium`.
- `npm run test:qa` = unit + API; `npm run test:qa:full` = `test:qa` + E2E; `npm run test:gate` inclui `test:pg` e E2E manualmente na mesma ordem do `package.json`.

---

## 5. Veredicto GO / NO-GO

**NO-GO** para “**produção** validada **só** por `pytest` local sem PG/API/E2E” — continuam skips nas categorias dependentes de ambiente.

**NO-GO** para “**produção**” até existir **pelo menos uma** corrida comprovada com **0 skips** no pacote alvo (CI **`production-readiness`** e/ou **`npm run test:qa:full:docker`** com sucesso).

**GO condicional** para “**merge / desenvolvimento** com regressão Python verde” — **72 passed** na última corrida documentada.

**GO condicional** para “**smoke browser** com Next no ar” — smoke E2E quando a UI responde.

---

## 6. Próximos passos sugeridos

1. Manter **`production-readiness`** verde no GitHub.
2. Localmente: exportar **`DATABASE_URL`** (Supabase de QA); `npm run test:qa:full:docker` com Docker Desktop iniciado.
3. Opcional: `pytest --junitxml` + agregação de relatórios.

---

## 7. Execução E2E (referência)

- Config: **`tests/e2e/playwright.config.ts`**; dependências **`tests/e2e/package.json`**.
- Pré-requisito: Next na **3000** (ou `PLAYWRIGHT_BASE_URL`).

```powershell
cd tests/e2e
npm install
npx playwright install chromium
cd ../..
npm --prefix web-prototype run dev   # se necessário
$env:ALIEH_E2E_USERNAME = "e2e_ci"
$env:ALIEH_E2E_PASSWORD = "E2E_ci_change_me_!"
npm run test:e2e
```

*Gate* completo (com Docker):

```powershell
cd "C:\Users\felip\Documents\ALIEH management"
npm run test:qa:full:docker
```

---

*Fim do relatório.*
