import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import type { InventoryLotFilterOptions, InventoryLotsTotals } from "@/lib/inventory-api";
import { formatCurrency, formatProductStock } from "@/lib/format";
import type { InventoryLotsQuery } from "@/lib/inventory-url";

function selectedSet(csv: string | undefined) {
  return new Set((csv ?? "").split(",").map((s) => s.trim()).filter(Boolean));
}

function MultiFilterField({
  label,
  name,
  values,
  selectedCsv,
}: {
  label: string;
  name: string;
  values: string[];
  selectedCsv: string | undefined;
}) {
  const selected = selectedSet(selectedCsv);
  // API pode devolver o mesmo valor mais do que uma vez (ex.: custos arredondados); uma opção por valor.
  const shown = [...new Set(values.filter(Boolean))];
  if (!shown.length) {
    return (
      <div className="space-y-1.5">
        <Label className="text-xs font-medium text-muted-foreground">{label}</Label>
        <p className="rounded-md border border-dashed border-border/60 px-2 py-3 text-center text-[11px] text-muted-foreground">
          Sem valores
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      <Label className="text-xs font-medium text-muted-foreground">{label}</Label>
      <div className="max-h-32 overflow-y-auto rounded-md border border-border/60 bg-background/80 p-2 shadow-inner">
        <div className="flex flex-col gap-1.5">
          {shown.map((v) => (
            <label key={`${name}:${v}`} className="flex cursor-pointer items-center gap-2 text-[11px] leading-tight">
              <input
                type="checkbox"
                name={name}
                value={v}
                defaultChecked={selected.has(v)}
                className="h-3.5 w-3.5 shrink-0 rounded border-input accent-[#c7a35b]"
              />
              <span className="min-w-0 truncate" title={v}>
                {v.length > 42 ? `${v.slice(0, 39)}…` : v}
              </span>
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}

export function InventoryFilters({
  options,
  query,
}: {
  options: InventoryLotFilterOptions;
  query: InventoryLotsQuery;
}) {
  const names = options.names ?? [];
  const skus = options.skus ?? [];
  const frame = options.frame_color ?? [];
  const lens = options.lens_color ?? [];
  const gender = options.gender ?? [];
  const style = options.style ?? [];
  const palette = options.palette ?? [];
  const costs = options.costs ?? [];
  const prices = options.prices ?? [];
  const markups = options.markups ?? [];
  const stocks = options.stocks ?? [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Filtros e ordenação</CardTitle>
        <CardDescription>
          Dados via API — apenas lotes com stock &gt; 0. Multiseleção por coluna (valores em CSV na URL). Exclusão em
          lote zera stock e precificação do código de entrada.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form method="get" action="/inventory" className="space-y-5">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-2">
              <Label htmlFor="sort">Ordenar por</Label>
              <Select id="sort" name="sort" defaultValue={query.sort ?? "name"}>
                <option value="sku">SKU (A–Z)</option>
                <option value="name">Nome (A–Z)</option>
                <option value="stock_desc">Stock (maior → menor)</option>
                <option value="stock_asc">Stock (menor → maior)</option>
              </Select>
            </div>
          </div>

          <details className="group rounded-xl border border-border/60 bg-muted/15 open:shadow-sm" open>
            <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium text-foreground marker:text-muted-foreground">
              Filtros por coluna (multiseleção)
            </summary>
            <div className="border-t border-border/50 px-3 pb-4 pt-3">
              <p className="mb-3 text-[11px] text-muted-foreground">
                Marque um ou mais valores por dimensão; deixe vazio para não filtrar nessa coluna.
              </p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                <MultiFilterField label="Nome" name="names" values={names} selectedCsv={query.names} />
                <MultiFilterField label="SKU" name="skus" values={skus} selectedCsv={query.skus} />
                <MultiFilterField
                  label="Cor armação"
                  name="frame_colors"
                  values={frame}
                  selectedCsv={query.frame_colors}
                />
                <MultiFilterField
                  label="Cor lente"
                  name="lens_colors"
                  values={lens}
                  selectedCsv={query.lens_colors}
                />
                <MultiFilterField label="Estilo" name="styles" values={style} selectedCsv={query.styles} />
                <MultiFilterField label="Paleta" name="palettes" values={palette} selectedCsv={query.palettes} />
                <MultiFilterField label="Gênero" name="genders" values={gender} selectedCsv={query.genders} />
                <MultiFilterField label="Custo (unit.)" name="costs" values={costs} selectedCsv={query.costs} />
                <MultiFilterField label="Preço (unit.)" name="prices" values={prices} selectedCsv={query.prices} />
                <MultiFilterField label="Margem (unit.)" name="markups" values={markups} selectedCsv={query.markups} />
                <MultiFilterField label="Stock (lote)" name="stocks" values={stocks} selectedCsv={query.stocks} />
              </div>
            </div>
          </details>

          <div className="flex flex-wrap gap-2">
            <Button type="submit">Aplicar</Button>
            <Button type="button" variant="outline" asChild>
              <Link href="/inventory">Limpar</Link>
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export function InventoryTotalsBar({ totals }: { totals: InventoryLotsTotals }) {
  return (
    <div className="grid grid-cols-2 gap-3 rounded-lg border border-border/60 bg-muted/15 px-4 py-3 text-sm md:grid-cols-4">
      <div>
        <div className="text-xs text-muted-foreground">Stock total (filtrado)</div>
        <div className="font-semibold tabular-nums">{formatProductStock(totals.total_stock)}</div>
      </div>
      <div>
        <div className="text-xs text-muted-foreground">Valor custo (stock × custo)</div>
        <div className="font-semibold tabular-nums">{formatCurrency(totals.total_cost_value)}</div>
      </div>
      <div>
        <div className="text-xs text-muted-foreground">Receita (stock × preço)</div>
        <div className="font-semibold tabular-nums">{formatCurrency(totals.total_revenue_value)}</div>
      </div>
      <div>
        <div className="text-xs text-muted-foreground">Margem (stock × margem)</div>
        <div className="font-semibold tabular-nums">{formatCurrency(totals.total_margin_value)}</div>
      </div>
    </div>
  );
}
