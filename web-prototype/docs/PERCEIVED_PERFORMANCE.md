# Percepção de performance (Next.js — protótipo)

Resumo técnico da **sexta passagem** (sem alterar `services/`, contratos REST nem motor Python).

**Camada global de dados (fases 1–2):** ver **`CLIENT_DATA_PHASES.md`** (`zustand`, `loadGlobalReadBundleAction`, `ClientDataProvider`).

## Lotes / nova venda

- `lib/sale-batches-client-dedupe.ts` — uma *Promise* partilhada por SKU entre prefetch, efeitos e abertura do select.
- `lib/prototype-client-cache.ts` — TTL **120 s** por SKU; limpeza após venda concluída.
- `new-sale-form.tsx` — prefetch até **24** SKUs; `onPointerDown` no select dispara prefetch de até **16** SKUs sem cache; cache-hit mostra dados de imediato e revalida em segundo plano (sem `useTransition` nesse caminho).

## Precificação

- `pricing-insight-client-cache.ts` — TTL **90 s**; dedupe in-flight por SKU.
- `pricing-workflow.tsx` — debounce **40 ms** em `loadInsight` e `scheduleComputePreview`.

## Navegação e layouts

- `components/top-nav.tsx` — `router.prefetch` em **hover** e **focus**; em **Vendas**, prefetch de `/sales`, `/sales/new`, `/customers`, `/inventory`.
- `app/(main)/sales/layout.tsx` — *warm* paralelo: SKUs vendáveis, clientes, `fetchPrototypeInventoryLotOptions`.

## Outros

- `components/data-table.tsx` — debounce de pesquisa **100 ms**.

Contratos e backend permanecem inalterados; apenas camada de cliente e RSC de aquecimento.
