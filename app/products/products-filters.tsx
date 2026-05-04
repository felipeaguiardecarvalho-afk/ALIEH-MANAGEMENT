"use client";

// Pagination only. Filter UI moved to products-filter-bar.tsx and products-command-header.tsx.
// Kept in this file to preserve existing import path.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { mergeProductCatalogQuery, type ProductCatalogQuery } from "@/lib/products-url";

export function ProductsPaginationBar({
  query,
  total,
  page,
  pageSize,
  view,
}: {
  query: ProductCatalogQuery;
  total: number;
  page: number;
  pageSize: number;
  view?: string;
}) {
  const router = useRouter();
  const base: ProductCatalogQuery = useMemo(() => {
    const b = { ...query };
    delete b.detail;
    return b;
  }, [query]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const prevPage = Math.max(1, page - 1);
  const nextPage = Math.min(totalPages, page + 1);

  const buildHref = (p: number) => {
    let href = `/products${mergeProductCatalogQuery(base, { page: String(p) })}`;
    if (view) href += `${href.includes("?") ? "&" : "?"}view=${encodeURIComponent(view)}`;
    return href;
  };

  const [pageInput, setPageInput] = useState(String(page));
  useEffect(() => setPageInput(String(page)), [page]);

  const goToPage = (raw: string) => {
    const n = Math.min(totalPages, Math.max(1, Math.floor(Number(raw)) || 1));
    router.push(buildHref(n));
    setPageInput(String(n));
  };

  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(total, page * pageSize);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-1 pt-4 text-sm text-muted-foreground">
      <span className="tabular-nums">
        {start}–{end} de <span className="text-foreground">{total}</span>
      </span>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-2">
          <Label htmlFor="catalog-page-jump" className="whitespace-nowrap text-xs">
            Ir
          </Label>
          <Input
            id="catalog-page-jump"
            name="page"
            type="number"
            min={1}
            max={totalPages}
            value={pageInput}
            onChange={(e) => setPageInput(e.target.value)}
            onBlur={() => goToPage(pageInput)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                goToPage(pageInput);
              }
            }}
            className="h-8 w-16 tabular-nums"
          />
          <span className="text-xs">/ {totalPages}</span>
        </div>
        {page > 1 ? (
          <Button type="button" variant="ghost" size="sm" asChild>
            <Link href={buildHref(prevPage)}>← Anterior</Link>
          </Button>
        ) : (
          <Button type="button" variant="ghost" size="sm" disabled>
            ← Anterior
          </Button>
        )}
        {page < totalPages ? (
          <Button type="button" variant="ghost" size="sm" asChild>
            <Link href={buildHref(nextPage)}>Seguinte →</Link>
          </Button>
        ) : (
          <Button type="button" variant="ghost" size="sm" disabled>
            Seguinte →
          </Button>
        )}
      </div>
    </div>
  );
}
