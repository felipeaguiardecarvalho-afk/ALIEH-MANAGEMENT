import type { DailyRevenue } from "@/lib/types";
import { formatCurrency } from "@/lib/format";

const W = 800;
const H = 220;
const PAD_X = 8;
const PAD_TOP = 16;
const PAD_BOTTOM = 22;

function movingAverage(values: number[], window: number) {
  const out: number[] = [];
  for (let i = 0; i < values.length; i++) {
    const start = Math.max(0, i - window + 1);
    const slice = values.slice(start, i + 1);
    out.push(slice.reduce((a, b) => a + b, 0) / slice.length);
  }
  return out;
}

function pathFor(values: number[], max: number) {
  if (values.length === 0) return "";
  const stepX = (W - PAD_X * 2) / Math.max(1, values.length - 1);
  const innerH = H - PAD_TOP - PAD_BOTTOM;
  return values
    .map((v, i) => {
      const x = PAD_X + i * stepX;
      const y = PAD_TOP + innerH - (v / max) * innerH;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function areaFor(values: number[], max: number) {
  if (values.length === 0) return "";
  const stepX = (W - PAD_X * 2) / Math.max(1, values.length - 1);
  const innerH = H - PAD_TOP - PAD_BOTTOM;
  const top = values
    .map((v, i) => {
      const x = PAD_X + i * stepX;
      const y = PAD_TOP + innerH - (v / max) * innerH;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const last = PAD_X + (values.length - 1) * stepX;
  return `${top} L${last.toFixed(1)},${(PAD_TOP + innerH).toFixed(1)} L${PAD_X.toFixed(1)},${(PAD_TOP + innerH).toFixed(1)} Z`;
}

export function RevenueAnalytics({ rows }: { rows: DailyRevenue[] }) {
  const sorted = [...rows].sort((a, b) => a.day.localeCompare(b.day));
  const series = sorted.map((r) => r.revenue);
  const max = Math.max(...series, 1);
  const ma7 = movingAverage(series, 7);

  const half = Math.floor(sorted.length / 2);
  const prev = sorted.slice(0, half).reduce((a, r) => a + r.revenue, 0);
  const curr = sorted.slice(half).reduce((a, r) => a + r.revenue, 0);
  const total = prev + curr;
  const delta = prev > 0 ? ((curr - prev) / prev) * 100 : 0;

  const peak = sorted.reduce((acc, r) => (r.revenue > acc.revenue ? r : acc), sorted[0]);
  const avg = sorted.length > 0 ? total / sorted.length : 0;

  return (
    <section className="rounded-2xl border border-border/60 bg-background">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border/40 px-6 pb-5 pt-6">
        <div>
          <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Receita · 30 dias</p>
          <p className="mt-2 font-serif text-3xl font-semibold tabular-nums tracking-tight">
            {formatCurrency(total)}
          </p>
        </div>
        <dl className="grid grid-cols-3 gap-x-8 gap-y-1 text-right text-xs">
          <div>
            <dt className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">15d vs 15d</dt>
            <dd className={`mt-0.5 font-medium tabular-nums ${delta >= 0 ? "text-[#1F6E4A]" : "text-destructive"}`}>
              {delta >= 0 ? "+" : ""}
              {delta.toFixed(1)}%
            </dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Pico</dt>
            <dd className="mt-0.5 tabular-nums text-foreground">{formatCurrency(peak?.revenue ?? 0)}</dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Média/dia</dt>
            <dd className="mt-0.5 tabular-nums text-foreground">{formatCurrency(avg)}</dd>
          </div>
        </dl>
      </header>

      <div className="px-6 py-6">
        {sorted.length === 0 ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            Sem vendas no período.
          </p>
        ) : (
          <svg
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            className="h-[220px] w-full"
            role="img"
            aria-label="Receita diária"
          >
            <defs>
              <linearGradient id="rev-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#c7a35b" stopOpacity="0.18" />
                <stop offset="100%" stopColor="#c7a35b" stopOpacity="0" />
              </linearGradient>
            </defs>
            {/* gridlines */}
            {[0.25, 0.5, 0.75].map((p) => {
              const y = PAD_TOP + (H - PAD_TOP - PAD_BOTTOM) * p;
              return (
                <line
                  key={p}
                  x1={PAD_X}
                  x2={W - PAD_X}
                  y1={y}
                  y2={y}
                  stroke="currentColor"
                  strokeOpacity="0.06"
                  strokeDasharray="2 4"
                />
              );
            })}
            {/* mid divider (period split) */}
            <line
              x1={W / 2}
              x2={W / 2}
              y1={PAD_TOP}
              y2={H - PAD_BOTTOM}
              stroke="currentColor"
              strokeOpacity="0.08"
              strokeDasharray="3 3"
            />
            {/* fill */}
            <path d={areaFor(series, max)} fill="url(#rev-fill)" />
            {/* moving average */}
            <path
              d={pathFor(ma7, max)}
              fill="none"
              stroke="currentColor"
              strokeOpacity="0.35"
              strokeWidth="1"
              strokeDasharray="3 3"
            />
            {/* revenue line */}
            <path
              d={pathFor(series, max)}
              fill="none"
              stroke="#c7a35b"
              strokeWidth="1.75"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            {/* dots */}
            {sorted.map((r, i) => {
              const stepX = (W - PAD_X * 2) / Math.max(1, sorted.length - 1);
              const x = PAD_X + i * stepX;
              const y = PAD_TOP + (H - PAD_TOP - PAD_BOTTOM) - (r.revenue / max) * (H - PAD_TOP - PAD_BOTTOM);
              const isPeak = peak && r.day === peak.day;
              return (
                <circle
                  key={r.day}
                  cx={x}
                  cy={y}
                  r={isPeak ? 3.5 : 1.5}
                  fill={isPeak ? "#c7a35b" : "currentColor"}
                  fillOpacity={isPeak ? 1 : 0.35}
                />
              );
            })}
            {/* x labels: first / mid / last */}
            <text x={PAD_X} y={H - 4} fill="currentColor" fillOpacity="0.45" fontSize="10">
              {sorted[0]?.day.slice(5)}
            </text>
            <text x={W / 2} y={H - 4} textAnchor="middle" fill="currentColor" fillOpacity="0.45" fontSize="10">
              {sorted[Math.floor(sorted.length / 2)]?.day.slice(5)}
            </text>
            <text x={W - PAD_X} y={H - 4} textAnchor="end" fill="currentColor" fillOpacity="0.45" fontSize="10">
              {sorted[sorted.length - 1]?.day.slice(5)}
            </text>
          </svg>
        )}
        {sorted.length > 0 ? (
          <div className="mt-3 flex flex-wrap items-center gap-4 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-px w-5 bg-[#c7a35b]" /> Receita diária
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-px w-5 border-t border-dashed border-current opacity-40" /> Média móvel 7d
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full bg-[#c7a35b]" /> Pico do período
            </span>
          </div>
        ) : null}
      </div>
    </section>
  );
}
