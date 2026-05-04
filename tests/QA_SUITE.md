# Suite de QA (ALIEH)

## Comandos (raiz do repositório)

| Comando | Descrição |
|---------|-----------|
| `npm run test:unit` | Pytest em `tests/` exceto `tests/api` (regressão Python existente). |
| `npm run test:api` | Testes HTTP `tests/api` com marcador `live_api` (requer `ALIEH_API_TEST_URL`). |
| `npm run test:qa` | `test:unit` + `test:api`. |
| `npm run test:e2e` | Playwright em `tests/e2e` (`playwright.config.ts` na mesma pasta). Primeira vez: `cd tests/e2e && npm install && npx playwright install chromium`. Next na **3000** (`npm run dev` na raiz). |
| `npm run test:qa:full` | `test:qa` + `test:e2e`. |
| `npm run test:qa:full:docker` | *Gate*: **`DATABASE_URL`** (Supabase); schema/seed no host; Docker **`qa-api`** + **`qa-web`**; pytest + E2E. Ver `scripts/qa/README.md`. |

### Variável para API ao vivo

```powershell
$env:ALIEH_API_TEST_URL="http://127.0.0.1:8000"
npm run test:api
```

A URL tem de ser a **api-prototype** (resposta `/health` com `sales_paths` e `dependencies`). Outros serviços na mesma porta fazem os testes **saltarem** de propósito.

## Estrutura

- `tests/api/` — smoke + RBAC + contratos leves (sem mutar negócio sem ambiente descartável).
- `tests/e2e/` — Playwright; expandir para UAT (vendas, clientes, …).
- `tests/factories/` — headers e payloads mínimos reutilizáveis.

## Relatório gerado

Após uma corrida completa com API + Next, actualizar `Relatórios/RELATORIO_QA_READINESS.md` (ou script futuro `scripts/qa_report.py`). Inventário técnico: `Relatórios/RELATORIO_COMPLETO_TESTES.md`.
