import { ArrowDownRight, ArrowUpRight, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  fetchPrototypeDashboardPanel,
  type DashboardCustomerBreakdown,
  type DashboardDailyRow,
  type DashboardMarginSkuRow,
  type DashboardPanelResponse,
  type DashboardProductBreakdown,
  type DashboardSkuBreakdown,
  type DashboardStockTurnoverRow,
} from "@/lib/dashboard-api";
import type { DashboardQuery } from "@/lib/dashboard-url";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/format";

// ---------- helpers ----------

function deltaPctText(d: number | null | undefined): string | null {
  if (d == null || !Number.isFinite(d)) return null;
  return `${d >= 0 ? "+" : ""}${d.toFixed(1)}%`;
}

function deltaPpText(d: number | null | undefined): string | null {
  if (d == null || !Number.isFinite(d) || Math.abs(d) < 0.05) return null;
  return `${d >= 0 ? "+" : ""}${d.toFixed(1)}pp`;
}

// ---------- main ----------

export async function DashboardDataSection({ query }: { query: DashboardQuery }) {
  let data: DashboardPanelResponse;
  try {
    data = await fetchPrototypeDashboardPanel(query);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Erro ao carregar painel.";
    return (
      <Card className="border-destructive/50">
        <CardHeader>
          <CardTitle className="text-destructive">Painel indisponível</CardTitle>
          <CardDescription>{msg}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            Verifique <code className="rounded bg-muted px-1">API_PROTOTYPE_URL</code>, se a FastAPI está a correr na
            porta correcta e a sessão.
          </p>
        </CardContent>
      </Card>
    );
  }

  const {
    kpis,
    kpi_deltas: dlt,
    active_customers_window,
    daily,
    breakdown_skus,
    breakdown_products,
    breakdown_customers,
    breakdown_payment,
    margin_by_sku,
    cohort,
    stock_aging,
    low_stock,
    inventory_summary,
    insights,
    stock_turnover = [],
  } = data;

  /** Stock ≤ 1 — filtro na UI alinhado ao contrato do painel (defesa se a API devolver linhas extra). */
  const lowStockAtMostOne = low_stock.filter((r) => (Number(r.stock) || 0) <= 1);

  return (
    <div className="space-y-10">
      {/* Reference period note */}
      <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
        referência para deltas ·{" "}
        <span className="text-foreground tabular-nums">{data.prev_date_start}</span>
        <span className="mx-2 inline-block h-px w-3 bg-border align-middle" />
        <span className="text-foreground tabular-nums">{data.prev_date_end}</span>
      </p>

      {/* 1. Insights */}
      <InsightsBlock lines={insights} />

      {/* 2. Executive strip */}
      <ExecutiveStrip
        kpis={kpis}
        deltas={dlt}
        activeCustomers={active_customers_window}
        activeDays={data.filters.active_customer_days}
        dateEnd={data.date_end}
        inventoryValue={inventory_summary.value_cmp}
        inventoryUnits={inventory_summary.total_units}
        criticalSkus={lowStockAtMostOne.length}
        stockUnits={kpis.stock_units}
        uniqueCustomers={kpis.unique_customers}
      />

      {/* 3. Revenue analytics + Payments */}
      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <Section
          eyebrow="Receita · 30 dias"
          title={`${data.date_start} → ${data.date_end}`}
          subtitle="Linha diária + média móvel 7d (server-side)"
        >
          <DailyRevenueChart rows={daily} />
        </Section>
        <Section eyebrow="Pagamentos" title="Receita por método">
          <PaymentBreakdownChart rows={breakdown_payment} />
        </Section>
      </div>

      {/* 4. Margin per SKU + Cohort */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Section eyebrow="Margem por SKU" title="Lucro ÷ receita" subtitle="Até 12 SKUs">
          <MarginSkuChart rows={margin_by_sku} />
        </Section>
        <Section eyebrow="Cohort · primeira compra" title="Clientes novos por mês">
          <CohortChart rows={cohort} />
        </Section>
      </div>

      {/* 5. Stock turnover */}
      <Section
        eyebrow="Giro de stock"
        title="Unidades vendidas ÷ stock no período"
        subtitle="Até 20 SKUs com venda — paridade Streamlit"
      >
        <StockTurnoverChart rows={stock_turnover} />
      </Section>

      {/* 6. Aging + Low stock */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Section
          eyebrow="Inventário envelhecido"
          title="Aging"
          subtitle={`Sem venda há ≥ ${data.filters.aging_min_days} dias`}
        >
          <StockAgingTable rows={stock_aging} />
        </Section>
        <Section
          eyebrow="Estoque crítico"
          title="Stock ≤ 1"
          subtitle="Apenas produtos com 0 ou 1 unidade — Crítico = esgotado; Baixo = última unidade"
        >
          <LowStockTable rows={lowStockAtMostOne} />
        </Section>
      </div>

      {/* 7. Top breakdowns */}
      <Section eyebrow="Performance de produto" title="Top do período">
        <div className="grid gap-px bg-border/60 lg:grid-cols-3">
          <Sub title="Top SKUs">
            <SkuBreakdownChart rows={breakdown_skus} />
          </Sub>
          <Sub title="Top produtos">
            <ProductBreakdownChart rows={breakdown_products} />
          </Sub>
          <Sub title="Principais clientes">
            <CustomerBreakdownChart rows={breakdown_customers} />
          </Sub>
        </div>
      </Section>
    </div>
  );
}

// ============= SECTION SHELL =============

function Section({
  eyebrow,
  title,
  subtitle,
  children,
}: {
  eyebrow: string;
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-border/60 bg-background">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-border/40 px-6 py-5">
        <div>
          <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">{eyebrow}</p>
          {title ? (
            <p className="mt-1.5 font-serif text-lg font-medium tabular-nums tracking-tight">{title}</p>
          ) : null}
          {subtitle ? <p className="text-xs text-muted-foreground">{subtitle}</p> : null}
        </div>
      </header>
      <div className="px-6 py-6">{children}</div>
    </section>
  );
}

function Sub({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-background p-6">
      <p className="mb-4 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{title}</p>
      {children}
    </div>
  );
}

// ============= INSIGHTS =============

function InsightsBlock({ lines }: { lines: string[] }) {
  if (!lines || !lines.length) return null;
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">
          <Sparkles className="h-3 w-3" />
          Insights
        </h2>
        <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
          gerados automaticamente
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {lines.slice(0, 6).map((line, i) => (
          <article
            key={i}
            className="group rounded-xl border border-border/60 bg-background p-4 transition-colors hover:border-border"
          >
            <p className="text-sm leading-6 text-foreground">{line}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

// ============= EXECUTIVE STRIP =============

function ExecutiveStrip({
  kpis,
  deltas,
  activeCustomers,
  activeDays,
  dateEnd,
  inventoryValue,
  inventoryUnits,
  criticalSkus,
  stockUnits,
  uniqueCustomers,
}: {
  kpis: DashboardPanelResponse["kpis"];
  deltas: DashboardPanelResponse["kpi_deltas"];
  activeCustomers: number;
  activeDays: number;
  dateEnd: string;
  inventoryValue: number;
  inventoryUnits: number;
  criticalSkus: number;
  stockUnits: number;
  uniqueCustomers: number;
}) {
  const items: Array<{
    label: string;
    value: string;
    delta?: string | null;
    deltaPositive?: boolean;
    hint: string;
  }> = [
    {
      label: "Receita",
      value: formatCurrency(kpis.revenue),
      delta: deltaPctText(deltas.revenue_pct),
      deltaPositive: (deltas.revenue_pct ?? 0) >= 0,
      hint: `${formatNumber(kpis.sales_count)} vendas`,
    },
    {
      label: "Margem bruta",
      value: formatPercent(kpis.margin_pct),
      delta: deltaPpText(deltas.margin_pp),
      deltaPositive: (deltas.margin_pp ?? 0) >= 0,
      hint: `${formatCurrency(kpis.profit)} de lucro`,
    },
    {
      label: "Volume",
      value: formatNumber(kpis.sales_count),
      delta: deltaPctText(deltas.sales_count_pct),
      deltaPositive: (deltas.sales_count_pct ?? 0) >= 0,
      hint: `ticket ${formatCurrency(kpis.ticket_avg)}`,
    },
    {
      label: "Ticket médio",
      value: formatCurrency(kpis.ticket_avg),
      delta: deltaPctText(deltas.ticket_avg_pct),
      deltaPositive: (deltas.ticket_avg_pct ?? 0) >= 0,
      hint: "receita ÷ linhas",
    },
  ];

  return (
    <div className="space-y-4">
      <section className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border/60 bg-border/60 lg:grid-cols-4">
        {items.map((it) => {
          const Arrow = it.deltaPositive ? ArrowUpRight : ArrowDownRight;
          return (
            <div key={it.label} className="bg-background px-6 py-7">
              <p className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">{it.label}</p>
              <p className="mt-3 font-serif text-3xl font-semibold tabular-nums tracking-tight md:text-4xl">
                {it.value}
              </p>
              <div className="mt-3 flex items-center gap-2 text-xs">
                {it.delta ? (
                  <span
                    className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 tabular-nums ${
                      it.deltaPositive
                        ? "bg-[#1F6E4A]/10 text-emerald-300"
                        : "bg-destructive/10 text-destructive"
                    }`}
                  >
                    <Arrow className="h-3 w-3" />
                    {it.delta.replace(/^[+-]/, "")}
                  </span>
                ) : null}
                <span className="truncate text-muted-foreground">{it.hint}</span>
              </div>
            </div>
          );
        })}
      </section>

      {/* Secondary inline metrics — chrome-less */}
      <section className="grid gap-px overflow-hidden rounded-2xl border border-border/60 bg-border/60 sm:grid-cols-3">
        <div className="bg-background px-6 py-5">
          <p className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">Clientes activos</p>
          <p className="mt-2 font-serif text-2xl font-semibold tabular-nums tracking-tight">
            {formatNumber(activeCustomers)}
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            últimos {activeDays}d até {dateEnd}
          </p>
        </div>
        <div className="bg-background px-6 py-5">
          <p className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">Valor inventário (CMP)</p>
          <p className="mt-2 font-serif text-2xl font-semibold tabular-nums tracking-tight">
            {formatCurrency(inventoryValue)}
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {formatNumber(inventoryUnits)} un · <span className={criticalSkus > 0 ? "text-[#d4b36c]" : ""}>{criticalSkus} críticos</span>
          </p>
        </div>
        <div className="bg-background px-6 py-5">
          <p className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">Estoque catálogo</p>
          <p className="mt-2 font-serif text-2xl font-semibold tabular-nums tracking-tight">
            {formatNumber(stockUnits)}
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {formatNumber(uniqueCustomers)} clientes únicos no período
          </p>
        </div>
      </section>
    </div>
  );
}

// ============= REVENUE CHART (SVG) =============

function DailyRevenueChart({ rows }: { rows: DashboardDailyRow[] }) {
  if (!rows.length) {
    return <p className="py-12 text-center text-sm text-muted-foreground">Sem vendas no período.</p>;
  }
  const W = 800;
  const H = 220;
  const PAD_X = 8;
  const PAD_TOP = 16;
  const PAD_BOTTOM = 22;

  const series = rows.map((r) => Number(r.revenue) || 0);
  const ma = rows.map((r) => (r.revenue_ma7 != null ? Number(r.revenue_ma7) : null));
  const max = Math.max(...series, ...ma.filter((x): x is number => typeof x === "number" && Number.isFinite(x)), 1);
  const innerH = H - PAD_TOP - PAD_BOTTOM;
  const stepX = (W - PAD_X * 2) / Math.max(1, rows.length - 1);

  const xy = (i: number, v: number | null) =>
    v == null ? null : [PAD_X + i * stepX, PAD_TOP + innerH - (v / max) * innerH] as const;

  const linePath = (vals: (number | null)[]) => {
    let started = false;
    let d = "";
    vals.forEach((v, i) => {
      const p = xy(i, v);
      if (!p) return;
      d += `${started ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)} `;
      started = true;
    });
    return d.trim();
  };

  const areaPath = (vals: number[]) => {
    if (!vals.length) return "";
    const pts = vals.map((v, i) => xy(i, v)!);
    const top = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    const last = pts[pts.length - 1][0];
    return `${top} L${last.toFixed(1)},${(PAD_TOP + innerH).toFixed(1)} L${PAD_X.toFixed(1)},${(PAD_TOP + innerH).toFixed(1)} Z`;
  };

  const peak = rows.reduce((acc, r) => (r.revenue > acc.revenue ? r : acc), rows[0]);
  const total = series.reduce((a, b) => a + b, 0);
  const avgPerDay = total / rows.length;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <p className="font-serif text-3xl font-semibold tabular-nums tracking-tight">
          {formatCurrency(total)}
        </p>
        <dl className="grid grid-cols-2 gap-x-6 text-right text-xs">
          <div>
            <dt className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Pico</dt>
            <dd className="mt-0.5 tabular-nums text-foreground">{formatCurrency(peak.revenue)}</dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Média/dia</dt>
            <dd className="mt-0.5 tabular-nums text-foreground">{formatCurrency(avgPerDay)}</dd>
          </div>
        </dl>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="h-[220px] w-full"
        role="img"
        aria-label="Receita diária com média móvel 7d"
      >
        <defs>
          <linearGradient id="rev-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#c7a35b" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#c7a35b" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* gridlines */}
        {[0.25, 0.5, 0.75].map((p) => {
          const y = PAD_TOP + innerH * p;
          return (
            <line key={p} x1={PAD_X} x2={W - PAD_X} y1={y} y2={y} stroke="currentColor" strokeOpacity="0.06" strokeDasharray="2 4" />
          );
        })}
        {/* fill */}
        <path d={areaPath(series)} fill="url(#rev-fill)" />
        {/* MM7 (server) */}
        <path d={linePath(ma)} fill="none" stroke="currentColor" strokeOpacity="0.4" strokeWidth="1" strokeDasharray="3 3" />
        {/* revenue */}
        <path d={linePath(series)} fill="none" stroke="#c7a35b" strokeWidth="1.75" strokeLinejoin="round" strokeLinecap="round" />
        {/* dots */}
        {rows.map((r, i) => {
          const p = xy(i, r.revenue);
          if (!p) return null;
          const isPeak = r.day === peak.day;
          return (
            <circle key={r.day} cx={p[0]} cy={p[1]} r={isPeak ? 3.5 : 1.5} fill={isPeak ? "#c7a35b" : "currentColor"} fillOpacity={isPeak ? 1 : 0.35} />
          );
        })}
        {/* x labels */}
        <text x={PAD_X} y={H - 4} fill="currentColor" fillOpacity="0.45" fontSize="10">{rows[0]?.day.slice(5)}</text>
        <text x={W / 2} y={H - 4} textAnchor="middle" fill="currentColor" fillOpacity="0.45" fontSize="10">
          {rows[Math.floor(rows.length / 2)]?.day.slice(5)}
        </text>
        <text x={W - PAD_X} y={H - 4} textAnchor="end" fill="currentColor" fillOpacity="0.45" fontSize="10">{rows[rows.length - 1]?.day.slice(5)}</text>
      </svg>

      <div className="mt-3 flex flex-wrap items-center gap-4 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5"><span className="h-px w-5 bg-[#c7a35b]" /> Receita diária</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-px w-5 border-t border-dashed border-current opacity-40" /> MM7</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-2 w-2 rounded-full bg-[#c7a35b]" /> Pico</span>
      </div>
    </div>
  );
}

// ============= PAYMENT =============

function PaymentBreakdownChart({ rows }: { rows: { payment_method: string; revenue: number; n_sales: number }[] }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">Sem dados.</p>;
  const max = Math.max(...rows.map((r) => r.revenue), 1);
  return (
    <ul className="space-y-3.5">
      {rows.map((row) => (
        <li key={row.payment_method} className="space-y-1.5">
          <div className="flex items-baseline justify-between gap-3 text-xs">
            <span className="truncate text-foreground">{row.payment_method}</span>
            <span className="shrink-0 tabular-nums text-muted-foreground">
              <span className="text-foreground">{formatCurrency(row.revenue)}</span> · {row.n_sales}
            </span>
          </div>
          <div className="h-px w-full bg-muted/40">
            <div className="h-full bg-[#c7a35b]" style={{ width: `${Math.max((row.revenue / max) * 100, 2)}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

// ============= STOCK TURNOVER =============

function StockTurnoverChart({ rows }: { rows: DashboardStockTurnoverRow[] }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">Sem vendas com SKU no período.</p>;
  const ratios = rows.map((r) =>
    r.turnover_ratio != null && Number.isFinite(Number(r.turnover_ratio)) ? Number(r.turnover_ratio) : 0
  );
  const max = Math.max(...ratios, 1e-6);
  return (
    <ol className="max-h-[340px] space-y-3 overflow-y-auto pr-1">
      {rows.map((row, i) => {
        const ratio = row.turnover_ratio != null && Number.isFinite(Number(row.turnover_ratio)) ? Number(row.turnover_ratio) : null;
        const w = ratio != null ? Math.max((ratio / max) * 100, 3) : 6;
        return (
          <li key={row.sku} className="space-y-1.5">
            <div className="flex flex-wrap items-baseline justify-between gap-2 text-xs">
              <span className="flex min-w-0 items-baseline gap-2">
                <span className="text-[10px] tabular-nums text-muted-foreground">{i + 1}.</span>
                <span className="truncate font-mono text-[#d4b36c]" title={row.sku}>
                  {row.sku.length > 36 ? `${row.sku.slice(0, 33)}…` : row.sku}
                </span>
              </span>
              <span className="shrink-0 tabular-nums text-muted-foreground">
                {formatNumber(row.units_sold)} vend · stock {formatNumber(row.stock_on_hand)}
                {ratio != null ? ` · ${ratio.toFixed(2)}×` : ""}
              </span>
            </div>
            <div className="h-px w-full bg-muted/40">
              <div className="h-full bg-emerald-500/70" style={{ width: `${w}%` }} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// ============= MARGIN BY SKU =============

function MarginSkuChart({ rows }: { rows: DashboardMarginSkuRow[] }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">Sem SKUs no período.</p>;
  const max = Math.max(...rows.map((r) => r.margin_pct), 1);
  const lowCount = rows.filter((r) => r.margin_pct < 15).length;
  return (
    <div className="space-y-3.5">
      {rows.map((row) => (
        <div key={row.sku} className="space-y-1.5">
          <div className="flex items-baseline justify-between gap-2 text-xs">
            <span className="truncate font-mono text-[#d4b36c]" title={row.sku}>
              {row.sku.length > 32 ? `${row.sku.slice(0, 29)}…` : row.sku}
            </span>
            <span className={`shrink-0 tabular-nums ${row.margin_pct < 15 ? "text-destructive" : "text-foreground"}`}>
              {formatPercent(row.margin_pct)}
            </span>
          </div>
          <div className="h-px w-full bg-muted/40">
            <div
              className={`h-full ${row.margin_pct < 15 ? "bg-destructive/70" : "bg-[#c7a35b]"}`}
              style={{ width: `${Math.max((row.margin_pct / max) * 100, 3)}%` }}
            />
          </div>
        </div>
      ))}
      {lowCount > 0 ? (
        <p className="border-t border-border/30 pt-3 text-[11px] text-destructive/90">
          {lowCount} SKU(s) com margem &lt; 15% — rever preço ou custo.
        </p>
      ) : null}
    </div>
  );
}

// ============= COHORT =============

function CohortChart({ rows }: { rows: { cohort_month: string; n_customers: number }[] }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">Sem histórico.</p>;
  const max = Math.max(...rows.map((r) => r.n_customers), 1);
  return (
    <ol className="max-h-[280px] space-y-2.5 overflow-y-auto pr-1">
      {rows.map((row) => (
        <li key={row.cohort_month} className="space-y-1.5">
          <div className="flex items-baseline justify-between gap-2 text-xs">
            <span className="font-mono text-muted-foreground">{row.cohort_month}</span>
            <span className="tabular-nums text-foreground">{row.n_customers}</span>
          </div>
          <div className="h-px w-full bg-muted/40">
            <div className="h-full bg-foreground/40" style={{ width: `${Math.max((row.n_customers / max) * 100, 3)}%` }} />
          </div>
        </li>
      ))}
    </ol>
  );
}

// ============= AGING =============

function StockAgingTable({
  rows,
}: {
  rows: { sku: string; total_stock: number; last_sale_day?: string | null; days_since_sale?: number | null }[];
}) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">Nenhum SKU neste critério.</p>;
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="[&_th]:text-[10px] [&_th]:uppercase [&_th]:tracking-[0.16em] [&_th]:text-muted-foreground">
            <TableHead>SKU</TableHead>
            <TableHead className="text-right">Stock</TableHead>
            <TableHead className="text-right">Dias s/ venda</TableHead>
            <TableHead>Última venda</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => {
            const days = r.days_since_sale != null && !Number.isNaN(Number(r.days_since_sale))
              ? Math.floor(Number(r.days_since_sale))
              : null;
            return (
              <TableRow key={r.sku} className="border-b-border/30">
                <TableCell className="max-w-[200px] truncate font-mono text-xs text-[#d4b36c]">{r.sku}</TableCell>
                <TableCell className="text-right tabular-nums">{formatNumber(r.total_stock)}</TableCell>
                <TableCell className={`text-right tabular-nums ${days != null && days > 90 ? "text-destructive" : "text-muted-foreground"}`}>
                  {days != null ? formatNumber(days) : "—"}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">{r.last_sale_day || "—"}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

// ============= LOW STOCK =============

function LowStockTable({ rows }: { rows: import("@/lib/dashboard-api").DashboardLowStockRow[] }) {
  if (!rows.length) return <p className="text-sm text-emerald-300/70">Nenhum produto abaixo do limiar.</p>;
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="[&_th]:text-[10px] [&_th]:uppercase [&_th]:tracking-[0.16em] [&_th]:text-muted-foreground">
            <TableHead>Prio.</TableHead>
            <TableHead>SKU</TableHead>
            <TableHead>Nome</TableHead>
            <TableHead className="text-right">Stock</TableHead>
            <TableHead className="text-right">CMP</TableHead>
            <TableHead className="text-right">Preço</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.id} className="border-b-border/30">
              <TableCell>
                <Badge
                  variant={r.priority === "critical" ? "outline" : "secondary"}
                  className={r.priority === "critical" ? "border-destructive/50 text-[10px] text-destructive" : "text-[10px]"}
                >
                  {r.priority === "critical" ? "Crítico" : "Baixo"}
                </Badge>
              </TableCell>
              <TableCell className="font-mono text-xs text-[#d4b36c]">{r.sku || "—"}</TableCell>
              <TableCell className="max-w-[160px] truncate text-xs">{r.name}</TableCell>
              <TableCell className={`text-right tabular-nums ${r.stock <= 0 ? "text-destructive" : "text-[#d4b36c]"}`}>
                {formatNumber(r.stock)}
              </TableCell>
              <TableCell className="text-right text-xs tabular-nums text-muted-foreground">
                {formatCurrency(r.unit_cost)}
              </TableCell>
              <TableCell className="text-right text-xs tabular-nums">{formatCurrency(r.sell_price)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// ============= TOP BREAKDOWNS =============

function SkuBreakdownChart({ rows }: { rows: DashboardSkuBreakdown[] }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">Sem SKUs no período.</p>;
  const max = Math.max(...rows.map((r) => r.revenue), 1);
  return (
    <ol className="space-y-3">
      {rows.map((row, i) => (
        <li key={row.sku} className="space-y-1.5">
          <div className="flex items-baseline justify-between gap-2">
            <div className="flex min-w-0 items-baseline gap-2">
              <span className="text-[10px] tabular-nums text-muted-foreground">{i + 1}.</span>
              <span className="truncate font-mono text-xs text-[#d4b36c]" title={row.sku}>
                {row.sku.length > 28 ? `${row.sku.slice(0, 25)}…` : row.sku}
              </span>
            </div>
            <span className="shrink-0 text-xs tabular-nums text-foreground">{formatCurrency(row.revenue)}</span>
          </div>
          <div className="h-px w-full bg-muted/40">
            <div className="h-full bg-[#c7a35b]" style={{ width: `${Math.max((row.revenue / max) * 100, 3)}%` }} />
          </div>
          <p className="text-[11px] text-muted-foreground">{formatNumber(row.qty)} unidades</p>
        </li>
      ))}
    </ol>
  );
}

function ProductBreakdownChart({ rows }: { rows: DashboardProductBreakdown[] }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">Sem produtos.</p>;
  const max = Math.max(...rows.map((r) => r.revenue), 1);
  return (
    <ol className="space-y-3">
      {rows.map((row, i) => (
        <li key={row.product_name} className="space-y-1.5">
          <div className="flex items-baseline justify-between gap-2">
            <span className="line-clamp-2 text-xs font-medium leading-snug text-foreground">
              <span className="mr-1.5 text-[10px] tabular-nums text-muted-foreground">{i + 1}.</span>
              {row.product_name}
            </span>
            <span className="shrink-0 text-xs tabular-nums text-foreground">{formatCurrency(row.revenue)}</span>
          </div>
          <div className="h-px w-full bg-muted/40">
            <div className="h-full bg-[#c7a35b]/90" style={{ width: `${Math.max((row.revenue / max) * 100, 3)}%` }} />
          </div>
        </li>
      ))}
    </ol>
  );
}

function CustomerBreakdownChart({ rows }: { rows: DashboardCustomerBreakdown[] }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">Sem clientes no período.</p>;
  const max = Math.max(...rows.map((r) => r.revenue), 1);
  return (
    <ol className="space-y-3.5">
      {rows.map((row, i) => {
        const share = row.revenue_share_pct != null ? row.revenue_share_pct : 0;
        return (
          <li key={row.customer_id} className="space-y-1.5">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-xs font-medium text-foreground">
                  <span className="text-[10px] tabular-nums text-muted-foreground">{i + 1}. </span>
                  <span className="font-mono text-[#d4b36c]">{row.customer_code}</span>
                </p>
                <p className="truncate text-[11px] text-muted-foreground">
                  {row.customer_name || "—"} · {row.n_orders} pedido(s) · {formatPercent(share)}
                </p>
              </div>
              <span className="shrink-0 text-xs tabular-nums text-foreground">{formatCurrency(row.revenue)}</span>
            </div>
            <div className="h-px w-full bg-muted/40">
              <div className="h-full bg-[#c7a35b]" style={{ width: `${Math.max((row.revenue / max) * 100, 3)}%` }} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// ============= SKELETONS =============

export function DashboardFiltersSkeleton() {
  return <Skeleton className="h-[280px] w-full rounded-2xl" />;
}

export function DashboardDataSkeleton() {
  return (
    <div className="space-y-10">
      <Skeleton className="h-3 w-64" />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-36 rounded-2xl" />
      <Skeleton className="h-24 rounded-2xl" />
      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <Skeleton className="h-[360px] rounded-2xl" />
        <Skeleton className="h-[360px] rounded-2xl" />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-[300px] rounded-2xl" />
        <Skeleton className="h-[300px] rounded-2xl" />
      </div>
      <Skeleton className="h-[280px] rounded-2xl" />
      <div className="grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-[280px] rounded-2xl" />
        <Skeleton className="h-[280px] rounded-2xl" />
      </div>
      <Skeleton className="h-[420px] rounded-2xl" />
    </div>
  );
}
