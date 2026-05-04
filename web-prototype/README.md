# ALIEH — protótipo web (versão oficial)

Esta pasta é a **única UI Next.js** a tratar como protótipo de produto. Corre em **`http://localhost:3000`**.

## Arranque

```bash
# a partir da raiz do monorepo (recomendado)
cd ..
npm run dev

# ou só aqui
npm run dev
```

(`npm run dev` na raiz delega para este pacote na porta 3000.)

## API

O protótipo consome **`api-prototype/`** (FastAPI), tipicamente `http://127.0.0.1:8000`. Definir `API_PROTOTYPE_URL` em `.env.local`.

## Documentação global

Ver **`../PROTOTIPO_OFICIAL.md`** na raiz do repositório para a definição completa (o que é oficial vs legado).
