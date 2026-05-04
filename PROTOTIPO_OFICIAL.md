# Protótipo oficial ALIEH (definição fixa)

## Versão oficial

| O quê | Onde | URL / porta |
|--------|------|-------------|
| **UI protótipo (única versão a usar no dia-a-dia)** | Pasta **`web-prototype/`** — Next.js App Router, TypeScript, Tailwind | **`http://localhost:3000`** |
| **API do protótipo** | Pasta **`api-prototype/`** — FastAPI | **`http://127.0.0.1:8000`** (por convenção) |

**Regra:** trabalhos de UI, rotas, componentes e `lib/` do protótipo fazem-se **sempre** dentro de **`web-prototype/`**. O arranque padrão na raiz do repositório é essa app na porta **3000**.

## Como subir

Na raiz do repositório:

```bash
npm run dev
```

Equivale a `npm --prefix web-prototype run dev` → Next na porta **3000**.

Com a API local:

```bash
npm run dev:api
```

(em outro terminal, depois configurar `API_PROTOTYPE_URL` no `.env.local` do `web-prototype`).

Variáveis: copiar `web-prototype/.env.example` → `web-prototype/.env.local`.

## O que **não** é o protótipo oficial

- **`app/`**, **`components/`** na **raiz** do repo — Next “clássico” de referência; arranque com `npm run dev:root` na porta **3001** se precisar de comparar (não usar como destino principal de desenvolvimento).
- **Streamlit** (`app.py`, etc.) — outro cliente do motor Python; não substitui o fluxo web em **3000**.
- **Worktrees** (ex. `.claude/worktrees/...`) — cópias experimentais; não são a fonte de verdade.

## Cursor / IDE

- Abrir o repositório na **raiz** `ALIEH management` e editar ficheiros sob **`web-prototype/`** para o protótipo web.
- Regra do projeto: `.cursor/rules/prototipo-oficial-alieh.mdc` (contexto persistente para agentes).

---

*Documento de referência operacional — actualizar se mudar porta ou pasta canónica.*
