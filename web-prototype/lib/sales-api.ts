import "server-only";

import { cache } from "react";
import { apiPrototypeFetchRead, readApiError } from "@/lib/api-prototype";
import type { SaleableSku } from "@/lib/types";

/** Limite fixo na página Vendas do Streamlit (últimas vendas). */
export const STREAMLIT_RECENT_SALES_LIMIT = 20;

/**
 * Linha de `GET /sales/recent` (`get_recent_sales_rows`).
 * Campos `product_name`, `unit_price`, `discount_amount` vêm da API mesmo quando a UI
 * de `/sales` não os mostra — mantêm paridade de dados com o Streamlit.
 */
export type RecentSaleRow = {
  sale_code?: string | null;
  id: number;
  product_name?: string | null;
  sku?: string | null;
  customer_label?: string | null;
  quantity?: number;
  unit_price?: number;
  discount_amount?: number;
  total?: number;
  /** ISO 8601 do servidor (mesmo formato que na inserção da venda). */
  sold_at?: string | null;
  payment_method?: string | null;
};

export type RecentSalesResponse = {
  items: RecentSaleRow[];
};

function normalizeRecentSalesLimit(limit?: number): number {
  return Math.min(500, Math.max(1, Math.floor(limit ?? STREAMLIT_RECENT_SALES_LIMIT)));
}

async function fetchPrototypeRecentSalesUncached(lim: number): Promise<RecentSalesResponse> {
  const res = await apiPrototypeFetchRead(`/sales/recent?limit=${lim}`);
  if (!res.ok) {
    throw new Error(await readApiError(res));
  }
  let body: RecentSalesResponse;
  try {
    body = (await res.json()) as RecentSalesResponse;
  } catch {
    throw new Error("Resposta inválida da API de vendas recentes (não é JSON).");
  }
  return { items: Array.isArray(body.items) ? body.items : [] };
}

const _fetchPrototypeRecentSalesCached = cache(fetchPrototypeRecentSalesUncached);

export async function fetchPrototypeRecentSales(
  limit?: number
): Promise<RecentSalesResponse> {
  return _fetchPrototypeRecentSalesCached(normalizeRecentSalesLimit(limit));
}

type SaleableSkuApiRow = {
  sku: string;
  selling_price: number;
  total_stock: number;
  sample_name: string | null;
};

async function fetchPrototypeSaleableSkusUncached(): Promise<SaleableSku[]> {
  const res = await apiPrototypeFetchRead("/sales/saleable-skus");
  if (!res.ok) {
    throw new Error(await readApiError(res));
  }
  const body = (await res.json()) as { items: SaleableSkuApiRow[] };
  const items = Array.isArray(body.items) ? body.items : [];
  return items.map((r) => ({
    sku: String(r.sku ?? ""),
    sellingPrice: Number(r.selling_price ?? 0),
    totalStock: Number(r.total_stock ?? 0),
    sampleName: r.sample_name ?? null,
  }));
}

export const fetchPrototypeSaleableSkus = cache(fetchPrototypeSaleableSkusUncached);
