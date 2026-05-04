"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LayoutGrid, Plus, RefreshCw, Rows3, Search } from "lucide-react";
import { refreshProducts } from "./actions";
import { Button } from "@/components/ui/button";
import { mergeProductCatalogQuery, type ProductCatalogQuery } from "@/lib/products-url";
import { formatProductMoney, formatProductStock } from "@/lib/format";
import type { ProductListRow } from "@/lib/products-api";

const DEBOUNCE_MS = 350;
const LOW_STOCK_THRESHOLD = 5;

export function ProductsCommandHeader({
  query,
  rows,
  total,
  view,
  cadastroAnchorHref,
}: {
  query: ProductCatalogQuery;
  rows: ProductListRow[];
  total: number;
  view: "table" | "gallery";
  cadastroAnchorHref: string;
}) {
  const router = useRouter();
  const baseline = useMemo(() => {
    const b = { ...query };
    delete b.detail;
    return b;
  }, [query]);

  const [q, setQ] = useState(baseline.q ?? "");
  useEffect(() => setQ(baseline.q ?? ""), [baseline.q]);

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const pushQ = useCallback(
    (raw: string) => {
      const next: ProductCatalogQuery = { ...baseline, page: "1" };
      const trimmed = raw.trim();
      if (trimmed) next.q = trimmed;
      else delete next.q;
      delete next.detail;
      router.push(`/products${mergeProductCatalogQuery({}, next as Record<string, string | null>)}`);
    },
    [baseline, router]
  );

  const onChange = (val: string) => {
    setQ(val);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => pushQ(val), DEBOUNCE_MS);
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (timer.current) clearTimeout(timer.current);
    pushQ(q);
  };

  // Inline metrics computed from current page rows
  const stockSum = rows.reduce((a, r) => a + (Number(r.stock) || 0), 0);
  const priceVals = rows.map((r) => Number(r.sell_price)).filter((n) => Number.isFinite(n) && n > 0);
  const avgPrice = priceVals.length ? priceVals.reduce((a, b) => a + b, 0) / priceVals.length : 0;
  const lowStock = rows.filter((r) => {
    const s = Number(r.stock);
    return Number.isFinite(s) && s <= LOW_STOCK_THRESHOLD;
  }).length;

  const setView = (v: "table" | "gallery") => {
    const params = new URLSearchParams();
    Object.entries(baseline).forEach(([k, val]) => {
      if (val && String(val).trim()) params.set(k, String(val).trim());
    });
    if (v === "gallery") params.set("view", "gallery");
    else params.delete("view");
    const qs = params.toString();
    router.push(qs ? `/products?${qs}` : "/products");
  };

  return (
    <header className="space-y-7 pt-2">
      {/* Eyebrow row: breadcrumb + inline metrics + actions */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3 text-[11px] uppercase tracking-[0.32em] text-muted-foreground">
          <span className="text-[#d4b36c]">Catálogo</span>
          <span className="h-px w-6 bg-border/70" />
          <span className="tabular-nums">
            <span className="text-foreground">{total}</span> produtos
          </span>
          <span className="hidden h-px w-6 bg-border/70 md:block" />
          <span className="hidden tabular-nums md:inline">
            estoque <span className="text-foreground">{formatProductStock(stockSum)}</span>
          </span>
          <span className="hidden h-px w-6 bg-border/70 lg:block" />
          <span className="hidden tabular-nums lg:inline">
            preço médio <span className="text-foreground">{formatProductMoney(avgPrice)}</span>
          </span>
          {lowStock > 0 ? (
            <>
              <span className="hidden h-px w-6 bg-border/70 lg:block" />
              <span className="hidden tabular-nums text-[#d4b36c] lg:inline">
                {lowStock} estoque baixo
              </span>
            </>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <form action={refreshProducts}>
            <Button
              type="submit"
              variant="ghost"
              size="sm"
              className="h-9 gap-2 text-muted-foreground hover:text-foreground"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Atualizar</span>
            </Button>
          </form>
          <Button asChild variant="luxury" size="sm" className="h-9 gap-2">
            <Link href={cadastroAnchorHref} prefetch={false}>
              <Plus className="h-3.5 w-3.5" />
              Novo produto
              <kbd className="ml-1 hidden rounded border border-black/20 bg-black/10 px-1.5 py-0.5 text-[10px] font-medium text-black/70 md:inline-block">
                N
              </kbd>
            </Link>
          </Button>
        </div>
      </div>

      {/* Title */}
      <div>
        <h1 className="font-serif text-5xl font-semibold tracking-tight md:text-6xl">Produtos</h1>
      </div>

      {/* Dominant search */}
      <form onSubmit={submit} className="relative">
        <Search className="pointer-events-none absolute left-0 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={q}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Buscar por SKU, nome ou atributo…"
          className="h-14 w-full border-0 border-b border-border/60 bg-transparent pl-9 pr-32 font-serif text-2xl tracking-tight text-foreground caret-[#c7a35b] outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-[#c7a35b]/60 md:text-3xl"
          autoComplete="off"
          spellCheck={false}
        />
        <div className="absolute right-0 top-1/2 flex -translate-y-1/2 items-center gap-2">
          {q ? (
            <button
              type="button"
              onClick={() => { setQ(""); pushQ(""); }}
              className="rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground"
            >
              limpar
            </button>
          ) : null}
          <kbd className="hidden h-6 items-center rounded border border-border/60 bg-muted/30 px-1.5 text-[10px] font-medium text-muted-foreground md:inline-flex">
            ⌘K
          </kbd>
        </div>
      </form>

      {/* View toggle row */}
      <div className="flex items-center justify-between border-b border-border/40 pb-3">
        <div className="inline-flex items-center gap-0.5 rounded-lg border border-border/60 bg-background p-0.5">
          <button
            type="button"
            onClick={() => setView("table")}
            className={`inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-colors ${
              view === "table"
                ? "bg-muted/60 text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Rows3 className="h-3.5 w-3.5" />
            Tabela
          </button>
          <button
            type="button"
            onClick={() => setView("gallery")}
            className={`inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-colors ${
              view === "gallery"
                ? "bg-muted/60 text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <LayoutGrid className="h-3.5 w-3.5" />
            Galeria
          </button>
        </div>
        <p className="text-xs text-muted-foreground tabular-nums">
          {rows.length} de {total} nesta página
        </p>
      </div>
    </header>
  );
}
