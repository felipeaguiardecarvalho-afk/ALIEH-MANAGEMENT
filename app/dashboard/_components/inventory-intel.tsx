import Link from "next/link";
import type { Product, Sale } from "@/lib/types";
import { formatCurrency, formatNumber } from "@/lib/format";

const BUCKETS = [
  { id: "out", label: "Esgotado", min: 0, max: 0 },
  { id: "crit", label: "Crítico (1–5)", min: 1, max: 5 },
  { id: "low", label: "Baixo (6–15)", min: 6, max: 15 },
  { id: "ok", label: "Saudável (16–50)", min: 16, max: 50 },
  { id: "high", label: "Excedente (50+)", min: 51, max: Infinity },
];

export function InventoryIntel({
  products,
  sales,
}: {
  products: Product[];
  sales: Sale[];
}) {
  const totalSkus = products.length;
  const buckets = BUCKETS.map((b) => ({
    ...b,
    count: products.filter((p) => p.stock >= b.min && p.stock <= b.max).length,
  }));
  const maxBucket = Math.max(...buckets.map((b) => b.count), 1);

  // Slow-moving = stock > 0 but no sales in window (sales is recent sales)
  const soldSkus = new Set(sales.map((s) => s.sku).filter(Boolean) as string[]);
  const slowMoving = products
    .filter((p) => p.stock > 0 && p.sku && !soldSkus.has(p.sku))
    .sort((a, b) => b.stock * b.price - a.stock * a.price)
    .slice(0, 5);

  const critical = products
    .filter((p) => p.stock <= 5)
    .sort((a, b) => a.stock - b.stock)
    .slice(0, 5);

  const tiedCapital = products.reduce((a, p) => a + p.stock * p.price, 0);

  return (
    <section className="rounded-2xl border border-border/60 bg-background">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-border/40 px-6 py-5">
        <div>
          <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Inteligência de estoque</p>
          <p className="mt-2 font-serif text-2xl font-semibold tabular-nums tracking-tight">
            {formatCurrency(tiedCapital)}
          </p>
          <p className="text-xs text-muted-foreground">capital em {totalSkus} SKUs</p>
        </div>
      </header>

      {/* Stock distribution */}
      <div className="border-b border-border/40 px-6 py-5">
        <p className="mb-3 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Distribuição</p>
        <div className="space-y-2.5">
          {buckets.map((b) => (
            <div key={b.id} className="grid grid-cols-[8rem_1fr_4rem] items-center gap-3">
              <span className={`text-xs ${b.id === "out" ? "text-destructive" : b.id === "crit" ? "text-[#a8782b]" : "text-foreground"}`}>
                {b.label}
              </span>
              <div className="h-1.5 overflow-hidden rounded-full bg-muted/40">
                <div
                  className={`h-full rounded-full ${
                    b.id === "out"
                      ? "bg-destructive/80"
                      : b.id === "crit"
                        ? "bg-[#c7a35b]"
                        : b.id === "high"
                          ? "bg-foreground/70"
                          : "bg-foreground/40"
                  }`}
                  style={{ width: `${Math.max((b.count / maxBucket) * 100, b.count > 0 ? 4 : 0)}%` }}
                />
              </div>
              <span className="text-right font-mono text-xs tabular-nums text-foreground">
                {formatNumber(b.count)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Critical stock */}
      <div className="border-b border-border/40 px-6 py-5">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Estoque crítico</p>
          <Link href="/inventory" className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground hover:text-foreground">
            ver tudo →
          </Link>
        </div>
        {critical.length === 0 ? (
          <p className="text-xs text-muted-foreground">Nenhum SKU em estado crítico.</p>
        ) : (
          <ul className="divide-y divide-border/30">
            {critical.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm text-foreground">{p.name}</p>
                  <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    {p.sku ?? "—"}
                  </p>
                </div>
                <span
                  className={`shrink-0 font-mono text-sm tabular-nums ${
                    p.stock === 0 ? "text-destructive" : "text-[#d4b36c]"
                  }`}
                >
                  {formatNumber(p.stock)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Slow moving */}
      <div className="px-6 py-5">
        <p className="mb-3 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
          Aging · sem vendas no período
        </p>
        {slowMoving.length === 0 ? (
          <p className="text-xs text-muted-foreground">Todos os SKUs com estoque tiveram movimento.</p>
        ) : (
          <ul className="space-y-2">
            {slowMoving.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-3 rounded-lg bg-muted/15 px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm text-foreground">{p.name}</p>
                  <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    {p.sku ?? "—"} · {formatNumber(p.stock)} un
                  </p>
                </div>
                <span className="shrink-0 font-mono text-xs tabular-nums text-muted-foreground">
                  {formatCurrency(p.stock * p.price)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
