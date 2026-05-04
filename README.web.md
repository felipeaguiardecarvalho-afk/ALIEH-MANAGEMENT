# ALIEH Management — Next.js UI

Premium, minimalist web UI that replaces the Streamlit dashboard. Built with
Next.js (App Router), TypeScript, Tailwind CSS, shadcn-style primitives, and
TanStack Table. Business logic and schema live unchanged in the existing Python
services (`services/`, `database/`).

## Versão oficial do protótipo (porta 3000)

**Fonte de verdade:** [`PROTOTIPO_OFICIAL.md`](PROTOTIPO_OFICIAL.md) na raiz do repositório.

- **UI canónica:** `web-prototype/` → **`http://localhost:3000`**
- **API canónica:** `api-prototype/` → **`http://127.0.0.1:8000`** (típico)

Na **raiz do repositório**, `npm run dev` arranca **só o `web-prototype`** na porta **3000**.

```bash
npm install
npm install --prefix web-prototype
cp web-prototype/.env.example web-prototype/.env.local
# Edite web-prototype/.env.local (AUTH_SESSION_SECRET, ALIEH_AUTH_*, API_PROTOTYPE_URL, …)
npm run dev
```

### UI legada na raiz (referência, não oficial)

A pasta `app/` na raiz é um Next “clássico” mantido para referência. Para o subir noutra porta:

```bash
npm run dev:root
```

Abre em **`http://localhost:3001`**. Não usar como fluxo principal de desenvolvimento do protótipo.

### Build

- **Protótipo (`web-prototype`):** na raiz, `npm run build:prototype` (ou `npm run build` dentro de `web-prototype/`).
- **UI raiz (`app/`):** `npm run build` na raiz (para a app legada).

### Environment

Only these variables are required by the Node UI (see `.env.example`):

| Variable            | Purpose                                           |
| ------------------- | ------------------------------------------------- |
| `DATABASE_URL`      | Server-side Postgres / Supabase pooler URL        |
| `SUPABASE_DB_URL`   | Fallback for `DATABASE_URL`                       |
| `ALIEH_TENANT_ID`   | Default tenant, mirrors the Python app (`default`)|
| `POSTGRES_SSL`      | Set to `false` to disable TLS (local dev)         |

Secrets are **server-only**. The browser never receives them.

If neither `DATABASE_URL` nor `SUPABASE_DB_URL` is set, every page falls back to
mock data defined in `lib/queries.ts`. This keeps the UI navigable in demo mode.

## Routes

- `/dashboard` — KPIs (Revenue, Margin, Sales, Stock), revenue timeline, stock alerts
- `/products` — TanStack Table with debounced search, sort, pagination, mobile card fallback
- `/customers` — CRM list, tenant-scoped
- `/inventory` — `sku_master` summary
- `/sales` — recent sales

## Data layer

- `lib/db.ts` — thin `postgres` client with PgBouncer-safe settings (`prepare: false`)
- `lib/queries.ts` — mirrors the existing Python `fetch_*` queries; all wrapped
  with `unstable_cache` at 120s (equivalent to `st.cache_data(ttl=120)`)
- `lib/tenant.ts` — cookie/role helpers ready to hook RBAC into the data layer

## Deploy (Vercel)

1. `vercel link` in this folder
2. Add env vars in the project settings (`DATABASE_URL`, `ALIEH_TENANT_ID`)
3. Push to main — Next.js builds and deploys automatically
