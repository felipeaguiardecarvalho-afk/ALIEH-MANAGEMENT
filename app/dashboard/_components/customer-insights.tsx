import type { Customer, Sale } from "@/lib/types";
import { formatCurrency, formatNumber } from "@/lib/format";

export function CustomerInsights({
  customers,
  sales,
}: {
  customers: Customer[];
  sales: Sale[];
}) {
  // Aggregate by customerId
  const map = new Map<number, { revenue: number; count: number }>();
  for (const s of sales) {
    if (s.customerId == null) continue;
    const cur = map.get(s.customerId) ?? { revenue: 0, count: 0 };
    cur.revenue += s.total;
    cur.count += 1;
    map.set(s.customerId, cur);
  }
  const top = [...map.entries()]
    .map(([id, v]) => {
      const c = customers.find((x) => x.id === id);
      return { id, name: c?.name ?? `#${id}`, code: c?.customerCode ?? "—", ...v };
    })
    .sort((a, b) => b.revenue - a.revenue)
    .slice(0, 5);

  const repeat = [...map.values()].filter((v) => v.count > 1).length;
  const totalUnique = map.size;
  const repeatRate = totalUnique > 0 ? (repeat / totalUnique) * 100 : 0;
  const totalCustomerRev = [...map.values()].reduce((a, v) => a + v.revenue, 0);
  const avgPerCustomer = totalUnique > 0 ? totalCustomerRev / totalUnique : 0;

  return (
    <section className="rounded-2xl border border-border/60 bg-background">
      <header className="border-b border-border/40 px-6 py-5">
        <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Clientes</p>
        <div className="mt-3 grid grid-cols-3 gap-4">
          <Stat label="Compradores" value={formatNumber(totalUnique)} />
          <Stat label="Recorrência" value={`${repeatRate.toFixed(0)}%`} hint={`${repeat} repetiram`} />
          <Stat label="LTV médio" value={formatCurrency(avgPerCustomer)} />
        </div>
      </header>
      <div className="px-6 py-5">
        <p className="mb-3 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Top compradores</p>
        {top.length === 0 ? (
          <p className="text-xs text-muted-foreground">Sem vendas atribuídas a clientes no período.</p>
        ) : (
          <ol className="space-y-2.5">
            {top.map((c, i) => (
              <li key={c.id} className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-baseline gap-2">
                  <span className="text-[10px] tabular-nums text-muted-foreground">{i + 1}.</span>
                  <div className="min-w-0">
                    <p className="truncate text-sm text-foreground">{c.name}</p>
                    <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                      {c.code} · {c.count} compra{c.count > 1 ? "s" : ""}
                    </p>
                  </div>
                </div>
                <span className="shrink-0 font-mono text-sm tabular-nums text-foreground">
                  {formatCurrency(c.revenue)}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
      <p className="mt-1 font-serif text-xl font-semibold tabular-nums tracking-tight">{value}</p>
      {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
