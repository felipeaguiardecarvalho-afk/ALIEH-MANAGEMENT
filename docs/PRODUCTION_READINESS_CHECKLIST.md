# Checklist final — GO / NO-GO produção

## MUST PASS (automatizado no CI `production-readiness`)

- [ ] Secret **`ALIEH_CI_DATABASE_URL`** (Supabase de CI/QA) configurado no repositório GitHub
- [ ] `pytest tests` (exceto `tests/api`) — regressão unitária contra `DATABASE_URL` (Supabase)
- [ ] `pytest tests/api -m live_api` com `ALIEH_API_TEST_URL` = api-prototype real — **sem skips**
- [ ] Integração Postgres incluída no mesmo run com `ALIEH_PG_INTEGRATION=1` (não usar BD de produção)
- [ ] Playwright (`tests/e2e`) com `ALIEH_E2E_PASSWORD` — smoke + fluxos (`flows.spec.ts`)

Comandos na raiz do repositório:

```bash
npm run test:unit
npm run test:api          # exige ALIEH_API_TEST_URL
npm run test:pg           # exige ALIEH_PG_INTEGRATION=1 e DATABASE_URL
npm run test:e2e          # Next + API no ar; credenciais E2E
npm run test:gate         # cadeia completa (falha localmente sem serviços)
```

## MUST VERIFY (manual / operações)

- [ ] `ALIEH_ENV=production` (ou equivalente Vercel) no Next e na API onde aplicável
- [ ] `ALIEH_PROTOTYPE_OPEN` **não** activo em produção (o Next ignora-o em tier produção, mas remova da config)
- [ ] `AUTH_SESSION_SECRET` ≥ 32 caracteres, exclusivo por ambiente
- [ ] `API_PROTOTYPE_URL` aponta para host **interno** ou gateway, não porta do Next
- [ ] API atrás de VPC / internal load balancer **ou** `API_PROTOTYPE_INTERNAL_SECRET` + gateway
- [ ] Supabase: backups, RLS/políticas e separação projecto **QA** vs **produção**
- [ ] `/health` da API `OK` antes de tráfego
- [ ] Logs JSON sem PII (rever campos custom)

## NO-GO imediato se

- Testes `live_api` a saltar em CI com `ALIEH_REQUIRE_API_URL_IN_CI` activo (padrão)
- E2E sem credenciais em CI
- API exposta publicamente sem camada adicional e sem segredo interno acordado

## GO quando

- Pipeline verde com a matriz acima
- Revisão manual dos itens de verificação concluída
- Plano de rollback e rotação de secrets definidos
