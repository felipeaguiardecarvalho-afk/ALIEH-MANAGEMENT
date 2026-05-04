"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Filter, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import type { ProductAttributeOptions } from "@/lib/products-api";
import { mergeProductCatalogQuery, type ProductCatalogQuery } from "@/lib/products-url";

const DEBOUNCE_MS = 350;

type AttrKey = "frame_color" | "lens_color" | "gender" | "palette" | "style";

const ATTR_LABEL: Record<AttrKey, string> = {
  frame_color: "Armação",
  lens_color: "Lente",
  gender: "Gênero",
  palette: "Paleta",
  style: "Estilo",
};

function buildHref(next: ProductCatalogQuery, view?: string): string {
  const patch: Record<string, string | null | undefined> = {};
  for (const [k, v] of Object.entries(next)) {
    if (v === undefined || v === null || String(v).trim() === "") patch[k] = null;
    else patch[k] = String(v).trim();
  }
  delete patch.detail;
  const base = `/products${mergeProductCatalogQuery({}, patch)}`;
  if (!view) return base;
  // Append view if present
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}view=${encodeURIComponent(view)}`;
}

export function ProductsFilterBar({
  options,
  query,
  view,
}: {
  options: ProductAttributeOptions;
  query: ProductCatalogQuery;
  view?: string;
}) {
  const router = useRouter();
  const baseline = useMemo(() => {
    const b = { ...query };
    delete b.detail;
    return b;
  }, [query]);

  const [sort, setSort] = useState(baseline.sort ?? "sku");
  const [pageSize, setPageSize] = useState(baseline.page_size ?? "100");
  const [frame_color, setFrame] = useState(baseline.frame_color ?? "");
  const [lens_color, setLens] = useState(baseline.lens_color ?? "");
  const [gender, setGender] = useState(baseline.gender ?? "");
  const [palette, setPalette] = useState(baseline.palette ?? "");
  const [style, setStyle] = useState(baseline.style ?? "");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setSort(baseline.sort ?? "sku");
    setPageSize(baseline.page_size ?? "100");
    setFrame(baseline.frame_color ?? "");
    setLens(baseline.lens_color ?? "");
    setGender(baseline.gender ?? "");
    setPalette(baseline.palette ?? "");
    setStyle(baseline.style ?? "");
  }, [baseline]);

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const push = useCallback(
    (override?: Partial<Record<AttrKey | "sort" | "page_size", string>>) => {
      const next: ProductCatalogQuery = { ...baseline };
      const merged = {
        sort,
        page_size: pageSize,
        frame_color,
        lens_color,
        gender,
        palette,
        style,
        ...override,
      };
      Object.entries(merged).forEach(([k, v]) => {
        if (v && String(v).trim()) (next as any)[k] = String(v).trim();
        else delete (next as any)[k];
      });
      next.page = "1";
      delete next.detail;
      router.push(buildHref(next, view));
    },
    [baseline, sort, pageSize, frame_color, lens_color, gender, palette, style, router, view]
  );

  const schedule = useCallback(
    (override?: Partial<Record<AttrKey | "sort" | "page_size", string>>) => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => push(override), DEBOUNCE_MS);
    },
    [push]
  );

  const clearAttr = (k: AttrKey) => {
    const setters: Record<AttrKey, (v: string) => void> = {
      frame_color: setFrame, lens_color: setLens, gender: setGender, palette: setPalette, style: setStyle,
    };
    setters[k]("");
    push({ [k]: "" });
  };

  type Pill = { key: AttrKey | "q"; label: string; clear: () => void };
  const pills: Pill[] = [];
  if (baseline.q?.trim()) {
    pills.push({
      key: "q",
      label: `“${baseline.q.trim()}”`,
      clear: () => {
        const next = { ...baseline };
        delete (next as any).q;
        next.page = "1";
        router.push(buildHref(next, view));
      },
    });
  }
  (Object.keys(ATTR_LABEL) as AttrKey[]).forEach((k) => {
    const v =
      k === "frame_color" ? frame_color :
      k === "lens_color" ? lens_color :
      k === "gender" ? gender :
      k === "palette" ? palette : style;
    if (v) pills.push({ key: k, label: `${ATTR_LABEL[k]}: ${v}`, clear: () => clearAttr(k) });
  });

  const activeCount = pills.length - (baseline.q?.trim() ? 1 : 0);

  const clearAllHref = view ? `/products?view=${encodeURIComponent(view)}` : "/products";

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Filter popover */}
      <div className="relative">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setOpen((v) => !v)}
          className="h-8 gap-1.5"
          aria-expanded={open}
        >
          <Filter className="h-3.5 w-3.5" />
          Filtros
          {activeCount > 0 ? (
            <span className="ml-0.5 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-[#c7a35b] px-1 text-[10px] font-semibold text-black">
              {activeCount}
            </span>
          ) : null}
        </Button>
        {open ? (
          <>
            <button
              type="button"
              aria-hidden
              onClick={() => setOpen(false)}
              className="fixed inset-0 z-30"
            />
            <div className="absolute left-0 top-[calc(100%+6px)] z-40 w-[min(92vw,520px)] origin-top-left rounded-xl border border-border/70 bg-background p-4 shadow-2xl animate-in fade-in slide-in-from-top-1 duration-150">
              <p className="mb-3 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                Atributos
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <FieldSelect label="Armação"  values={options.frame_color}  value={frame_color}  onChange={(v) => { setFrame(v); schedule({ frame_color: v }); }} />
                <FieldSelect label="Lente"    values={options.lens_color}   value={lens_color}   onChange={(v) => { setLens(v); schedule({ lens_color: v }); }} />
                <FieldSelect label="Gênero"   values={options.gender}       value={gender}       onChange={(v) => { setGender(v); schedule({ gender: v }); }} />
                <FieldSelect label="Paleta"   values={options.palette}      value={palette}      onChange={(v) => { setPalette(v); schedule({ palette: v }); }} />
                <FieldSelect label="Estilo"   values={options.style}        value={style}        onChange={(v) => { setStyle(v); schedule({ style: v }); }} />
              </div>
              <div className="mt-4 flex items-center justify-between border-t border-border/50 pt-3">
                <Link
                  href={clearAllHref}
                  className="text-xs text-muted-foreground transition-colors hover:text-foreground"
                >
                  Limpar tudo
                </Link>
                <Button type="button" size="sm" variant="luxury" className="h-8" onClick={() => { push(); setOpen(false); }}>
                  Aplicar
                </Button>
              </div>
            </div>
          </>
        ) : null}
      </div>

      {/* Sort + page size — inline minimal */}
      <Select
        value={sort}
        onChange={(e) => { setSort(e.target.value); schedule({ sort: e.target.value }); }}
        className="h-8 w-auto min-w-[140px] border-border/60 bg-background text-xs"
      >
        <option value="sku">SKU (A–Z)</option>
        <option value="name">Nome (A–Z)</option>
        <option value="stock_desc">Estoque ↓</option>
        <option value="stock_asc">Estoque ↑</option>
      </Select>
      <Select
        value={pageSize}
        onChange={(e) => { setPageSize(e.target.value); schedule({ page_size: e.target.value }); }}
        className="h-8 w-auto min-w-[88px] border-border/60 bg-background text-xs"
      >
        <option value="25">25 / pág.</option>
        <option value="50">50 / pág.</option>
        <option value="100">100 / pág.</option>
        <option value="200">200 / pág.</option>
      </Select>

      {/* Pills */}
      {pills.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="h-5 w-px bg-border/70" />
          {pills.map((p) => (
            <button
              key={p.key}
              type="button"
              onClick={p.clear}
              className="group inline-flex items-center gap-1 rounded-full border border-border/60 bg-muted/20 px-2.5 py-0.5 text-xs text-foreground transition-all duration-150 hover:border-[#c7a35b]/60 hover:bg-[#c7a35b]/10"
            >
              {p.label}
              <X className="h-3 w-3 text-muted-foreground transition-colors group-hover:text-foreground" />
            </button>
          ))}
          <Link
            href={clearAllHref}
            className="ml-1 text-xs text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
          >
            Limpar
          </Link>
        </div>
      ) : null}
    </div>
  );
}

function FieldSelect({
  label,
  values,
  value,
  onChange,
}: {
  label: string;
  values: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{label}</Label>
      <Select value={value} onChange={(e) => onChange(e.target.value)} className="h-9">
        <option value="">Todos</option>
        {values.filter(Boolean).map((v) => (
          <option key={v} value={v}>
            {v.length > 56 ? `${v.slice(0, 53)}…` : v}
          </option>
        ))}
      </Select>
    </div>
  );
}
