/** Tipos do módulo de custos (sem `server-only` — seguros para import em Client Components). */

export type SkuMasterCostRow = {
  sku: string;
  total_stock: number;
  avg_unit_cost: number;
  selling_price: number;
  structured_cost_total: number;
  valuation_cmp: number;
  updated_at: string | null;
};

export type SkuCostPickerOption = { label: string; sku: string };

export type CostCompositionComponent = {
  component_key: string;
  label: string;
  unit_price: number;
  quantity: number;
  line_total: number;
  updated_at?: string | null;
  quantity_text?: string;
};

export type PreviewCompositionLine = {
  component_key: string;
  label: string;
  quantity_parsed: number | null;
  unit_price_parsed: number | null;
  line_total: number | null;
  quantity_error: string | null;
  price_error: string | null;
};

export type PreviewCompositionResponse = {
  lines: PreviewCompositionLine[];
  live_total: number;
  errors: string[];
  has_errors: boolean;
};

export type StockCostHistoryRow = {
  id?: number | null;
  product_id?: number | null;
  created_at: string;
  sku: string;
  quantity: number;
  unit_cost: number;
  total_cost: number;
  stock_before?: number;
  stock_after?: number;
  cmp_before?: number;
  cmp_after?: number;
};

export type StockEntryBatch = {
  id: number;
  sku: string;
  name: string;
  product_enter_code: string | null;
  stock: number;
  label: string;
};
