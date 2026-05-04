import { Award, Crown, Flame, ShieldAlert, Sparkles, Target } from "lucide-react";
import type { DashboardKpis, Product } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/format";

const REVENUE_TARGET = 100_000; // monthly soft target (display-only)
const MARGIN_TARGET = 35; // %

export function BadgesRow({
  kpis,
  products,
}: {
  kpis: DashboardKpis;
  products: Product[];
}) {
  const revenueProgress = Math.min(100, (kpis.revenue / REVENUE_TARGET) * 100);
  const marginProgress = Math.min(100, (kpis.marginPct / MARGIN_TARGET) * 100);

  type Badge = { icon: typeof Sparkles; label: string; tone: "earned" | "near" | "risk"; sub: string };
  const badges: Badge[] = [];

  if (kpis.marginPct >= 35)
    badges.push({ icon: Sparkles, label: "High Margin Week", tone: "earned", sub: formatPercent(kpis.marginPct) });
  if (kpis.salesCount >= 30)
    badges.push({ icon: Crown, label: "Top Seller", tone: "earned", sub: `${kpis.salesCount} vendas` });
  if (kpis.uniqueCustomers >= 20)
    badges.push({ icon: Award, label: "Audience Builder", tone: "earned", sub: `${kpis.uniqueCustomers} clientes` });
  if (kpis.ticketAvg >= 400)
    badges.push({ icon: Flame, label: "Premium Ticket", tone: "earned", sub: formatCurrency(kpis.ticketAvg) });

  const lowStockCount = products.filter((p) => p.stock > 0 && p.stock <= 5).length + products.filter((p) => p.stock === 0).length;
  if (lowStockCount >= 5)
    badges.push({ icon: ShieldAlert, label: "Inventory Risk", tone: "risk", sub: `${lowStockCount} SKUs` });

  if (revenueProgress >= 50 && revenueProgress < 100)
    badges.push({ icon: Target, label: "Halfway to Target", tone: "near", sub: `${revenueProgress.toFixed(0)}%` });

  return (
    <section className="space-y-4 rounded-2xl border border-border/60 bg-background p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Conquistas do período</p>
          <p className="mt-1 text-xs text-muted-foreground">Métricas que celebram (ou avisam) este ciclo.</p>
        </div>
      </div>

      {/* Goal progress */}
      <div className="grid gap-5 md:grid-cols-2">
        <Goal
          label="Receita do período"
          value={formatCurrency(kpis.revenue)}
          target={formatCurrency(REVENUE_TARGET)}
          progress={revenueProgress}
        />
        <Goal
          label="Meta de margem"
          value={formatPercent(kpis.marginPct)}
          target={`${MARGIN_TARGET}%`}
          progress={marginProgress}
        />
      </div>

      {/* Badges */}
      {badges.length === 0 ? (
        <p className="border-t border-border/30 pt-4 text-xs text-muted-foreground">
          Quando atingir certos limiares (margem 35%, ticket alto, esgotamentos), badges aparecem aqui.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2 border-t border-border/30 pt-4">
          {badges.map((b, i) => {
            const Icon = b.icon;
            const tone =
              b.tone === "earned"
                ? "border-[#c7a35b]/40 bg-[#c7a35b]/[0.06] text-foreground"
                : b.tone === "near"
                  ? "border-foreground/20 bg-muted/30 text-foreground"
                  : "border-destructive/30 bg-destructive/[0.05] text-destructive";
            return (
              <span
                key={i}
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${tone}`}
                title={b.sub}
              >
                <Icon className="h-3 w-3" />
                <span className="font-medium">{b.label}</span>
                <span className="text-muted-foreground">·</span>
                <span className="font-mono tabular-nums text-muted-foreground">{b.sub}</span>
              </span>
            );
          })}
        </div>
      )}
    </section>
  );
}

function Goal({
  label,
  value,
  target,
  progress,
}: {
  label: string;
  value: string;
  target: string;
  progress: number;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
        <p className="text-[10px] tabular-nums text-muted-foreground">
          alvo <span className="text-foreground">{target}</span>
        </p>
      </div>
      <p className="font-serif text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
      <div className="relative h-1 overflow-hidden rounded-full bg-muted/40">
        <div
          className="h-full rounded-full bg-[#c7a35b] transition-[width] duration-500 ease-out"
          style={{ width: `${Math.max(progress, 2)}%` }}
        />
      </div>
      <p className="text-[10px] tabular-nums text-muted-foreground">{progress.toFixed(0)}% do alvo</p>
    </div>
  );
}
