import type { ProductAttributeOptions } from "@/lib/products-api";
import {
  PRODUCT_FRAME_COLOR_OPTIONS,
  PRODUCT_GENDER_OPTIONS,
  PRODUCT_LENS_COLOR_OPTIONS,
  PRODUCT_PALETTE_OPTIONS,
  PRODUCT_STYLE_OPTIONS,
} from "@/lib/domain";

function mergeLists(domain: readonly string[], api: string[] | undefined): string[] {
  const set = new Set<string>();
  for (const s of domain) {
    const t = (s ?? "").trim();
    if (t) set.add(t);
  }
  for (const s of api ?? []) {
    const t = (s ?? "").trim();
    if (t) set.add(t);
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b, "pt"));
}

/** Union of canonical domain lists and values already present in the API (e.g. after custom saves). */
export function mergeDomainWithApiAttributeOptions(api: ProductAttributeOptions | null): ProductAttributeOptions {
  const a = api ?? {
    frame_color: [],
    lens_color: [],
    gender: [],
    palette: [],
    style: [],
  };
  return {
    frame_color: mergeLists(PRODUCT_FRAME_COLOR_OPTIONS, a.frame_color),
    lens_color: mergeLists(PRODUCT_LENS_COLOR_OPTIONS, a.lens_color),
    gender: mergeLists(PRODUCT_GENDER_OPTIONS, a.gender),
    palette: mergeLists(PRODUCT_PALETTE_OPTIONS, a.palette),
    style: mergeLists(PRODUCT_STYLE_OPTIONS, a.style),
  };
}
