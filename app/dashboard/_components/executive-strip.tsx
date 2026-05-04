import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { DashboardKpis, DailyRevenue, Product } from "@/lib/types";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/format";

function splitPeriod(rows: DailyRevenue[]) {
  if (rows.length === 0) return { prev: 0, curr: 0, prevSales: 0, currSales: 0 };
  const sorted = [...rows].sort((a, b) => a.day.localeCompare(b.day));
  const mid = Math.floor(sorted.length / 2);
  const prev = sorted.slice(0, mid).reduce((a, r) => a + r.revenue, 0);
  const curr = sorted.slice(mid).reduce((a, r) => a + r.revenue, 0);
  return { prev, curr, prevSales: 0, currSales: 0 };
}

function pct(curr: number, prev: number) {
  if (prev === 0) return curr === 0 ? 0 : 100;
  return ((curr - prev) / prev) * 100;
}

export function ExecutiveStrip({
  kpis,
  daily,
  products,
}: {
  kpis: DashboardKpis;
  daily: DailyRevenue[];
  products: Product[];
}) {
  const { prev, curr } = splitPeriod(daily);
  const revenueDelta = pct(curr, prev);

  const prevProfit = daily.slice(0, Math.floor(daily.length / 2)).reduce((a, r) => a + r.profit, 0);
  const currProfit = daily.slice(Math.floor(daily.length / 2)).reduce((a, r) => a + r.profit, 0);
  const prevMargin = prev > 0 ? (prevProfit / prev) * 100 : 0;
  const currMargin = curr > 0 ? (currProfit / curr) * 100 : 0;
  const marginDelta = currMargin - prevMargin; // points

  const stockValue = products.reduce((a, p) => a + p.stock * p.price, 0);

  const items = [
    {
      label: "Receita 30d",
      value: formatCurrency(kpis.revenue),
      delta: revenueDelta,
      hint: `${formatNumber(kpis.salesCount)} vendas · ticket ${formatCurrency(kpis.ticketAvg)}`,
    },
    {
      label: "Margem",
      value: formatPercent(kpis.marginPct),
      delta: marginDelta,
      deltaSuffix: "pp",
      hint: `${formatCurrency(kpis.profit)} de lucro`,
    },
    {
      label: "Vendas",
      value: formatNumber(kpis.salesCount),
      delta: pct(daily.slice(Math.floor(daily.length / 2)).length, daily.slice(0, Math.floor(daily.length / 2)).length),
      hint: `${formatNumber(kpis.uniqueCustomers)} clientes únicos`,
    },
    {
      label: "Valor em estoque",
      value: formatCurrency(stockValue),
      hint: `${formatNumber(kpis.stockUnits)} unidades em ${products.length} SKUs`,
    },
  ];

  return (
    <section className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border/60 bg-border/60 lg:grid-cols-4">
      {items.map((it) => {
        const hasDelta = typeof it.delta === "number";
        const positive = hasDelta && (it.delta as number) >= 0;
        const Arrow = positive ? ArrowUpRight : ArrowDownRight;
        return (
          <div key={it.label} className="bg-background px-6 py-7">
            <p className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">{it.label}</p>
            <p className="mt-3 font-serif text-3xl font-semibold tabular-nums tracking-tight md:text-4xl">
              {it.value}
            </p>
            <div className="mt-3 flex items-center gap-2 text-xs">
              {hasDelta ? (
                <span
                  className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 tabular-nums ${
                    positive
                      ? "bg-[#1F6E4A]/10 text-[#1F6E4A]"
                      : "bg-destructive/10 text-destructive"
                  }`}
                >
                  <Arrow className="h-3 w-3" />
                  {Math.abs(it.delta as number).toFixed(1)}
                  {it.deltaSuffix ?? "%"}
                </span>
              ) : null}
              <span className="truncate text-muted-foreground">{it.hint}</span>
            </div>
          </div>
        );
      })}
    </section>
  );
}
