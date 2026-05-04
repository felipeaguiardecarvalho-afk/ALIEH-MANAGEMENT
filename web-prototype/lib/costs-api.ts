import "server-only";

import { cache } from "react";
import { apiPrototypeFetch, apiPrototypeFetchRead, readApiError } from "@/lib/api-prototype";
import type {
  CostCompositionComponent,
  PreviewCompositionResponse,
  SkuCostPickerOption,
  SkuMasterCostRow,
  StockCostHistoryRow,
  StockEntryBatch,
} from "@/lib/costs-types";

export type {
  CostCompositionComponent,
  PreviewCompositionResponse,
  SkuCostPickerOption,
  SkuMasterCostRow,
  StockCostHistoryRow,
  StockEntryBatch,
} from "@/lib/costs-types";

export async function fetchCostsSkuMasters(): Promise<SkuMasterCostRow[]> {
  const res = await apiPrototypeFetchRead("/costs/sku-masters");
  if (!res.ok) throw new Error(await readApiError(res));
  const j = (await res.json()) as { items: SkuMasterCostRow[] };
  return j.items ?? [];
}

async function fetchCostsSkuOptionsUncached(): Promise<{
  skus: string[];
  pick_by_name: SkuCostPickerOption[];
}> {
  const res = await apiPrototypeFetchRead("/costs/sku-options");
  if (!res.ok) throw new Error(await readApiError(res));
  return (await res.json()) as { skus: string[]; pick_by_name: SkuCostPickerOption[] };
}

/** Dedupes within one RSC request (e.g. custos + precificação no mesmo render). */
export const fetchCostsSkuOptions = cache(fetchCostsSkuOptionsUncached);

export async function fetchCostsComposition(sku: string): Promise<{
  sku: string;
  components: CostCompositionComponent[];
  last_saved_structured_total: number;
}> {
  const q = new URLSearchParams({ sku: sku.trim() });
  const res = await apiPrototypeFetchRead(`/costs/composition?${q}`);
  if (!res.ok) throw new Error(await readApiError(res));
  return (await res.json()) as {
    sku: string;
    components: CostCompositionComponent[];
    last_saved_structured_total: number;
  };
}

export async function fetchStockCostHistory(limit = 75): Promise<StockCostHistoryRow[]> {
  const res = await apiPrototypeFetchRead(`/costs/stock-cost-history?limit=${limit}`);
  if (!res.ok) throw new Error(await readApiError(res));
  const j = (await res.json()) as { items: StockCostHistoryRow[] };
  return j.items ?? [];
}

export async function fetchStockEntryContext(sku: string): Promise<{
  sku: string;
  structured_unit_cost: number;
  batches: StockEntryBatch[];
  components_readonly: { componente: string; preço_unit: number; qtd: number; linha: number }[];
}> {
  const q = new URLSearchParams({ sku: sku.trim() });
  const res = await apiPrototypeFetchRead(`/costs/stock-entry?${q}`);
  if (!res.ok) throw new Error(await readApiError(res));
  return (await res.json()) as {
    sku: string;
    structured_unit_cost: number;
    batches: StockEntryBatch[];
    components_readonly: { componente: string; preço_unit: number; qtd: number; linha: number }[];
  };
}

export async function postPreviewComposition(
  lines: { component_key: string; quantity_text: string; unit_price: number }[]
): Promise<PreviewCompositionResponse> {
  const res = await apiPrototypeFetch("/costs/preview-composition", {
    method: "POST",
    json: { lines },
  });
  if (!res.ok) throw new Error(await readApiError(res));
  return (await res.json()) as PreviewCompositionResponse;
}
