import "server-only";

import { cache } from "react";
import { apiPrototypeFetchRead, readApiError } from "@/lib/api-prototype";
import { inventoryLotsFetchCacheKey, type InventoryLotsQuery } from "@/lib/inventory-url";
import type { ProductBatch } from "@/lib/types";

export type InventoryLotFilterOptions = {
  names: string[];
  skus: string[];
  frame_color: string[];
  lens_color: string[];
  gender: string[];
  palette: string[];
  style: string[];
  costs: string[];
  prices: string[];
  markups: string[];
  stocks: string[];
};

export type InventoryLotRow = {
  product_id: number;
  sku: string | null;
  name: string;
  stock: number;
  product_enter_code: string | null;
  registered_date: string | null;
  frame_color: string | null;
  lens_color: string | null;
  style: string | null;
  palette: string | null;
  gender: string | null;
  cost: number;
  price: number;
  markup: number;
};

export type InventoryLotsTotals = {
  total_stock: number;
  total_cost_value: number;
  total_revenue_value: number;
  total_margin_value: number;
};

export type InventoryLotsResponse = {
  items: InventoryLotRow[];
  total: number;
  page: number;
  page_size: number;
  totals: InventoryLotsTotals;
};

function lotsQueryString(q: InventoryLotsQuery, overrides?: Record<string, string>): string {
  const params = new URLSearchParams();
  const merged: Record<string, string | undefined> = { ...q, ...overrides };
  for (const [k, v] of Object.entries(merged)) {
    if (!v) continue;
    params.set(k, v);
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

async function fetchPrototypeInventoryLotOptionsUncached(): Promise<InventoryLotFilterOptions> {
  const res = await apiPrototypeFetchRead("/inventory/lots/filter-options");
  if (!res.ok) throw new Error(await readApiError(res));
  return (await res.json()) as InventoryLotFilterOptions;
}

export const fetchPrototypeInventoryLotOptions = cache(fetchPrototypeInventoryLotOptionsUncached);

async function fetchPrototypeInventoryLotsUncached(
  cacheKey: string
): Promise<InventoryLotsResponse> {
  const { q, p } = JSON.parse(cacheKey) as {
    q: InventoryLotsQuery;
    p: { page: string; page_size: string };
  };
  const qs = lotsQueryString(q, {
    page: p.page,
    page_size: p.page_size,
  });
  const res = await apiPrototypeFetchRead(`/inventory/lots${qs}`);
  if (!res.ok) throw new Error(await readApiError(res));
  const body = (await res.json()) as InventoryLotsResponse;
  return {
    ...body,
    totals: body.totals ?? {
      total_stock: 0,
      total_cost_value: 0,
      total_revenue_value: 0,
      total_margin_value: 0,
    },
  };
}

const _fetchPrototypeInventoryLotsCached = cache(fetchPrototypeInventoryLotsUncached);

export async function fetchPrototypeInventoryLots(
  q: InventoryLotsQuery,
  paging?: { page?: string; page_size?: string }
): Promise<InventoryLotsResponse> {
  const key = inventoryLotsFetchCacheKey(q, paging);
  return _fetchPrototypeInventoryLotsCached(key);
}

/** In-flight dedupe when the same SKU is requested concurrently (e.g. Strict Mode / double action). */
const _batchesInflight = new Map<string, Promise<ProductBatch[]>>();

/** Lotes com stock > 0 por SKU (usado no fluxo Nova venda). */
export async function fetchPrototypeBatchesForSkuCached(sku: string): Promise<ProductBatch[]> {
  const s = (sku || "").trim();
  if (!s) return [];
  const existing = _batchesInflight.get(s);
  if (existing) return existing;

  const p = (async (): Promise<ProductBatch[]> => {
    const res = await apiPrototypeFetchRead(`/inventory/batches?sku=${encodeURIComponent(s)}`, {
      next: { revalidate: 20 },
    });
    if (!res.ok) return [];
    const data = (await res.json()) as {
      items: Array<{
        id: number;
        name: string;
        stock: number;
        product_enter_code: string | null;
        frame_color: string | null;
        lens_color: string | null;
        style: string | null;
        palette: string | null;
        gender: string | null;
      }>;
    };
    const items = Array.isArray(data.items) ? data.items : [];
    return items.map((row) => ({
      id: row.id,
      name: String(row.name ?? ""),
      stock: Number(row.stock ?? 0),
      productEnterCode: row.product_enter_code ?? null,
      frameColor: row.frame_color ?? null,
      lensColor: row.lens_color ?? null,
      style: row.style ?? null,
      palette: row.palette ?? null,
      gender: row.gender ?? null,
    }));
  })();

  _batchesInflight.set(s, p);
  try {
    return await p;
  } finally {
    _batchesInflight.delete(s);
  }
}
