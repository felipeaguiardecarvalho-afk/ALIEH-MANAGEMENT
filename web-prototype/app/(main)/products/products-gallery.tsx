import Link from "next/link";
import { ArrowUpRight, Package } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatProductMoney, formatProductStock } from "@/lib/format";
import type { ProductListRow } from "@/lib/products-api";
import { mergeProductCatalogQuery, type ProductCatalogQuery } from "@/lib/products-url";

function stockTone(stock: number | string | null | undefined) {
  const n = Number(stock);
  if (!Number.isFinite(n)) return "text-muted-foreground";
  if (n <= 0) return "text-destructive";
  if (n <= 5) return "text-[#d4b36c]";
  return "text-foreground";
}

function monogram(sku: string | null | undefined, name: string) {
  const s = (sku ?? "").trim();
  if (s) return s.split("-")[0]?.slice(0, 4).toUpperCase() || s.slice(0, 4).toUpperCase();
  const w = name.trim().split(/\s+/);
  return ((w[0]?.[0] ?? "") + (w[1]?.[0] ?? "")).toUpperCase() || "—";
}

export function ProductsGallery({
  rows,
  listQuery,
  view,
}: {
  rows: ProductListRow[];
  listQuery: ProductCatalogQuery;
  view?: string;
}) {
  if (rows.length === 0) return <GalleryEmpty />;

  return (
    <div className="grid grid-cols-1 gap-px overflow-hidden rounded-xl border border-border/60 bg-border/60 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {rows.map((row) => {
        const baseHref = `/products${mergeProductCatalogQuery(listQuery, { detail: String(row.id) })}`;
        const href = view === "gallery"
          ? `${baseHref}${baseHref.includes("?") ? "&" : "?"}view=gallery`
          : baseHref;
        const sku = row.sku?.trim() || "—";
        const attrs = [row.frame_color, row.lens_color, row.style, row.gender, row.palette]
          .filter(Boolean)
          .slice(0, 3) as string[];
        return (
          <Link
            key={row.id}
            href={href}
            className="group relative flex flex-col bg-background transition-colors duration-200 hover:bg-muted/[0.04]"
          >
            {/* Visual */}
            <div className="relative aspect-[4/3] overflow-hidden bg-gradient-to-br from-muted/30 via-background to-muted/10">
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="font-serif text-5xl font-semibold tracking-tight text-foreground/15 transition-all duration-300 group-hover:scale-105 group-hover:text-foreground/25">
                  {monogram(row.sku, row.name)}
                </span>
              </div>
              {/* Stock pill top-left */}
              <div className="absolute left-3 top-3">
                <span className={`inline-flex items-center gap-1 rounded-full bg-background/85 px-2 py-0.5 text-[10px] font-medium tabular-nums backdrop-blur ${stockTone(row.stock)}`}>
                  <span className="h-1 w-1 rounded-full bg-current" />
                  {formatProductStock(row.stock)}
                </span>
              </div>
              {/* Hover action */}
              <div className="absolute right-3 top-3 translate-y-1 opacity-0 transition-all duration-200 group-hover:translate-y-0 group-hover:opacity-100">
                <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-background/90 text-foreground shadow-sm backdrop-blur">
                  <ArrowUpRight className="h-3.5 w-3.5" />
                </span>
              </div>
            </div>

            {/* Info */}
            <div className="flex flex-1 flex-col gap-2 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <Badge variant="gold" className="mb-1.5">{sku}</Badge>
                  <p className="line-clamp-2 font-serif text-[15px] font-medium leading-tight tracking-tight text-foreground">
                    {row.name?.trim() || "—"}
                  </p>
                </div>
              </div>

              {attrs.length > 0 ? (
                <p className="line-clamp-1 text-[11px] text-muted-foreground">
                  {attrs.join(" · ")}
                </p>
              ) : null}

              <div className="mt-auto flex items-end justify-between border-t border-border/30 pt-3">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Preço</p>
                  <p className="font-serif text-lg font-semibold tabular-nums">
                    {formatProductMoney(row.sell_price)}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Custo</p>
                  <p className="text-sm tabular-nums text-muted-foreground">
                    {formatProductMoney(row.avg_cost)}
                  </p>
                </div>
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}

function GalleryEmpty() {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border/60 bg-muted/10 px-6 py-20 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full border border-border/60 bg-background">
        <Package className="h-6 w-6 text-muted-foreground" strokeWidth={1.4} />
      </div>
      <p className="mt-5 font-serif text-2xl tracking-tight text-foreground">Nenhum produto encontrado</p>
      <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">
        Ajuste a busca ou os filtros, ou cadastre um novo lote para começar.
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
