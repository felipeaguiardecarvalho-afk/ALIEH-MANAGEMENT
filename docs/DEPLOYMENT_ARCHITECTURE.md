# Arquitectura de deploy — ALIEH (Next + FastAPI + Postgres)

## Visão geral

| Camada | Função | Exposição recomendada |
|--------|--------|------------------------|
| **web-prototype** (Next.js) | UI pública, autenticação (cookie httpOnly), chamadas server-side à API | **Internet** (HTTPS, WAF opcional) |
| **api-prototype** (FastAPI) | Orquestra `services/` e `database/` existentes | **Apenas rede interna** ou gateway com políticas estritas |
| **PostgreSQL** | Dados de negócio | **Privado** — sem acesso directo da Internet |

## Fluxo de confiança

1. O browser fala só com o **Next**.
2. O Next chama a **API** com cabeçalhos de actor (`X-User-Id`, `X-Tenant-Id`, `X-Role`) derivados da sessão.
3. A API **não** deve ser exposta como API pública genérica: trate-a como **backend interno**.

## Endurecimento opcional (operacional)

- **`API_PROTOTYPE_INTERNAL_SECRET`**: se definido na API e no Next (`web-prototype`), o Next envia `X-Alieh-Internal`; a API rejeita pedidos sem o segredo (excepto `/health`, documentação OpenAPI e `/metrics` conforme middleware).
- **`API_PROTOTYPE_TRUSTED_ORIGINS`**: lista separada por vírgulas; se o pedido trouxer `Origin` / `Referer` de browser, deve coincidir (pedidos sem `Origin`, típicos de `fetch` server-side, continuam permitidos).
- **`ALIEH_METRICS_SCRAPE_TOKEN`**: em `ALIEH_ENV=production`, `GET /metrics` só responde com `?token=…` correcto.

## Ambientes

| Tier | Variável | Notas |
|------|-----------|--------|
| Desenvolvimento | `ALIEH_ENV=development` ou omitido | `ALIEH_PROTOTYPE_OPEN=1` permitido (não use em produção). |
| Staging | `ALIEH_ENV=staging` ou `VERCEL_ENV=preview` | Paridade com prod; sem dados reais. |
| Produção | `ALIEH_ENV=production` ou `VERCEL_ENV=production` | Validação estrita no Next (`instrumentation.ts`) e na API (`prototype_env`). |

## Health

- API: `GET /health` — deve responder `OK` ou `DEGRADED` antes de receber tráfego de utilizador (load balancers / orchestrators).
- Next: depende da plataforma (ex.: rota sintética ou verificação de processo).

## Streamlit (já em produção) + protótipo Next em paralelo — sem se atrapalharem

**Estratégia adoptada pela equipa: Plano C (Opção C)** — mesmo **projecto Supabase** e mesmo **`tenant_id`** (normalmente `default`): **uma única fonte de verdade**; o Next é um segundo front-end sobre os mesmos dados que o Streamlit já usa em Postgres.

O Streamlit e o Next são **processos e origens HTTP diferentes**: não há conflito de cookies, de porta local na Cloud, nem de “derrubar” um ao fazer deploy do outro, **desde que** a camada de **dados** e **secrets** estejam planeadas.

### 1. O que já fica isolado por natureza

| Aspecto | Streamlit | Next + `api-prototype` |
|--------|-----------|-------------------------|
| Hospedagem | Streamlit Community Cloud / VM / Docker | Vercel (Next) + API noutro host (Railway, Fly, VM, etc.) |
| Sessão | `st.session_state` + cookies do domínio Streamlit | JWT em cookie `httpOnly` no **teu** domínio |
| Deploy | Botão “Reboot” / push no repo da app Streamlit | Deploy do `web-prototype` + API independente |

Ou seja: **subir o Next em produção não altera o binário nem os secrets do Streamlit**, a menos que edites manualmente o mesmo segredo ou a mesma base de forma destrutiva.

### 2. Onde pode haver “interferência” (e como evitar)

**Conflito real = duas aplicações a escrever na mesma base / mesmo inquilino sem regra clara.**

- **Mesmo projecto Supabase + mesmo `tenant_id` (ex.: `default`)** nas duas apps: os dados são **partilhados**. Uma venda criada no Next aparece no Streamlit e vice‑versa. Isto pode ser desejável (única fonte de verdade) ou indesejável se quiseres **piloto isolado**.
- Para **piloto isolado** sem desligar o Streamlit, escolhe **uma** destas linhas:

**Opção A — Novo projecto Supabase só para o stack Next (máximo isolamento)**  
- Streamlit mantém o `DATABASE_URL` / secrets actuais **inalterados**.  
- Next + API usam um **segundo** DSN (novo projecto). Corres `schema_apply` e seeds só lá.  
- Não há cruzamento de linhas de negócio até fazeres migração/cutover explícito.

**Opção B — Mesmo projecto Supabase, tenant dedicado só para o Next**  
- Streamlit continua a operar no tenant que já usas (normalmente `default`).  
- Em **produção** do Next + API define **`ALIEH_TENANT_ID`** (e cabeçalho `X-Tenant-Id` coerente) para um valor **novo e exclusivo** (ex.: `next_prod`), e cria utilizadores **só** nesse tenant para login no Next.  
- O Streamlit não “vê” esses dados se só trabalhares no tenant antigo. **Requisito:** todas as rotas da API e o Next respeitam sempre o tenant (o código já está orientado a isso); não uses `ALIEH_PROTOTYPE_OPEN` em prod para contornar regras.

**Opção C — Mesmo projecto e mesmo tenant**  
- Não há isolamento de **dados**; só há isolamento de **UI**. Adequado quando o Next é apenas um novo front-end da mesma operação.

### 3. Boas práticas que protegem o Streamlit

- **Não** correr `database.schema_apply --full-reset` (ou equivalente destrutivo) na base que o Streamlit usa em produção.  
- **Não** reutilizar o secret `ALIEH_CI_DATABASE_URL` de CI como BD do Streamlit em produção.  
- DDL/migrations: testar em QA; em prod aplicar só migrações **incrementais** e reversíveis quando partilharem BD.  
- Opcional mas recomendado: **`API_PROTOTYPE_INTERNAL_SECRET`** na API + Next para a API não aceitar tráfego arbitrário da Internet.

### 4. Checklist rápido “GO paralelo”

- [ ] Domínio / URL do Next + URL da API definidos; Streamlit continua no URL actual.  
- [ ] **Plano C:** `DATABASE_URL` (e tenant efectivo) **iguais** entre Streamlit, Next e `api-prototype` em produção — ver secção seguinte.  
- [ ] `ALIEH_ENV=production`, `ALIEH_PROTOTYPE_OPEN=0`, `AUTH_SESSION_SECRET` forte só no stack Next.  
- [ ] `GET /health` da API OK antes de tráfego.

### 5. Plano C — guia de implementação (detalhe)

#### 5.1 Pré-requisito: uma só base de negócio

- Streamlit e Next devem apontar para o **mesmo DSN Postgres** (mesmo projecto Supabase) e o **mesmo `tenant_id`** em todas as escritas (por defeito **`default`** — alinhado a `database/tenancy.py` e ao login Next).
- Se o Streamlit em produção ainda estiver **apenas em SQLite** (`business.db` na Cloud), os dados **não** coincidem com o Postgres do Next: ou migras o Streamlit para o **mesmo** `DATABASE_URL` que o Next, ou aceitas uma **fase** em que só o Next está em Postgres até alinhares o Streamlit.

#### 5.2 Variáveis por camada (produção)

| Camada | O que alinhar |
|--------|----------------|
| **Streamlit Cloud** | Mantém os segredos actuais. Com Plano C, o **`DATABASE_URL`** (ou `supabase_db_url` / cadeia em `database.config`) é a **fonte** que o Next também deve usar — **não** trocar o DSN do Streamlit ao publicar o Next; copias o **mesmo** valor para Vercel/API. |
| **Next (`web-prototype`)** | `DATABASE_URL` = cópia exacta da URI Postgres do Streamlit. `ALIEH_TENANT_ID=default` (ou omitir se o utilizador na BD já for `default`). `ALIEH_ENV=production`, `ALIEH_PROTOTYPE_OPEN=0`, `AUTH_SESSION_SECRET` (≥ 32 chars). `API_PROTOTYPE_URL` = URL interna ou estável da API. Chaves `SUPABASE_*` / `NEXT_PUBLIC_SUPABASE_*` do **mesmo** projecto. |
| **`api-prototype`** | O mesmo `DATABASE_URL`. `ALIEH_ENV=production`. Pedidos autenticados levam `X-Tenant-Id` coerente com a sessão (em Plano C, `default` após login). |

#### 5.3 Utilizadores

- Tabela `users` (e PBKDF2 como em `utils/password_hash.py`) é **partilhada**: credenciais válidas numa app funcionam na outra **no mesmo tenant**. Sessões continuam **independentes** (Streamlit vs cookie JWT no domínio do Next).

#### 5.4 Schema e migrações

- Aplicar só **`database.schema_apply` idempotente** (sem `--full-reset`) em produção. Qualquer migração afecta **Streamlit e Next** ao mesmo tempo — validar em QA primeiro.

#### 5.5 Concorrência

- Dois operadores em UIs diferentes sobre o mesmo registo comportam-se como em qualquer sistema multi-cliente; não é falha de deploy, é regra de negócio e transacções na BD.

#### 5.6 CI / QA

- **Não** usar o DSN de produção nos testes destrutivos. Manter **`ALIEH_CI_DATABASE_URL`** (ou equivalente) num **Supabase só de CI/QA**, como em `docs/DATA_SAFETY.md`. O Plano C aplica-se ao **par** produção Streamlit+Next, não ao pipeline de testes.

---

## Referências no repositório

- **Vercel + Render (URLs, envs):** `docs/DEPLOYMENT_VERCEL_RENDER.md`
- Workflow CI: `.github/workflows/production-readiness.yml`
- Checklist manual: `docs/PRODUCTION_READINESS_CHECKLIST.md`
- Dados e testes: `docs/DATA_SAFETY.md`
