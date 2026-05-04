# Testes API (`tests/api`)

Testes **HTTP ao vivo** contra a `api-prototype` — **não** alteram `services/` nem contratos; apenas validam respostas.

## Pré-requisitos

1. API a correr (ex.: `npm run dev:api` na raiz → `http://127.0.0.1:8000`).
2. Variável de ambiente:

```bash
set ALIEH_API_TEST_URL=http://127.0.0.1:8000
pytest tests/api -v -m live_api
```

(Linux/macOS: `export ALIEH_API_TEST_URL=...`)

## Base de dados

Os testes **live_api** chamam rotas reais. Use **Postgres de desenvolvimento / staging**, nunca produção sem política explícita. Os testes aqui **não** executam fluxos de venda completos que persistam dados (excepto o que a API já faria com IDs inválidos — preferir tenant descartável).

## Marcador pytest

Todos os ficheiros nesta pasta usam `@pytest.mark.live_api`. Na raiz:

```bash
npm run test:api
```

equivale a `pytest tests/api -v --tb=short -m live_api`.
