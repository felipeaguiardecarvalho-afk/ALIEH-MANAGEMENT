import "server-only";

import { apiPrototypeFetch, readApiError } from "@/lib/api-prototype";
import type { SkuMasterRow } from "@/lib/types";

export type SkuMasterApiRow = {
  sku: string;
  total_stock: number;
  avg_unit_cost: number;
  selling_price: number;
  structured_cost_total: number;
  updated_at: string | null;
};

export type PricingSnapshotApi = {
  sku_master: SkuMasterApiRow;
  active_pricing: PricingRecordApiRow | null;
};

export type PricingRecordApiRow = {
  id: number;
  sku: string;
  avg_cost_snapshot: number;
  markup_pct: number;
  taxes_pct: number;
  interest_pct: number;
  markup_kind: number;
  taxes_kind: number;
  interest_kind: number;
  price_before_taxes: number;
  price_with_taxes: number;
  target_price: number;
  is_active: boolean;
  created_at: string | null;
};

export type PriceHistoryApiRow = {
  id: number;
  sku: string;
  old_price: number | null;
  new_price: number;
  created_at: string | null;
  note: string | null;
};

export function mapSkuMasterApiToRow(r: SkuMasterApiRow): SkuMasterRow {
  return {
    sku: r.sku,
    totalStock: r.total_stock,
    avgUnitCost: r.avg_unit_cost,
    sellingPrice: r.selling_price,
    structuredCostTotal: r.structured_cost_total,
  };
}

export async function fetchPrototypeSkuMasterList(): Promise<SkuMasterRow[]> {
  const res = await apiPrototypeFetch("/pricing/sku-master");
  if (!res.ok) throw new Error(await readApiError(res));
  const data = (await res.json()) as { items: SkuMasterApiRow[] };
  return (data.items ?? []).map(mapSkuMasterApiToRow);
}
