import { Suspense } from "react";
import {
  DashboardDataSection,
  DashboardDataSkeleton,
  DashboardFiltersSkeleton,
} from "./dashboard-data-section";
import { DashboardFilters } from "./dashboard-filters";
import { normalizeDashboardQuery } from "@/lib/dashboard-url";

/** Cache curto para reduzir carga no upstream sem alterar fluxo funcional. */
export const revalidate = 30;

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const query = normalizeDashboardQuery(raw);
  const suspenseKey = `${query.period_preset}|${query.date_from}|${query.date_to}|${query.sku}|${query.customer_id}|${query.product_id}|${query.aging_min_days}|${query.active_customer_days}`;

  return (
    <div className="space-y-10 pb-16">
      <header className="flex flex-col gap-5">
        <div>
          <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">Cockpit</p>
          <h1 className="mt-2 font-serif text-5xl font-semibold tracking-tight md:text-6xl">
            Painel executivo
          </h1>
        </div>
      </header>

      <Suspense fallback={<DashboardFiltersSkeleton />}>
        <DashboardFilters query={query} />
      </Suspense>

      <Suspense key={suspenseKey} fallback={<DashboardDataSkeleton />}>
        <DashboardDataSection query={query} />
      </Suspense>
    </div>
  );
}
