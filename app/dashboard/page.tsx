import { Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { getCustomers, getDailyRevenue, getDashboardKpis, getProducts, getRecentSales } from "@/lib/queries";
import { AlertsPanel } from "./_components/alerts-panel";
import { BadgesRow } from "./_components/badges-row";
import { CustomerInsights } from "./_components/customer-insights";
import { ExecutiveStrip } from "./_components/executive-strip";
import { InsightsPanel } from "./_components/insights-panel";
import { InventoryIntel } from "./_components/inventory-intel";
import { PeriodFilter } from "./_components/period-filter";
import { ProductRanking } from "./_components/product-ranking";
import { RevenueAnalytics } from "./_components/revenue-analytics";

export const revalidate = 120;

export default function DashboardPage() {
  return (
    <div className="space-y-10 pb-16">
      {/* Editorial header */}
      <header className="flex flex-col gap-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">Cockpit</p>
            <h1 className="mt-2 font-serif text-5xl font-semibold tracking-tight md:text-6xl">
              Painel executivo
            </h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
              Sinais críticos, performance de produto e ações recomendadas — em tempo quase real.
            </p>
          </div>
          <PeriodFilter />
        </div>
      </header>

      {/* 1. Executive overview */}
      <Suspense fallback={<Skeleton className="h-36 rounded-2xl" />}>
        <ExecStripBlock />
      </Suspense>

      {/* 2. Insights — auto-surfaced */}
      <Suspense fallback={<Skeleton className="h-32" />}>
        <InsightsBlock />
      </Suspense>

      {/* 3. Revenue analytics + alerts side-by-side */}
      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <Suspense fallback={<Skeleton className="h-[360px] rounded-2xl" />}>
          <RevenueBlock />
        </Suspense>
        <Suspense fallback={<Skeleton className="h-[360px] rounded-2xl" />}>
          <AlertsBlock />
        </Suspense>
      </div>

      {/* 4. Product ranking */}
      <Suspense fallback={<Skeleton className="h-72 rounded-2xl" />}>
        <RankingBlock />
      </Suspense>

      {/* 5. Inventory + Customers */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Suspense fallback={<Skeleton className="h-[420px] rounded-2xl" />}>
          <InventoryBlock />
        </Suspense>
        <Suspense fallback={<Skeleton className="h-[420px] rounded-2xl" />}>
          <CustomersBlock />
        </Suspense>
      </div>

      {/* 6. Gamification */}
      <Suspense fallback={<Skeleton className="h-40 rounded-2xl" />}>
        <BadgesBlock />
      </Suspense>
    </div>
  );
}

async function ExecStripBlock() {
  const [kpis, daily, products] = await Promise.all([
    getDashboardKpis(),
    getDailyRevenue(),
    getProducts(),
  ]);
  return <ExecutiveStrip kpis={kpis} daily={daily} products={products} />;
}

async function InsightsBlock() {
  const [kpis, products, sales] = await Promise.all([
    getDashboardKpis(),
    getProducts(),
    getRecentSales(),
  ]);
  return <InsightsPanel kpis={kpis} products={products} sales={sales} />;
}

async function RevenueBlock() {
  const rows = await getDailyRevenue();
  return <RevenueAnalytics rows={rows} />;
}

async function AlertsBlock() {
  const products = await getProducts();
  return <AlertsPanel products={products} />;
}

async function RankingBlock() {
  const [products, sales] = await Promise.all([getProducts(), getRecentSales()]);
  return <ProductRanking products={products} sales={sales} />;
}

async function InventoryBlock() {
  const [products, sales] = await Promise.all([getProducts(), getRecentSales()]);
  return <InventoryIntel products={products} sales={sales} />;
}

async function CustomersBlock() {
  const [customers, sales] = await Promise.all([getCustomers(), getRecentSales()]);
  return <CustomerInsights customers={customers} sales={sales} />;
}

async function BadgesBlock() {
  const [kpis, products] = await Promise.all([getDashboardKpis(), getProducts()]);
  return <BadgesRow kpis={kpis} products={products} />;
}
