# QA gate local (Docker: API + Next, BD = Supabase)

## Passo 1 — definir `DATABASE_URL` (Supabase = mesmo projecto que o Streamlit)

1. No **Supabase**: [Dashboard](https://supabase.com/dashboard) → o **mesmo** projecto que o Streamlit usa → **Project Settings** (ícone de roda) → **Database**.
2. Em **Connection string**, escolha **URI** (formato `postgresql://...`).
   - Para **`python -m database.schema_apply`** (DDL completo), prefira a ligação **directa** na porta **5432** (`db.<project-ref>.supabase.co`), se o *pooler* **6543** der erro em `CREATE …`.
3. Copie a string (inclui palavra-passe; **não** a partilhe nem faça commit).

### Windows (PowerShell) — só nesta janela

```powershell
cd "C:\Users\felip\Documents\ALIEH management"
$env:DATABASE_URL = "postgresql://postgres.<...>:<PASSWORD>@db.<ref>.supabase.co:5432/postgres"
# Confirme (mostra só o host, não a password completa):
([uri]($env:DATABASE_URL -replace '^postgresql','http')).Host
```

### Persistir na raiz do repo (recomendado para `npm run` repetidos)

1. Na raiz do repo, crie ou edite o ficheiro **`.env`** (já está no `.gitignore`).
2. Adicione uma linha (sem aspas à volta do URL, salvo se a password tiver espaços):

```env
DATABASE_URL=postgresql://postgres.xxx:PASSWORD@db.xxx.supabase.co:5432/postgres
```

3. O **`gate-runner`** lê **`DATABASE_URL`** do **`.env` na raiz** se a variável **não** estiver já definida no ambiente. Com a linha `DATABASE_URL=...` no `.env`, pode correr `npm run test:qa:full:docker` sem exportar na PowerShell.

   Se definir `$env:DATABASE_URL` na sessão, esse valor **prevalece** sobre o `.env`.

---

## `npm run test:qa:full:docker`

1. Garanta **`DATABASE_URL`** (Supabase, mesmo projecto que o Streamlit): **`.env` na raiz** ou **`$env:DATABASE_URL`** na PowerShell.
2. No **host**: `python -m database.schema_apply` (idempotente, **sem** `--full-reset`) e `scripts/ci/seed_e2e_user.py`.
3. **Docker** sobe **`qa-api`** (FastAPI em **http://127.0.0.1:36101**) e **`qa-web`** (Next: `npm ci` + `build` + `start` em **http://127.0.0.1:3000**). O Next fala com a API via **`http://qa-api:8000`** na rede Docker.
4. **Pytest** no host (`ALIEH_PG_INTEGRATION=1`, `ALIEH_API_TEST_URL=http://127.0.0.1:36101`).
5. **Playwright** no host contra o Next mapeado na porta 3000.

Não existe serviço Postgres em Docker nem imagem `postgres` para BD — só **Supabase** via `DATABASE_URL`.

### Hostname Supabase

Por defeito o *gate* exige `supabase` no hostname. Para outro Postgres: **`ALIEH_ALLOW_NON_SUPABASE_DB=1`**.

### DDL (`schema.sql`)

Use ligação **directa** (porta **5432**, `db.<ref>.supabase.co`) se o *pooler* **6543** não permitir todo o DDL. O `database.schema_apply` já trata Supabase / grants quando o DSN o indica.

### Credenciais **só para QA**

- E2E: `e2e_ci` / `E2E_ci_change_me_!` (alinhado ao seed e ao CI).

Requisitos: Docker, Python com dependências do repo (`pip install -r requirements.txt` …), Node na máquina (para `npm run test:e2e`).

## GitHub Actions

Secret **`ALIEH_CI_DATABASE_URL`** — ver `.github/workflows/production-readiness.yml`.

## Produção — `ALIEH_PROTOTYPE_OPEN`

Em tier **produção**, Next (`instrumentation.ts`) e API (`prototype_env`) exigem **`ALIEH_PROTOTYPE_OPEN=0`**.
