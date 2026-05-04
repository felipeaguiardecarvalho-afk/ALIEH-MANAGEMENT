import type { Product, Sale } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/format";

type Mode = "revenue" | "margin" | "stock_value";

function rank(products: Product[], sales: Sale[], mode: Mode) {
  if (mode === "revenue") {
    const map = new Map<string, number>();
    for (const s of sales) if (s.sku) map.set(s.sku, (map.get(s.sku) ?? 0) + s.total);
    return [...map.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([sku, val]) => {
        const p = products.find((x) => x.sku === sku);
        return { sku, label: p?.name ?? sku, value: val };
      });
  }
  if (mode === "margin") {
    return products
      .filter((p) => p.price > 0)
      .map((p) => ({ sku: p.sku ?? String(p.id), label: p.name, value: ((p.price - p.cost) / p.price) * 100 }))
      .sort((a, b) => b.value - a.value);
  }
  return products
    .map((p) => ({ sku: p.sku ?? String(p.id), label: p.name, value: p.stock * p.price }))
    .sort((a, b) => b.value - a.value);
}

export function ProductRanking({
  products,
  sales,
}: {
  products: Product[];
  sales: Sale[];
}) {
  const byRevenue = rank(products, sales, "revenue").slice(0, 5);
  const byMargin = rank(products, sales, "margin").slice(0, 5);
  const byStockValue = rank(products, sales, "stock_value").slice(0, 5);

  return (
    <section className="rounded-2xl border border-border/60 bg-background">
      <header className="flex items-center justify-between border-b border-border/40 px-6 py-5">
        <div>
          <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Performance de produto</p>
          <p className="mt-1 text-xs text-muted-foreground">Top 5 por receita, margem e valor em estoque.</p>
        </div>
      </header>
      <div className="grid gap-px bg-border/60 lg:grid-cols-3">
        <Column title="Receita" rows={byRevenue} format={(v) => formatCurrency(v)} />
        <Column title="Margem" rows={byMargin} format={(v) => formatPercent(v)} bar="margin" />
        <Column title="Valor em estoque" rows={byStockValue} format={(v) => formatCurrency(v)} />
      </div>
    </section>
  );
}

function Column({
  title,
  rows,
  format,
  bar,
}: {
  title: string;
  rows: { sku: string; label: string; value: number }[];
  format: (v: number) => string;
  bar?: "margin";
}) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="bg-background p-6">
      <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{title}</p>
      {rows.length === 0 ? (
        <p className="mt-4 text-xs text-muted-foreground">Sem dados.</p>
      ) : (
        <ol className="mt-4 space-y-3">
          {rows.map((r, i) => {
            const w = bar === "margin" ? Math.min(100, r.value) : (r.value / max) * 100;
            return (
              <li key={r.sku} className="space-y-1.5">
                <div className="flex items-baseline justify-between gap-3">
                  <div className="flex min-w-0 items-baseline gap-2">
                    <span className="text-[10px] tabular-nums text-muted-foreground">{i + 1}.</span>
                    <span className="truncate text-sm text-foreground">{r.label}</span>
                  </div>
                  <span className="shrink-0 font-mono text-xs tabular-nums text-foreground">
                    {format(r.value)}
                  </span>
                </div>
                <div className="h-px w-full bg-muted/40">
                  <div
                    className="h-full bg-[#c7a35b]"
                    style={{ width: `${Math.max(w, 2)}%` }}
                  />
                </div>
                <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  {r.sku}
                </p>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
