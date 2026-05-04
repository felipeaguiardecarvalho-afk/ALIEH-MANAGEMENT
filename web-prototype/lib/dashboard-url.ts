export type PeriodPreset = "custom" | "7" | "30" | "90";

export type DashboardQuery = {
  date_from: string;
  date_to: string;
  sku: string;
  customer_id: string;
  product_id: string;
  period_preset: PeriodPreset;
  aging_min_days: string;
  active_customer_days: string;
};

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function addDays(iso: string, deltaDays: number): string {
  const d = new Date(`${iso}T12:00:00.000Z`);
  d.setUTCDate(d.getUTCDate() + deltaDays);
  return d.toISOString().slice(0, 10);
}

function defaultRange(): { from: string; to: string } {
  const end = todayISO();
  return { from: addDays(end, -29), to: end };
}

function isPreset(p: string): p is Exclude<PeriodPreset, "custom"> {
  return p === "7" || p === "30" || p === "90";
}

export function normalizeDashboardQuery(
  raw: Record<string, string | string[] | undefined>
): DashboardQuery {
  const pick = (key: string): string => {
    const v = raw[key];
    if (Array.isArray(v)) return (v[0] ?? "").trim();
    return typeof v === "string" ? v.trim() : "";
  };

  const presetRaw = pick("period_preset");
  const period_preset: PeriodPreset = isPreset(presetRaw)
    ? presetRaw
    : presetRaw === "custom"
      ? "custom"
      : "custom";

  const end = todayISO();
  let dateFrom = pick("date_from");
  let dateTo = pick("date_to");

  if (isPreset(period_preset)) {
    const daysBack = period_preset === "7" ? 6 : period_preset === "30" ? 29 : 89;
    dateTo = end;
    dateFrom = addDays(end, -daysBack);
  } else {
    const { from: defFrom, to: defTo } = defaultRange();
    dateFrom = dateFrom || defFrom;
    dateTo = dateTo || defTo;
  }

  const agingPick = pick("aging_min_days");
  const activePick = pick("active_customer_days");

  return {
    date_from: dateFrom,
    date_to: dateTo,
    sku: pick("sku"),
    customer_id: pick("customer_id"),
    product_id: pick("product_id"),
    period_preset,
    aging_min_days: agingPick || "45",
    active_customer_days: activePick || "90",
  };
}

export function mergeDashboardQuery(
  current: DashboardQuery,
  patch: Partial<Record<keyof DashboardQuery, string | null | undefined>>
): string {
  const next: Record<string, string> = {};
  for (const [k, v] of Object.entries(current)) {
    if (v) next[k] = v;
  }
  for (const [k, v] of Object.entries(patch)) {
    if (v === null || v === undefined || v === "") delete next[k];
    else next[k] = v;
  }
  const qs = new URLSearchParams(next);
  const s = qs.toString();
  return s ? `?${s}` : "";
}
