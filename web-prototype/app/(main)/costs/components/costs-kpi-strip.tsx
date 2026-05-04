import type { fetchCostsSkuMasters, fetchStockCostHistory } from "@/lib/costs-api";
import { formatCurrency, formatNumber, formatProductMoney } from "@/lib/format";

type Masters = Awaited<ReturnType<typeof fetchCostsSkuMasters>>;
type History = Awaited<ReturnType<typeof fetchStockCostHistory>>;

export function CostsKpiStrip({ masters, history }: { masters: Masters; history: History }) {
  const skuCount = masters.length;
  const capital = masters.reduce(
    (a, m) => a + (Number(m.total_stock) || 0) * (Number(m.avg_unit_cost) || 0),
    0
  );
  const totalStock = masters.reduce((a, m) => a + (Number(m.total_stock) || 0), 0);
  const cmpAvg = totalStock > 0 ? capital / totalStock : 0;
  const critical = masters.filter((m) => (Number(m.total_stock) || 0) <= 5).length;
  const lastEntry = history.length > 0 ? history[0].created_at : null;
  const lastEntryShort =
    lastEntry && typeof lastEntry === "string" ? lastEntry.slice(0, 10) : "—";

  const items = [
    {
      label: "SKUs no mestre",
      value: formatNumber(skuCount),
      hint: `${formatNumber(totalStock)} unidades totais`,
    },
    {
      label: "Capital em estoque (CMP)",
      value: formatCurrency(capital),
      hint: "stock × custo médio",
      accent: true,
    },
    {
      label: "CMP médio ponderado",
      value: formatProductMoney(cmpAvg),
      hint: "capital ÷ unidades",
    },
    {
      label: "SKUs críticos",
      value: formatNumber(critical),
      hint: "stock ≤ 5",
      tone: critical > 0 ? "warn" : undefined,
    },
    {
      label: "Última entrada",
      value: lastEntryShort,
      hint: history.length ? `${formatNumber(history.length)} no log` : "sem registros",
      mono: true,
    },
  ];

  return (
    <section className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border/60 bg-border/60 md:grid-cols-3 lg:grid-cols-5">
      {items.map((it) => (
        <div key={it.label} className="bg-background px-5 py-5">
          <p className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">{it.label}</p>
          <p
            className={`mt-2 font-serif text-2xl font-semibold tabular-nums tracking-tight ${
              it.tone === "warn" ? "text-[#d4b36c]" : it.accent ? "text-foreground" : "text-foreground"
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
