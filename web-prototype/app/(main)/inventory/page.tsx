import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  fetchPrototypeInventoryLotOptions,
  fetchPrototypeInventoryLots,
} from "@/lib/inventory-api";
import { normalizeInventoryLotsParams, type InventoryLotsQuery } from "@/lib/inventory-url";
import { requireAdminForPricing } from "@/lib/rbac";
import { InventoryActiveFilters, InventoryControlStrip } from "./inventory-control-strip";
import { InventoryKpiStrip } from "./inventory-kpi-strip";
import { InventoryLotsInteractive } from "./inventory-lots-interactive";
import { WriteDownForm } from "./write-down-form";

export const revalidate = 0;

function hasActiveFilters(q: InventoryLotsQuery): boolean {
  const keys: (keyof InventoryLotsQuery)[] = [
    "names",
    "skus",
    "frame_colors",
    "lens_colors",
    "styles",
    "palettes",
    "genders",
    "costs",
    "prices",
    "markups",
    "stocks",
  ];
  return keys.some((k) => typeof q[k] === "string" && (q[k] as string).trim() !== "");
}

export default async function InventoryPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const denied = await requireAdminForPricing();
  if (denied) {
    return (
      <div className="space-y-8 pb-16">
        <InventoryHeader />
        <Card className="border-border/80">
          <CardHeader>
            <CardTitle>Acesso negado</CardTitle>
            <CardDescription>{denied.message}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  const raw = await searchParams;
  const normalized = normalizeInventoryLotsParams(raw);
  const listQuery: InventoryLotsQuery = { ...normalized };

  let error: string | null = null;
  let list: Awaited<ReturnType<typeof fetchPrototypeInventoryLots>> | null = null;
  let options: Awaited<ReturnType<typeof fetchPrototypeInventoryLotOptions>> | null = null;
  let globalStock: Awaited<ReturnType<typeof fetchPrototypeInventoryLots>> | null = null;
  let writeDownLots: Awaited<ReturnType<typeof fetchPrototypeInventoryLots>> | null = null;

  try {
    [list, options, globalStock, writeDownLots] = await Promise.all([
      fetchPrototypeInventoryLots(listQuery),
      fetchPrototypeInventoryLotOptions(),
      fetchPrototypeInventoryLots({ sort: "name" }, { page: "1", page_size: "1" }),
      fetchPrototypeInventoryLots({ sort: "name" }),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : "Não foi possível carregar o inventário.";
  }

  const noStockAnywhere = !error && globalStock && globalStock.total === 0;
  const filtersEmpty = !error && list && list.total === 0 && globalStock && globalStock.total > 0;
  const filtered = hasActiveFilters(listQuery);

  return (
    <div className="space-y-8 pb-16">
      <InventoryHeader />

      {error ? (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-destructive">Erro ao carregar</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Verifique <code className="rounded bg-muted px-1">API_PROTOTYPE_URL</code> e a api-prototype com ligação à
            base de dados.
          </CardContent>
        </Card>
      ) : null}

      {!error && noStockAnywhere ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/10 px-6 py-20 text-center">
          <p className="font-serif text-2xl tracking-tight text-foreground">Sem estoque</p>
          <p className="mt-2 max-w-sm text-sm text-muted-foreground">
            Ainda não há lotes com stock disponível. Cadastre produtos com quantidade em{" "}
            <Link href="/products" className="text-foreground underline-offset-4 hover:underline">
              Produtos
            </Link>
            .
          </p>
        </div>
      ) : null}

      {!error && list && options && writeDownLots && globalStock && !noStockAnywhere ? (
        <>
          {/* Top KPI strip — promoted from bottom */}
          <InventoryKpiStrip totals={list.totals} lotCount={list.total} filtered={filtered} />

          {/* Sticky control strip */}
          <InventoryControlStrip options={options} query={listQuery} />

          {/* Active filter pills */}
          <InventoryActiveFilters query={listQuery} />

          {/* Cockpit grid: data left, action rail right */}
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <main className="min-w-0">
              {filtersEmpty ? (
                <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/10 px-6 py-20 text-center">
                  <p className="font-serif text-xl tracking-tight">Nenhum lote nos filtros atuais</p>
                  <p className="mt-2 max-w-sm text-sm text-muted-foreground">
                    Remova alguma dimensão de filtro ou{" "}
                    <Link href="/inventory" className="text-foreground underline-offset-4 hover:underline">
                      limpe tudo
                    </Link>
                    .
                  </p>
                </div>
              ) : (
                <InventoryLotsInteractive items={list.items} isAdmin />
              )}
            </main>

            {/* Action rail */}
            <aside className="lg:sticky lg:top-6 lg:self-start">
              <section className="overflow-hidden rounded-2xl border border-border/60 bg-background">
                <header className="border-b border-border/40 px-5 py-4">
                  <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Baixa manual</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    Reduz <code className="rounded bg-muted px-1 text-[10px]">products.stock</code> — custo e preço
                    inalterados. A API impede stock negativo.
                  </p>
                </header>
                <div className="px-5 py-5">
                  <WriteDownForm lots={writeDownLots.items} />
                </div>
              </section>
            </aside>
          </div>
        </>
      ) : null}
    </div>
  );
}

function InventoryHeader() {
  return (
    <header>
      <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">Operação · Estoque</p>
      <h1 className="mt-2 font-serif text-5xl font-semibold tracking-tight md:text-6xl">Cockpit de estoque</h1>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">
        Lotes com stock, filtros multidimensionais e ordenação via API · baixa manual com optimistic UI · exclusão
        de lote por código de entrada (zera stock, custo e preço).
      </p>
    </header>
  );
}
