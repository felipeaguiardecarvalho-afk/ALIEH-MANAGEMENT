import type { fetchCostsSkuMasters, fetchStockCostHistory } from "@/lib/costs-api";
import { formatDate, formatProductMoney } from "@/lib/format";
import { formatQtyDisplay4 } from "../format-qty";

type Masters = Awaited<ReturnType<typeof fetchCostsSkuMasters>>;
type History = Awaited<ReturnType<typeof fetchStockCostHistory>>;

const VALUATION_TOP = 8;
const HISTORY_TOP = 10;

export function ValuationSide({ masters }: { masters: Masters }) {
  const ranked = [...masters]
    .sort(
      (a, b) =>
        (Number(b.total_stock) || 0) * (Number(b.avg_unit_cost) || 0) -
        (Number(a.total_stock) || 0) * (Number(a.avg_unit_cost) || 0)
    )
    .slice(0, VALUATION_TOP);

  return (
    <section className="overflow-hidden rounded-2xl border border-border/60 bg-background">
      <header className="flex items-end justify-between border-b border-border/40 px-5 py-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Valorização</p>
          <p className="mt-1 text-xs text-muted-foreground">Top {VALUATION_TOP} por capital · sku_master</p>
        </div>
        <span className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          {masters.length} SKUs
        </span>
      </header>
      {ranked.length === 0 ? (
        <p className="px-5 py-8 text-center text-xs text-muted-foreground">Sem dados.</p>
      ) : (
        <ul className="divide-y divide-border/30">
          {ranked.map((row) => {
            const stock = Number(row.total_stock) || 0;
            const cmp = Number(row.avg_unit_cost) || 0;
            const cap = stock * cmp;
            const critical = stock <= 5;
            return (
              <li key={row.sku} className="px-5 py-3">
                <div className="flex items-baseline justify-between gap-3">
                  <span
                    className="truncate font-mono text-xs text-[#d4b36c]"
                    title={row.sku}
                  >
                    {row.sku.length > 22 ? `${row.sku.slice(0, 19)}…` : row.sku}
                  </span>
                  <span className="shrink-0 font-mono text-xs tabular-nums text-foreground">
                    {formatProductMoney(cap)}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between text-[11px] tabular-nums text-muted-foreground">
                  <span>
                    <span className={critical ? "text-[#d4b36c]" : ""}>{formatQtyDisplay4(stock)}</span> un
                    <span className="mx-1.5 inline-block h-px w-2 bg-border/60 align-middle" />
                    cmp {formatProductMoney(cmp)}
                  </span>
                  {row.updated_at ? (
                    <span className="text-[10px] text-muted-foreground/70">{formatDate(row.updated_at)}</span>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export function HistorySide({ history }: { history: History }) {
  const top = history.slice(0, HISTORY_TOP);

  return (
    <section className="overflow-hidden rounded-2xl border border-border/60 bg-background">
      <header className="flex items-end justify-between border-b border-border/40 px-5 py-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Histórico</p>
          <p className="mt-1 text-xs text-muted-foreground">Últimas {HISTORY_TOP} entradas · audit log</p>
        </div>
        <span className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          {history.length} no log
        </span>
      </header>
      {top.length === 0 ? (
        <p className="px-5 py-8 text-center text-xs text-muted-foreground">
          Nenhuma entrada de estoque registada ainda.
        </p>
      ) : (
        <ol className="divide-y divide-border/30">
          {top.map((row) => {
            const cmpUp = (Number(row.cmp_after) || 0) - (Number(row.cmp_before) || 0);
            const cmpUpAbs = Math.abs(cmpUp);
            const cmpArrow = cmpUp > 0 ? "↑" : cmpUp < 0 ? "↓" : "·";
            const cmpTone = cmpUp > 0 ? "text-[#d4b36c]" : cmpUp < 0 ? "text-emerald-400" : "text-muted-foreground";
            return (
              <li key={row.id != null ? String(row.id) : `${row.created_at}-${row.sku}`} className="px-5 py-3">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="truncate font-mono text-xs text-[#d4b36c]" title={row.sku}>
                    {row.sku.length > 20 ? `${row.sku.slice(0, 17)}…` : row.sku}
                  </span>
                  <span className="shrink-0 font-mono text-xs tabular-nums text-foreground">
                    +{formatQtyDisplay4(row.quantity)}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between text-[11px] tabular-nums text-muted-foreground">
                  <span>
                    {formatProductMoney(row.total_cost)}
                    <span className="mx-1.5 inline-block h-px w-2 bg-border/60 align-middle" />
                    <span className={cmpTone}>
                      {cmpArrow} cmp {formatProductMoney(cmpUpAbs)}
                    </span>
                  </span>
                  <span className="text-[10px] text-muted-foreground/70">{formatDate(row.created_at)}</span>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
