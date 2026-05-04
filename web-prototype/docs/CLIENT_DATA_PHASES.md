# Client data layer & performance phases (Next protótipo)

Backend / contratos / `services/` **não** foram alterados.

## Phase 1 — Global client store (Zustand)

- **`lib/client-data/store.ts`**: estado global com TTL (~120 s) para clientes, SKUs vendáveis, opções de filtro de inventário, lista mestre de precificação; `batchesBySku` com `{ data, ts, promise }` + dedupe in-flight.
- **`lib/actions/client-data-bootstrap.ts`**: `loadGlobalReadBundleAction()` — **um** server action, `Promise.allSettled` no servidor (mesmos endpoints que antes).
- **`lib/customers-map.ts`**: mapeamento partilhado `CustomerApiRow` → `Customer`.
- **`components/client-data-provider.tsx`**: após navegação, `ensureGlobalBundle()` e prefetch de lotes em `/sales/*`.

## Phase 2 — Prefetch agressivo

- **`top-nav.tsx`**: ao pairar/focar **Vendas**, além de `router.prefetch`, chama `ensureGlobalBundle` + `prefetchSaleBatchCluster` (até 28 SKUs).
- **`new-sale-form.tsx`**: `hydrateSalePage` com dados SSR; `prefetchSaleBatchCluster` no mount e em `onPointerDown` no select de SKU.

## Phase 3 — Menos fetch dependente (Nova venda)

- Lotes vêm da **store** (`ensureSaleBatches`); UI lê `batchSlot` — cache-hit + refresh em segundo plano (com `sale-batches-client-dedupe` + `prototype-client-cache`).

## Phases 4–7

- **4**: bundle único + reutilização de promises na store.
- **5**: `useOptimistic` já existente em vendas / precificação / inventário / clientes — mantido.
- **6–7**: sem *full-page loaders* novos; estado global mantém-se entre rotas no **cliente** (hard reload limpa a store).

## Phase 8 — Virtualização (pendente)

- Listas muito grandes (inventário / clientes / produtos): candidato a `@tanstack/react-virtual` ou virtualização na grelha; **não** incluído neste PR para evitar regressões de layout na `<table>`.

## Phase 9–10

- Padrão SWR coberto pela store (TTL + `promise`); micro-latências já reduzidas em `pricing-workflow` e `data-table` (ver `PERCEIVED_PERFORMANCE.md`).
