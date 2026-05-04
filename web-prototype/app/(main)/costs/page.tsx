import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchCostsSkuMasters, fetchCostsSkuOptions, fetchStockCostHistory } from "@/lib/costs-api";
import { resolveRole } from "@/lib/tenant";
import { CostStructureForm } from "./components/cost-structure-form";
import { CostsKpiStrip } from "./components/costs-kpi-strip";
import { CostsTabs } from "./components/costs-tabs";
import { HistorySide, ValuationSide } from "./components/costs-side-panels";
import { StockReceiptForm } from "./components/stock-receipt-form";

export const revalidate = 0;

export default async function CostsPage() {
  const role = await resolveRole();
  const isAdmin = role === "admin";

  let masters: Awaited<ReturnType<typeof fetchCostsSkuMasters>> = [];
  let options: Awaited<ReturnType<typeof fetchCostsSkuOptions>> = { skus: [], pick_by_name: [] };
  let history: Awaited<ReturnType<typeof fetchStockCostHistory>> = [];
  let error: string | null = null;

  try {
    [masters, options, history] = await Promise.all([
      fetchCostsSkuMasters(),
      fetchCostsSkuOptions(),
      fetchStockCostHistory(75),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : "Não foi possível carregar custos.";
  }

  return (
    <div className="space-y-8 pb-16">
      {/* Header */}
      <header>
        <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">Operação · Custos</p>
        <h1 className="mt-2 font-serif text-5xl font-semibold tracking-tight md:text-6xl">Cockpit de custos</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">
          Composição estrutural por SKU e entrada de estoque que recalcula CMP por média ponderada. Vendas não
          alteram o CMP; preço de venda fica em{" "}
          <Link href="/pricing" className="text-foreground underline-offset-4 hover:underline">
            Precificação
          </Link>
          .
        </p>
      </header>

      {error ? (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-destructive">Erro</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Verifique <code className="rounded bg-muted px-1">API_PROTOTYPE_URL</code> e a sessão.
          </CardContent>
        </Card>
      ) : null}

      {!error ? (
        <>
          {/* KPI strip */}
          <CostsKpiStrip masters={masters} history={history} />

          {/* Cockpit grid: main panel + reference sidebar */}
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
            <main className="min-w-0">
              <CostsTabs
                composition={
                  <CostStructureForm skus={options.skus} pickByName={options.pick_by_name} isAdmin={isAdmin} />
                }
                stockEntry={
                  <StockReceiptForm skus={options.skus} pickByName={options.pick_by_name} isAdmin={isAdmin} />
                }
              />
            </main>

            <aside className="space-y-6">
              <ValuationSide masters={masters} />
              <HistorySide history={history} />
            </aside>
          </div>
        </>
      ) : null}
    </div>
  );
}
