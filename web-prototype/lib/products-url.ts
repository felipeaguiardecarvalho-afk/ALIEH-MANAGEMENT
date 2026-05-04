/** Build query string for /products list + panel state (filters, pagination, detail). */

export type ProductCatalogQuery = Record<string, string | undefined>;

const CATALOG_KEYS = [
  "q",
  "frame_color",
  "lens_color",
  "gender",
  "palette",
  "style",
  "sort",
  "page",
  "page_size",
  "detail",
] as const;

export function normalizeProductCatalogParams(
  raw: Record<string, string | string[] | undefined>
): ProductCatalogQuery {
  const out: ProductCatalogQuery = {};
  for (const key of CATALOG_KEYS) {
    const v = raw[key];
    if (Array.isArray(v)) {
      const first = v[0]?.trim();
      if (first) out[key] = first;
    } else if (typeof v === "string" && v.trim()) {
      out[key] = v.trim();
    }
  }
  return out;
}

export function mergeProductCatalogQuery(
  current: ProductCatalogQuery,
  patch: Record<string, string | null | undefined>
): string {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(current)) {
    if (v !== undefined && v !== "") out[k] = v;
  }
  for (const [k, v] of Object.entries(patch)) {
    if (v === null || v === undefined || v === "") {
      delete out[k];
    } else {
      out[k] = v;
    }
  }
  const qs = new URLSearchParams(out);
  const s = qs.toString();
  return s ? `?${s}` : "";
}
