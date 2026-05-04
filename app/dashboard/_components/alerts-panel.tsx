import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import type { Product } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/format";

type Alert = {
  level: "high" | "med" | "low";
  title: string;
  body: string;
  action: { label: string; href: string };
};

export function AlertsPanel({ products }: { products: Product[] }) {
  const alerts: Alert[] = [];

  const zero = products.filter((p) => p.stock === 0);
  if (zero.length > 0) {
    alerts.push({
      level: "high",
      title: `${zero.length} SKU(s) esgotado(s)`,
      body: zero.slice(0, 3).map((p) => p.name).join(", ") + (zero.length > 3 ? "…" : ""),
      action: { label: "Repor", href: "/inventory?q=" },
    });
  }

  const critical = products.filter((p) => p.stock > 0 && p.stock <= 5);
  if (critical.length > 0) {
    alerts.push({
      level: "high",
      title: `${critical.length} SKU(s) com estoque crítico (≤5)`,
      body: critical.slice(0, 3).map((p) => `${p.name} (${p.stock})`).join(", "),
      action: { label: "Acionar", href: "/inventory" },
    });
  }

  const lowMargin = products
    .filter((p) => p.price > 0 && p.stock > 0)
    .filter((p) => ((p.price - p.cost) / p.price) * 100 < 25);
  if (lowMargin.length > 0) {
    alerts.push({
      level: "med",
      title: `${lowMargin.length} SKU(s) com margem < 25%`,
      body: `Reveja precificação ou custo. Top exposições: ${lowMargin
        .slice(0, 2)
        .map((p) => p.name)
        .join(", ")}.`,
      action: { label: "Precificar", href: "/pricing" },
    });
  }

  const overStock = products.filter((p) => p.stock > 80);
  if (overStock.length > 0) {
    const tied = overStock.reduce((a, p) => a + p.stock * p.price, 0);
    alerts.push({
      level: "low",
      title: `${overStock.length} SKU(s) com excedente (>80 un)`,
      body: `${formatCurrency(tied)} de capital parado em SKUs com baixo giro potencial.`,
      action: { label: "Revisar", href: "/inventory" },
    });
  }

  const unpriced = products.filter((p) => p.price <= 0);
  if (unpriced.length > 0) {
    alerts.push({
      level: "med",
      title: `${unpriced.length} SKU(s) sem preço definido`,
      body: `Não podem ser vendidos. ${unpriced.slice(0, 2).map((p) => p.name).join(", ")}.`,
      action: { label: "Definir preço", href: "/pricing" },
    });
  }

  const levelColors: Record<Alert["level"], string> = {
    high: "border-l-destructive bg-destructive/[0.03]",
    med: "border-l-[#c7a35b] bg-[#c7a35b]/[0.04]",
    low: "border-l-foreground/30 bg-muted/15",
  };
  const levelLabel: Record<Alert["level"], string> = {
    high: "Crítico",
    med: "Atenção",
    low: "Monitorar",
  };

  return (
    <section className="rounded-2xl border border-border/60 bg-background">
      <header className="flex items-center justify-between border-b border-border/40 px-6 py-5">
        <div>
          <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Precisa de atenção</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {alerts.length === 0 ? "Tudo sob controlo." : `${alerts.length} sinal(is) ativo(s)`}
          </p>
        </div>
        <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">tempo real</span>
      </header>
      <div className="divide-y divide-border/30">
        {alerts.length === 0 ? (
          <p className="px-6 py-10 text-center text-sm text-muted-foreground">
            Nenhum alerta ativo. Bom trabalho.
          </p>
        ) : (
          alerts.map((a, i) => (
            <article
              key={i}
              className={`group flex items-start justify-between gap-4 border-l-2 px-6 py-4 transition-colors hover:bg-muted/20 ${levelColors[a.level]}`}
            >
              <div className="min-w-0 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                    {levelLabel[a.level]}
                  </span>
                </div>
                <p className="font-medium text-foreground">{a.title}</p>
                <p className="text-xs leading-5 text-muted-foreground">{a.body}</p>
              </div>
              <Link
                href={a.action.href}
                className="inline-flex shrink-0 items-center gap-1 rounded-full border border-border/60 px-3 py-1 text-xs text-foreground transition-colors hover:border-[#c7a35b]/60 hover:bg-[#c7a35b]/10"
              >
                {a.action.label}
                <ArrowUpRight className="h-3 w-3" />
              </Link>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
