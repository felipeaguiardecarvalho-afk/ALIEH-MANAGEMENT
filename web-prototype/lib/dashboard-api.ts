import "server-only";

import { apiPrototypeFetchRead, readApiError } from "@/lib/api-prototype";
import type { DashboardQuery } from "@/lib/dashboard-url";

export type DashboardFilterOptions = {
  skus: string[];
  products: { id: number; name: string }[];
  customers: { id: number; customer_code: string; name: string }[];
};

export type DashboardPanelKpis = {
  revenue: number;
  cost: number;
  profit: number;
  sales_count: number;
  unique_customers: number;
  ticket_avg: number;
  margin_pct: number;
  stock_units: number;
};

export type DashboardDailyRow = {
  day: string;
  revenue: number;
  cost: number;
  profit: number;
  revenue_ma7?: number | null;
};

export type DashboardSkuBreakdown = {
  sku: string;
  revenue: number;
  profit: number;
  qty: number;
};

export type DashboardProductBreakdown = {
  product_name: string;
  revenue: number;
  profit: number;
  qty: number;
};

export type DashboardCustomerBreakdown = {
  customer_id: number;
  customer_code: string;
  customer_name: string;
  revenue: number;
  n_orders: number;
  revenue_share_pct?: number;
};

export type DashboardPaymentBreakdown = {
  payment_method: string;
  revenue: number;
  n_sales: number;
};

export type DashboardMarginSkuRow = {
  sku: string;
  revenue: number;
  profit: number;
  qty: number;
  margin_pct: number;
};

export type DashboardCohortRow = {
  cohort_month: string;
  n_customers: number;
};

export type DashboardStockAgingRow = {
  sku: string;
  total_stock: number;
  last_sale_day: string | null;
  days_since_sale?: number | null;
  aging_flag?: string | null;
};

export type DashboardLowStockRow = {
  id: number;
  sku: string;
  name: string;
  unit_cost: number;
  sell_price: number;
  stock: number;
  priority: "critical" | "low";
};

export type DashboardStockTurnoverRow = {
  sku: string;
  units_sold: number;
  stock_on_hand: number;
  turnover_ratio: number | null;
};

export type DashboardInventorySummary = {
  total_units: number;
  value_cmp: number;
  n_critical_skus: number;
};

export type DashboardKpiDeltas = {
  revenue_pct: number | null;
  sales_count_pct: number | null;
  ticket_avg_pct: number | null;
  margin_pp: number;
};

export type DashboardPanelResponse = {
  date_start: string;
  date_end: string;
  prev_date_start: string;
  prev_date_end: string;
  filters: {
    sku: string;
    customer_id: number | null;
    product_id: number | null;
    aging_min_days: number;
    active_customer_days: number;
  };
  kpis: DashboardPanelKpis;
  kpis_previous: DashboardPanelKpis;
  kpi_deltas: DashboardKpiDeltas;
  active_customers_window: number;
  daily: DashboardDailyRow[];
  breakdown_skus: DashboardSkuBreakdown[];
  breakdown_products: DashboardProductBreakdown[];
  breakdown_customers: DashboardCustomerBreakdown[];
  breakdown_payment: DashboardPaymentBreakdown[];
  margin_by_sku: DashboardMarginSkuRow[];
  cohort: DashboardCohortRow[];
  stock_aging: DashboardStockAgingRow[];
  low_stock: DashboardLowStockRow[];
  inventory_summary: DashboardInventorySummary;
  insights: string[];
  /** Presente nas respostas actuais da API; omisso em caches antigos. */
  stock_turnover?: DashboardStockTurnoverRow[];
};

function panelQueryString(q: DashboardQuery): string {
  const params = new URLSearchParams();
  params.set("date_start", q.date_from);
  params.set("date_end", q.date_to);
  if (q.sku) params.set("sku", q.sku);
  if (q.customer_id) params.set("customer_id", q.customer_id);
  if (q.product_id) params.set("product_id", q.product_id);
  params.set("aging_min_days", q.aging_min_days || "45");
  params.set("active_customer_days", q.active_customer_days || "90");
  return `?${params.toString()}`;
}

export async function fetchPrototypeDashboardFilters(): Promise<DashboardFilterOptions> {
  const res = await apiPrototypeFetchRead("/dashboard/filters");
  if (!res.ok) throw new Error(await readApiError(res));
  return (await res.json()) as DashboardFilterOptions;
}

export async function fetchPrototypeDashboardPanel(
  q: DashboardQuery
): Promise<DashboardPanelResponse> {
  const res = await apiPrototypeFetchRead(`/dashboard/panel${panelQueryString(q)}`);
  if (!res.ok) throw new Error(await readApiError(res));
  return (await res.json()) as DashboardPanelResponse;
}
