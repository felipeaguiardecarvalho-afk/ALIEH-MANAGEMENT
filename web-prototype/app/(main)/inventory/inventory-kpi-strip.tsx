import type { InventoryLotsTotals } from "@/lib/inventory-api";
import { formatCurrency, formatProductStock } from "@/lib/format";

export function InventoryKpiStrip({
  totals,
  lotCount,
  filtered,
}: {
  totals: InventoryLotsTotals;
  lotCount: number;
  filtered: boolean;
}) {
  const items = [
    {
      label: "Lotes ativos",
      value: String(lotCount),
      hint: filtered ? "no filtro atual" : "todos com stock > 0",
      mono: true,
    },
    {
      label: "Stock total",
      value: formatProductStock(totals.total_stock),
      hint: "unidades",
    },
    {
      label: "Capital custo",
      value: formatCurrency(totals.total_cost_value),
      hint: "stock × custo",
    },
    {
      label: "Receita potencial",
      value: formatCurrency(totals.total_revenue_value),
      hint: "stock × preço",
      accent: true,
    },
    {
      label: "Margem potencial",
      value: formatCurrency(totals.total_margin_value),
      hint: "stock × margem",
    },
  ];

  return (
    <section className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border/60 bg-border/60 md:grid-cols-3 lg:grid-cols-5">
      {items.map((it) => (
        <div key={it.label} className="bg-background px-5 py-5">
          <p className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">{it.label}</p>
          <p
            className={`mt-2 font-serif text-2xl font-semibold tabular-nums tracking-tight ${
              it.accent ? "text-[#d4b36c]" : "text-foreground"
            } ${it.mono ? "font-mono text-xl" : ""}`}
          >
            {it.value}
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">{it.hint}</p>
        </div>
      ))}
    </section>
  );
}
