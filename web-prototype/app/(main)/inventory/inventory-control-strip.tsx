"use client";

import Link from "next/link";
import { useState } from "react";
import { Filter, SlidersHorizontal, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import type { InventoryLotFilterOptions } from "@/lib/inventory-api";
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
  const shown = [...new Set(values.filter(Boolean))];
  if (!shown.length) {
    return (
      <div className="space-y-1.5">
        <Label className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{label}</Label>
        <p className="rounded-md border border-dashed border-border/60 px-2 py-3 text-center text-[11px] text-muted-foreground">
          Sem valores
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      <Label className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        {label} <span className="ml-1 normal-case tracking-normal text-muted-foreground/70">({shown.length})</span>
      </Label>
      <div className="max-h-32 overflow-y-auto rounded-md border border-border/60 bg-background/80 p-2">
        <div className="flex flex-col gap-1">
          {shown.map((v) => (
            <label
              key={`${name}:${v}`}
              className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-[11px] leading-tight hover:bg-muted/30"
            >
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

function activeFilterCount(query: InventoryLotsQuery): number {
  const keys: (keyof InventoryLotsQuery)[] = [
    "names",
    "skus",
    "frame_colors",
    "lens_colors",
    "styles",
    "palettes",
    "genders",
    "costs",
    "prices",
    "markups",
    "stocks",
  ];
  return keys.reduce((a, k) => a + (selectedSet(query[k]).size > 0 ? 1 : 0), 0);
}

export function InventoryControlStrip({
  options,
  query,
}: {
  options: InventoryLotFilterOptions;
  query: InventoryLotsQuery;
}) {
  const [open, setOpen] = useState(false);
  const activeDimensions = activeFilterCount(query);
  const anyActive = activeDimensions > 0 || (query.sort && query.sort !== "name");

  return (
    <form method="get" action="/inventory" className="space-y-3">
      {/* Sticky control strip */}
      <div className="sticky top-0 z-20 -mx-1 flex flex-wrap items-center gap-2 rounded-2xl border border-border/60 bg-background/85 px-3 py-2.5 backdrop-blur supports-[backdrop-filter]:bg-background/65">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-3.5 w-3.5 text-muted-foreground" />
          <Label htmlFor="sort" className="sr-only">
            Ordenar por
          </Label>
          <Select
            id="sort"
            name="sort"
            defaultValue={query.sort ?? "name"}
            className="h-9 w-auto min-w-[180px] border-border/60 bg-background text-xs"
          >
            <option value="name">Nome (A–Z)</option>
            <option value="sku">SKU (A–Z)</option>
            <option value="stock_desc">Stock (maior → menor)</option>
            <option value="stock_asc">Stock (menor → maior)</option>
          </Select>
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setOpen((v) => !v)}
          className="h-9 gap-1.5"
          aria-expanded={open}
        >
          <Filter className="h-3.5 w-3.5" />
          Filtros
          {activeDimensions > 0 ? (
            <span className="ml-0.5 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-[#c7a35b] px-1 text-[10px] font-semibold text-black">
              {activeDimensions}
            </span>
          ) : null}
        </Button>

        <Button type="submit" size="sm" variant="luxury" className="h-9">
          Aplicar
        </Button>

        {anyActive ? (
          <Button asChild type="button" variant="ghost" size="sm" className="h-9 text-muted-foreground hover:text-foreground">
            <Link href="/inventory">Limpar tudo</Link>
          </Button>
        ) : null}
      </div>

      {/* Collapsible filter panel */}
      <div
        className={`grid transition-all duration-200 ease-out ${
          open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
        }`}
      >
        <div className="overflow-hidden">
          <div className="rounded-2xl border border-border/60 bg-muted/[0.04] p-5">
            <p className="mb-4 text-[10px] uppercase tracking-[0.24em] text-muted-foreground">
              Multiseleção · marque um ou mais valores por dimensão
            </p>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              <MultiFilterField label="Nome" name="names" values={options.names ?? []} selectedCsv={query.names} />
              <MultiFilterField label="SKU" name="skus" values={options.skus ?? []} selectedCsv={query.skus} />
              <MultiFilterField
                label="Cor armação"
                name="frame_colors"
                values={options.frame_color ?? []}
                selectedCsv={query.frame_colors}
              />
              <MultiFilterField
                label="Cor lente"
                name="lens_colors"
                values={options.lens_color ?? []}
                selectedCsv={query.lens_colors}
              />
              <MultiFilterField label="Estilo" name="styles" values={options.style ?? []} selectedCsv={query.styles} />
              <MultiFilterField label="Paleta" name="palettes" values={options.palette ?? []} selectedCsv={query.palettes} />
              <MultiFilterField label="Gênero" name="genders" values={options.gender ?? []} selectedCsv={query.genders} />
              <MultiFilterField label="Custo (unit.)" name="costs" values={options.costs ?? []} selectedCsv={query.costs} />
              <MultiFilterField label="Preço (unit.)" name="prices" values={options.prices ?? []} selectedCsv={query.prices} />
              <MultiFilterField
                label="Margem (unit.)"
                name="markups"
                values={options.markups ?? []}
                selectedCsv={query.markups}
              />
              <MultiFilterField label="Stock (lote)" name="stocks" values={options.stocks ?? []} selectedCsv={query.stocks} />
            </div>
            <div className="mt-5 flex items-center justify-end gap-2 border-t border-border/40 pt-4">
              <Button asChild type="button" variant="ghost" size="sm">
                <Link href="/inventory">Limpar</Link>
              </Button>
              <Button type="submit" size="sm" variant="luxury">
                Aplicar filtros
              </Button>
            </div>
          </div>
        </div>
      </div>
    </form>
  );
}

// ───────── Active filter pills (separate component to render outside the form) ─────────

const PILL_LABELS: Record<string, string> = {
  names: "Nome",
  skus: "SKU",
  frame_colors: "Armação",
  lens_colors: "Lente",
  styles: "Estilo",
  palettes: "Paleta",
  genders: "Gênero",
  costs: "Custo",
  prices: "Preço",
  markups: "Margem",
  stocks: "Stock",
};

export function InventoryActiveFilters({ query }: { query: InventoryLotsQuery }) {
  const pills: Array<{ key: string; value: string; href: string }> = [];
  const buildHref = (omitKey: string, omitValue: string) => {
    const params = new URLSearchParams();
    for (const [k, vRaw] of Object.entries(query)) {
      if (typeof vRaw !== "string" || vRaw.trim() === "") continue;
      if (k === omitKey) {
        const remaining = vRaw
          .split(",")
          .map((s) => s.trim())
          .filter((s) => s && s !== omitValue);
        if (remaining.length) params.set(k, remaining.join(","));
      } else {
        params.set(k, vRaw);
      }
    }
    const qs = params.toString();
    return qs ? `/inventory?${qs}` : "/inventory";
  };

  for (const k of Object.keys(PILL_LABELS)) {
    const csv = (query as any)[k] as string | undefined;
    if (!csv) continue;
    for (const v of csv.split(",").map((s) => s.trim()).filter(Boolean)) {
      pills.push({ key: k, value: v, href: buildHref(k, v) });
    }
  }

  if (pills.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Filtros ativos</span>
      {pills.map((p) => (
        <Link
          key={`${p.key}:${p.value}`}
          href={p.href}
          className="group inline-flex items-center gap-1 rounded-full border border-border/60 bg-muted/20 px-2.5 py-0.5 text-xs text-foreground transition-colors hover:border-[#c7a35b]/60 hover:bg-[#c7a35b]/10"
        >
          <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            {PILL_LABELS[p.key]}:
          </span>
          <span className="max-w-[160px] truncate">{p.value}</span>
          <X className="h-3 w-3 text-muted-foreground transition-colors group-hover:text-foreground" />
        </Link>
      ))}
      <Link
        href="/inventory"
        className="ml-1 text-xs text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
      >
        Limpar
      </Link>
    </div>
  );
}
