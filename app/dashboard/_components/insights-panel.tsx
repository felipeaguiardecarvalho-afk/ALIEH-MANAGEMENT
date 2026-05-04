import { AlertTriangle, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import type { DashboardKpis, Product, Sale } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/format";

type Insight = {
  tone: "good" | "warn" | "bad" | "neutral";
  icon: typeof Sparkles;
  title: string;
  body: string;
};

export function InsightsPanel({
  kpis,
  products,
  sales,
}: {
  kpis: DashboardKpis;
  products: Product[];
  sales: Sale[];
}) {
  const insights: Insight[] = [];

  // 1) Top SKU by revenue contribution (from sales)
  const skuRev = new Map<string, number>();
  let totalRev = 0;
  for (const s of sales) {
    if (!s.sku) continue;
    skuRev.set(s.sku, (skuRev.get(s.sku) ?? 0) + s.total);
    totalRev += s.total;
  }
  const topSku = [...skuRev.entries()].sort((a, b) => b[1] - a[1])[0];
  if (topSku && totalRev > 0) {
    const [sku, rev] = topSku;
    const share = (rev / totalRev) * 100;
    const prod = products.find((p) => p.sku === sku);
    insights.push({
      tone: share > 25 ? "warn" : "good",
      icon: TrendingUp,
      title: `${sku} concentra ${share.toFixed(0)}% da receita recente`,
      body: `${prod?.name ?? "Produto"} · ${formatCurrency(rev)} em ${sales.filter((s) => s.sku === sku).length} vendas. ${
        share > 25 ? "Risco de concentração — diversifique o catálogo top." : "Performance consistente; mantenha o estoque."
      }`,
    });
  }

  // 2) Highest margin product
  const margins = products
    .map((p) => ({ p, m: p.price > 0 ? ((p.price - p.cost) / p.price) * 100 : 0 }))
    .filter((x) => x.p.price > 0)
    .sort((a, b) => b.m - a.m);
  if (margins[0]) {
    const { p, m } = margins[0];
    insights.push({
      tone: "good",
      icon: Sparkles,
      title: `Maior margem: ${p.name}`,
      body: `${formatPercent(m)} sobre ${formatCurrency(p.price)} (custo ${formatCurrency(p.cost)}). Considere destaque editorial e priorize na precificação.`,
    });
  }

  // 3) Margin alert (low-margin products with stock)
  const lowMargin = margins.filter((x) => x.m < 25 && x.p.stock > 0);
  if (lowMargin.length > 0) {
    insights.push({
      tone: "bad",
      icon: TrendingDown,
      title: `${lowMargin.length} SKU(s) com margem abaixo de 25%`,
      body: `Reveja preço ou custo de ${lowMargin
        .slice(0, 3)
        .map((x) => x.p.name)
        .join(", ")}${lowMargin.length > 3 ? "…" : ""}.`,
    });
  }

  // 4) Stock risk
  const lowStock = products.filter((p) => p.stock > 0 && p.stock <= 5);
  const zero = products.filter((p) => p.stock === 0);
  if (lowStock.length + zero.length > 0) {
    insights.push({
      tone: lowStock.length + zero.length > 5 ? "bad" : "warn",
      icon: AlertTriangle,
      title: `${lowStock.length + zero.length} SKU(s) em risco de stock`,
      body: `${zero.length} esgotados, ${lowStock.length} com ≤5 unidades. Acionar reposição ou pausar campanhas afetadas.`,
    });
  }

  // 5) Margin headline
  if (kpis.marginPct > 35) {
    insights.push({
      tone: "good",
      icon: TrendingUp,
      title: `Margem agregada saudável: ${formatPercent(kpis.marginPct)}`,
      body: `Acima do alvo interno (35%). ${formatCurrency(kpis.profit)} de lucro nas últimas 30 vendas.`,
    });
  } else if (kpis.marginPct > 0 && kpis.marginPct < 25) {
    insights.push({
      tone: "warn",
      icon: TrendingDown,
      title: `Margem agregada apertada: ${formatPercent(kpis.marginPct)}`,
      body: `Abaixo do mínimo recomendado (25%). Investigue mix de vendas e descontos aplicados.`,
    });
  }

  if (insights.length === 0) {
    insights.push({
      tone: "neutral",
      icon: Sparkles,
      title: "Sem insights críticos no momento",
      body: "Quando entrarem mais vendas, sinais de concentração, margem e estoque aparecerão aqui automaticamente.",
    });
  }

  const toneStyles: Record<Insight["tone"], string> = {
    good: "border-[#1F6E4A]/30 bg-[#1F6E4A]/[0.05] text-[#1F6E4A]",
    warn: "border-[#c7a35b]/40 bg-[#c7a35b]/[0.06] text-[#a8782b]",
    bad: "border-destructive/30 bg-destructive/[0.05] text-destructive",
    neutral: "border-border/60 bg-muted/20 text-muted-foreground",
  };

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">Insights</h2>
        <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
          gerados automaticamente
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {insights.slice(0, 6).map((it, i) => {
          const Icon = it.icon;
          return (
            <article
              key={i}
              className="group relative flex gap-3 rounded-xl border border-border/60 bg-background p-4 transition-colors hover:border-border"
            >
              <span
                className={`mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${
                  toneStyles[it.tone]
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
              </span>
              <div className="min-w-0 space-y-1">
                <p className="font-serif text-base font-medium leading-tight tracking-tight text-foreground">
                  {it.title}
                </p>
                <p className="text-xs leading-5 text-muted-foreground">{it.body}</p>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
