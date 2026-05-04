# Dados e segurança de testes

## Separação de bases

- **Produção**: base dedicada; credenciais só em secret store.
- **Staging / QA**: base isolada (clone sanitizado ou tenant `qa-*`).
- **CI**: Postgres efémero (ver workflow `production-readiness`) com `schema.sql` e utilizador `e2e_ci` descartável.

## Testes destrutivos

- `tests/test_postgres_integration.py` **insere e apaga** dados num `tenant_id` único (`itest_*`). **Nunca** apontar `DATABASE_URL` de produção com `ALIEH_PG_INTEGRATION=1`. Use um **projecto Supabase de QA** ou *branch* dedicada, separado do projecto de produção.
- Testes `live_api` assumem ambiente descartável para mutações futuras; hoje focam smoke e contratos.

## Seed de CI

- `scripts/ci/seed_e2e_user.py` — utilizador para Playwright. Controlado por `ALIEH_CI_E2E_USERNAME`, `ALIEH_CI_E2E_PASSWORD`, `ALIEH_CI_E2E_TENANT`.

## Variáveis críticas

| Variável | Risco se mal configurada |
|----------|---------------------------|
| `DATABASE_URL` | Escrita em base errada |
| `ALIEH_API_TEST_URL` | Testes contra serviço incorrecto |
| `ALIEH_PROTOTYPE_OPEN` | Bypass de auth — **bloqueado em produção** no Next |
