# E2E Playwright (`tests/e2e`)

Dependências Node desta pasta: `@playwright/test` (ver `package.json`). Configuração partilhada: `web-prototype/playwright.config.ts` (`testDir` aponta para aqui).

## Pré-requisitos

1. Uma vez: `cd tests/e2e && npm install && npx playwright install chromium`
2. Protótipo Next na **3000**: na raiz do repo, `npm run dev` (usa `web-prototype`).
3. Opcional: `PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000` (default no config).

## Executar

Na raiz do monorepo:

```bash
npm run test:e2e
```

Ou a partir de `web-prototype`: `npm run test:e2e` (delega para `tests/e2e`).

## UAT completo

Fluxos de cliente, inventário, venda e precificação exigem dados e credenciais de teste — expandir specs aqui e usar ambiente descartável (nunca produção).
