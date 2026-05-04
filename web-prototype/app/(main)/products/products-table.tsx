"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowUpRight, Check, Columns3, Package, Rows2, Rows3 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate, formatProductMoney, formatProductStock } from "@/lib/format";
import type { ProductListRow } from "@/lib/products-api";
import { mergeProductCatalogQuery, type ProductCatalogQuery } from "@/lib/products-url";

const ALL_COLS = [
  { key: "id", label: "ID", default: true },
  { key: "sku", label: "SKU", default: true, locked: true },
  { key: "name", label: "Nome", default: true, locked: true },
  { key: "frame_color", label: "Armação", default: true },
  { key: "lens_color", label: "Lente", default: true },
  { key: "gender", label: "Gênero", default: false },
  { key: "palette", label: "Paleta", default: false },
  { key: "style", label: "Estilo", default: true },
  { key: "created_at", label: "Criado", default: false },
  { key: "stock", label: "Estoque", default: true, locked: true },
  { key: "avg_cost", label: "Custo", default: true },
  { key: "sell_price", label: "Preço", default: true, locked: true },
] as const;

type ColKey = (typeof ALL_COLS)[number]["key"];

function dash(v: string | null | undefined) {
  const t = (v ?? "").trim();
  return t || "—";
}

function stockTone(stock: number | string | null | undefined) {
  const n = Number(stock);
  if (!Number.isFinite(n)) return "text-muted-foreground";
  if (n <= 0) return "text-destructive";
  if (n <= 5) return "text-[#d4b36c]";
  return "text-foreground";
}

export function ProductsTable({
  rows,
  listQuery,
  view,
}: {
  rows: ProductListRow[];
  listQuery: ProductCatalogQuery;
  view?: string;
}) {
  const [density, setDensity] = useState<"compact" | "comfortable">("comfortable");
  const [visible, setVisible] = useState<Record<ColKey, boolean>>(() => {
    const o = {} as Record<ColKey, boolean>;
    ALL_COLS.forEach((c) => (o[c.key] = c.default));
    return o;
  });
  const [colsOpen, setColsOpen] = useState(false);

  if (rows.length === 0) return <TableEmpty />;

  const cellY = density === "compact" ? "py-2" : "py-3.5";
  const isVisible = (k: ColKey) => visible[k];

  const detailHref = (id: number) => {
    const base = `/products${mergeProductCatalogQuery(listQuery, { detail: String(id) })}`;
    return view === "gallery"
      ? `${base}${base.includes("?") ? "&" : "?"}view=gallery`
      : base;
  };

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex items-center justify-end gap-2">
        {/* Column visibility */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setColsOpen((v) => !v)}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border/60 bg-background px-2.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            aria-expanded={colsOpen}
          >
            <Columns3 className="h-3.5 w-3.5" />
            Colunas
          </button>
          {colsOpen ? (
            <>
              <button
                type="button"
                aria-hidden
                onClick={() => setColsOpen(false)}
                className="fixed inset-0 z-30"
              />
              <div className="absolute right-0 top-[calc(100%+6px)] z-40 w-56 rounded-xl border border-border/70 bg-background p-1.5 shadow-2xl animate-in fade-in slide-in-from-top-1 duration-150">
                {ALL_COLS.map((c) => {
                  const on = isVisible(c.key);
                  const locked = "locked" in c && !!c.locked;
                  return (
                    <button
                      key={c.key}
                      type="button"
                      disabled={locked}
                      onClick={() => !locked && setVisible((s) => ({ ...s, [c.key]: !s[c.key] }))}
                      className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-xs transition-colors ${
                        locked ? "cursor-default opacity-50" : "hover:bg-muted/40"
                      }`}
                    >
                      <span className="text-foreground">{c.label}</span>
                      {on ? <Check className="h-3.5 w-3.5 text-[#c7a35b]" /> : <span className="h-3.5 w-3.5" />}
                    </button>
                  );
                })}
              </div>
            </>
          ) : null}
        </div>
        {/* Density */}
        <div className="inline-flex items-center gap-0.5 rounded-md border border-border/60 p-0.5">
          <button
            type="button"
            aria-label="Compacto"
            onClick={() => setDensity("compact")}
            className={`inline-flex h-7 w-7 items-center justify-center rounded transition-colors ${
              density === "compact" ? "bg-muted/60 text-foreground" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Rows3 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            aria-label="Confortável"
            onClick={() => setDensity("comfortable")}
            className={`inline-flex h-7 w-7 items-center justify-center rounded transition-colors ${
              density === "comfortable" ? "bg-muted/60 text-foreground" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Rows2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Table — chrome-less, sticky header, hover gold accent */}
      <div className="hidden md:block">
        <div className="max-h-[72vh] overflow-auto">
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
              <tr className="border-b border-border/60 [&>th]:px-3 [&>th]:py-2.5 [&>th]:text-left [&>th]:text-[10px] [&>th]:font-medium [&>th]:uppercase [&>th]:tracking-[0.16em] [&>th]:text-muted-foreground">
                {isVisible("id") && <th className="w-[56px]">ID</th>}
                {isVisible("sku") && <th>SKU</th>}
                {isVisible("name") && <th className="min-w-[200px]">Nome</th>}
                {isVisible("frame_color") && <th>Armação</th>}
                {isVisible("lens_color") && <th>Lente</th>}
                {isVisible("gender") && <th>Gênero</th>}
                {isVisible("palette") && <th>Paleta</th>}
                {isVisible("style") && <th>Estilo</th>}
                {isVisible("created_at") && <th>Criado</th>}
                {isVisible("stock") && <th className="text-right">Estoque</th>}
                {isVisible("avg_cost") && <th className="text-right">Custo</th>}
                {isVisible("sell_price") && <th className="text-right">Preço</th>}
                <th className="w-[56px]" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const href = detailHref(row.id);
                return (
                  <tr
                    key={row.id}
                    className="group relative cursor-pointer border-b border-border/30 transition-colors duration-150 hover:bg-[#c7a35b]/[0.05]"
                  >
                    {isVisible("id") && (
                      <td className={`px-3 ${cellY} text-xs tabular-nums text-muted-foreground`}>{row.id}</td>
                    )}
                    {isVisible("sku") && (
                      <td className={`px-3 ${cellY}`}>
                        <Badge variant="gold">{row.sku?.trim() || "—"}</Badge>
                      </td>
                    )}
                    {isVisible("name") && (
                      <td className={`px-3 ${cellY}`}>
                        <Link
                          href={href}
                          className="block max-w-[280px] truncate font-medium text-foreground after:absolute after:inset-0 after:content-['']"
                        >
                          {dash(row.name)}
                        </Link>
                      </td>
                    )}
                    {isVisible("frame_color") && <td className={`px-3 ${cellY} text-muted-foreground`}>{dash(row.frame_color)}</td>}
                    {isVisible("lens_color") && <td className={`px-3 ${cellY} text-muted-foreground`}>{dash(row.lens_color)}</td>}
                    {isVisible("gender") && <td className={`px-3 ${cellY} text-muted-foreground`}>{dash(row.gender)}</td>}
                    {isVisible("palette") && <td className={`px-3 ${cellY} text-muted-foreground`}>{dash(row.palette)}</td>}
                    {isVisible("style") && <td className={`px-3 ${cellY} text-muted-foreground`}>{dash(row.style)}</td>}
                    {isVisible("created_at") && (
                      <td className={`px-3 ${cellY} whitespace-nowrap text-xs text-muted-foreground`}>
                        {formatDate(row.created_at)}
                      </td>
                    )}
                    {isVisible("stock") && (
                      <td className={`px-3 ${cellY} text-right tabular-nums ${stockTone(row.stock)}`}>
                        {formatProductStock(row.stock)}
                      </td>
                    )}
                    {isVisible("avg_cost") && (
                      <td className={`px-3 ${cellY} text-right tabular-nums text-muted-foreground`}>
                        {formatProductMoney(row.avg_cost)}
                      </td>
                    )}
                    {isVisible("sell_price") && (
                      <td className={`px-3 ${cellY} text-right tabular-nums font-medium`}>
                        {formatProductMoney(row.sell_price)}
                      </td>
                    )}
                    <td className={`px-3 ${cellY}`}>
                      <span className="relative z-10 inline-flex h-6 w-6 translate-x-1 items-center justify-center rounded-full text-muted-foreground opacity-0 transition-all duration-150 group-hover:translate-x-0 group-hover:opacity-100">
                        <ArrowUpRight className="h-3.5 w-3.5" />
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Mobile cards */}
      <div className="space-y-2 md:hidden">
        {rows.map((row) => {
          const href = detailHref(row.id);
          return (
            <Link
              key={row.id}
              href={href}
              className="block rounded-xl border border-border/60 bg-background p-4 transition-colors active:bg-muted/40"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="gold">{row.sku?.trim() || "—"}</Badge>
                    <span className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                      #{row.id}
                    </span>
                  </div>
                  <p className="truncate font-serif text-base font-medium tracking-tight">{dash(row.name)}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {[row.frame_color, row.lens_color, row.style].filter(Boolean).join(" · ") || "—"}
                  </p>
                </div>
                <ArrowUpRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 border-t border-border/40 pt-3">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Estoque</p>
                  <p className={`mt-0.5 text-sm font-semibold tabular-nums ${stockTone(row.stock)}`}>
                    {formatProductStock(row.stock)}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Custo</p>
                  <p className="mt-0.5 text-sm tabular-nums text-muted-foreground">
                    {formatProductMoney(row.avg_cost)}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Preço</p>
                  <p className="mt-0.5 text-sm font-semibold tabular-nums">
                    {formatProductMoney(row.sell_price)}
                  </p>
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

function TableEmpty() {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-20 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full border border-border/60 bg-background">
        <Package className="h-6 w-6 text-muted-foreground" strokeWidth={1.4} />
      </div>
      <p className="mt-5 font-serif text-2xl tracking-tight text-foreground">Nenhum produto encontrado</p>
      <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">
        Ajuste a busca ou os filtros, ou cadastre um novo lote.
      </p>
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        <Button asChild variant="luxury">
          <Link href="#cadastro-produto">Cadastrar produto</Link>
        </Button>
        <Button asChild variant="ghost">
          <Link href="/products">Limpar filtros</Link>
        </Button>
      </div>
    </div>
  );
}
