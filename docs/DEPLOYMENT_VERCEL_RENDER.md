# Deploy — Vercel (Next) + Render (API)

## Vercel — `web-prototype`

O projecto já está **ligado** localmente (`web-prototype/.vercel/project.json`; pasta `.vercel` está no `.gitignore`). Conta **felipeaguiardecarvalho-1364**, projecto **`web-prototype`**.

**Produção (último deploy CLI):** [https://web-prototype-weld.vercel.app](https://web-prototype-weld.vercel.app) — confirme no [dashboard do projecto](https://vercel.com/felipeaguiardecarvalho-1364s-projects/web-prototype) e configure **Environment Variables** (sem elas a app pode falhar em runtime).

### Próximos passos no [Vercel Dashboard](https://vercel.com/dashboard)

1. Confirme que o projecto **web-prototype** existe e associe o **repositório Git** (Import / Settings → Git).
2. **Root Directory:** `web-prototype` (monorepo).
3. **Environment Variables** (Production / Preview), alinhadas ao Plano C e a `web-prototype/.env.example`:
   - `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `NEXT_PUBLIC_SUPABASE_*`, `SUPABASE_SERVICE_ROLE_KEY`
   - `API_PROTOTYPE_URL` = URL pública HTTPS do serviço Render (ex.: `https://alieh-api-prototype.onrender.com`)
   - `ALIEH_ENV=production`, `ALIEH_PROTOTYPE_OPEN=0`, `AUTH_SESSION_SECRET` (≥ 32 caracteres)
   - `ALIEH_TENANT_ID=default` (Plano C)
   - `PROTOTYPE_AUDIT_INGEST_SECRET`, `API_PROTOTYPE_INTERNAL_SECRET`, `API_PROTOTYPE_TRUSTED_ORIGINS` conforme `docs/DEPLOYMENT_ARCHITECTURE.md`
4. Deploy: na pasta `web-prototype`, `npx vercel@latest --prod` (ou push com Git integrado).

---

## Render — `api-prototype`

O ficheiro **`render.yaml`** na raiz define o serviço web **`alieh-api-prototype`**.

### Criar o serviço no [Render Dashboard](https://dashboard.render.com)

1. **New +** → **Blueprint** → ligue o **mesmo** repositório Git.
2. O Render detecta `render.yaml` e propõe o serviço; confirme a criação.
3. Em **Environment** do serviço, preencha as variáveis marcadas com `sync: false` no YAML (principalmente **`DATABASE_URL`** — o mesmo Supabase do Plano C / Streamlit).
4. Após o primeiro deploy com sucesso, copie a URL HTTPS (ex. `https://alieh-api-prototype.onrender.com`) para **`API_PROTOTYPE_URL`** no Vercel.

### CLI (opcional)

1. Instale o [Render CLI](https://render.com/docs/cli) (Windows: release `.zip` em [render-oss/cli](https://github.com/render-oss/cli/releases)).
2. `render login` (abre o browser) ou defina `RENDER_API_KEY` para CI.
3. Valide o blueprint: `render blueprints validate render.yaml`
4. Criação não interactiva de serviço Git: ver `render services create --help` (requer `--repo`, região, etc.).

---

## Ordem recomendada

1. **Render** — subir API e validar `GET /health`.
2. **Vercel** — definir `API_PROTOTYPE_URL` e restantes envs; deploy do Next.

Assim o build do Next não falha por URL da API ausente.
