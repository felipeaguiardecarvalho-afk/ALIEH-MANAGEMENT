import type { ProductListRow } from "@/lib/products-api";
import { formatProductMoney, formatProductStock } from "@/lib/format";

const LOW_STOCK_THRESHOLD = 5;

export function ProductsKpiStrip({
  rows,
  total,
}: {
  rows: ProductListRow[];
  total: number;
}) {
  const stockSum = rows.reduce((acc, r) => acc + (Number(r.stock) || 0), 0);
  const priceVals = rows
    .map((r) => Number(r.sell_price))
    .filter((n) => Number.isFinite(n) && n > 0);
  const avgPrice =
    priceVals.length > 0
      ? priceVals.reduce((a, b) => a + b, 0) / priceVals.length
      : 0;
  const lowStock = rows.filter((r) => {
    const s = Number(r.stock);
    return Number.isFinite(s) && s <= LOW_STOCK_THRESHOLD;
  }).length;

  const items = [
    { label: "Total de produtos", value: String(total) },
    { label: "Estoque (página)", value: formatProductStock(stockSum) },
    { label: "Preço médio (página)", value: formatProductMoney(avgPrice) },
    {
      label: "Estoque baixo (≤5)",
      value: String(lowStock),
      tone: lowStock > 0 ? "warn" : undefined,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border/60 bg-border/60 md:grid-cols-4">
      {items.map((it) => (
        <div key={it.label} className="bg-background p-5">
          <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            {it.label}
          </p>
          <p
            className={`mt-2 font-serif text-2xl font-semibold tabular-nums tracking-tight ${
              it.tone === "warn" ? "text-[#d4b36c]" : "text-foreground"
            }`}
          >
            {it.value}
          </p>
        </div>
      ))}
    </div>
  );
}
