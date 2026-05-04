export type InventoryLotsQuery = Record<string, string | undefined>;

const KEYS = [
  "names",
  "skus",
  "frame_colors",
  "lens_colors",
  "genders",
  "styles",
  "palettes",
  "costs",
  "prices",
  "markups",
  "stocks",
  "sku",
  "frame_color",
  "lens_color",
  "gender",
  "style",
  "palette",
  "sort",
] as const;

/** Keys stored in URL after normalize (legacy single-value keys are folded into plural). */
const URL_KEYS = new Set<string>([
  "names",
  "skus",
  "frame_colors",
  "lens_colors",
  "genders",
  "styles",
  "palettes",
  "costs",
  "prices",
  "markups",
  "stocks",
  "sort",
]);

function pickCsv(raw: Record<string, string | string[] | undefined>, key: string): string | undefined {
  const v = raw[key];
  if (Array.isArray(v)) {
    const parts = [...new Set(v.map((x) => String(x).trim()).filter(Boolean))];
    return parts.length ? parts.join(",") : undefined;
  }
  if (typeof v === "string" && v.trim()) return v.trim();
  return undefined;
}

function pickScalar(raw: Record<string, string | string[] | undefined>, key: string): string | undefined {
  const v = raw[key];
  if (Array.isArray(v)) {
    const first = v[0]?.trim();
    if (first) return first;
    return undefined;
  }
  if (typeof v === "string" && v.trim()) return v.trim();
  return undefined;
}

export function normalizeInventoryLotsParams(
  raw: Record<string, string | string[] | undefined>
): InventoryLotsQuery {
  const out: InventoryLotsQuery = {};
  const multiKeys = new Set([
    "names",
    "skus",
    "frame_colors",
    "lens_colors",
    "genders",
    "styles",
    "palettes",
    "costs",
    "prices",
    "markups",
    "stocks",
  ]);
  for (const key of KEYS) {
    const v = multiKeys.has(key) ? pickCsv(raw, key) : pickScalar(raw, key);
    if (v !== undefined && v !== "") out[key] = v;
  }
  if (!out.skus && out.sku) {
    out.skus = out.sku;
    delete out.sku;
  }
  if (!out.frame_colors && out.frame_color) {
    out.frame_colors = out.frame_color;
    delete out.frame_color;
  }
  if (!out.lens_colors && out.lens_color) {
    out.lens_colors = out.lens_color;
    delete out.lens_color;
  }
  if (!out.genders && out.gender) {
    out.genders = out.gender;
    delete out.gender;
  }
  if (!out.styles && out.style) {
    out.styles = out.style;
    delete out.style;
  }
  if (!out.palettes && out.palette) {
    out.palettes = out.palette;
    delete out.palette;
  }
  for (const k of Object.keys(out)) {
    if (!URL_KEYS.has(k)) delete out[k];
  }
  return out;
}

/** Stable key for `React.cache` dedupe of identical inventory lot queries in one RSC request. */
export function inventoryLotsFetchCacheKey(
  q: InventoryLotsQuery,
  paging?: { page?: string; page_size?: string }
): string {
  const sortedQ = Object.fromEntries(
    Object.entries(q)
      .filter(([, v]) => v != null && String(v).length > 0)
      .sort(([a], [b]) => a.localeCompare(b))
  );
  const p = {
    page: paging?.page ?? "1",
    page_size: paging?.page_size ?? "50000",
  };
  return JSON.stringify({ q: sortedQ, p });
}
