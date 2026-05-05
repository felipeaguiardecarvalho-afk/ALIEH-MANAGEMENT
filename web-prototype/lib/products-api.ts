import "server-only";

import { apiPrototypeFetchRead, readApiError } from "@/lib/api-prototype";
import type { ProductCatalogQuery } from "@/lib/products-url";

export type ProductAttributeOptions = {
  frame_color: string[];
  lens_color: string[];
  gender: string[];
  palette: string[];
  style: string[];
};

export type ProductListRow = {
  id: number;
  sku: string | null;
  name: string;
  frame_color: string | null;
  lens_color: string | null;
  gender: string | null;
  palette: string | null;
  style: string | null;
  stock: number;
  created_at: string | null;
  avg_cost: number;
  sell_price: number;
};

export type ProductListResponse = {
  items: ProductListRow[];
  total: number;
  page: number;
  page_size: number;
};

export type ProductDetail = {
  id: number;
  sku: string | null;
  name: string;
  frame_color: string | null;
  lens_color: string | null;
  gender: string | null;
  palette: string | null;
  style: string | null;
  stock: number;
  registered_date: string | null;
  product_enter_code: string | null;
  created_at: string | null;
  product_image_path: string | null;
  avg_cost: number;
  sell_price: number;
  lot_edit_block_reason: string | null;
  sku_delete_block_reason: string | null;
};

function listQueryFromCatalog(q: ProductCatalogQuery): string {
  const params = new URLSearchParams();
  const map: [keyof ProductCatalogQuery, string][] = [
    ["q", "q"],
    ["frame_color", "frame_color"],
    ["lens_color", "lens_color"],
    ["gender", "gender"],
    ["palette", "palette"],
    ["style", "style"],
    ["sort", "sort"],
    ["page", "page"],
    ["page_size", "page_size"],
  ];
  for (const [from, to] of map) {
    const v = q[from]?.trim();
    if (v) params.set(to, v);
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

export async function fetchPrototypeProductList(
  q: ProductCatalogQuery
): Promise<ProductListResponse> {
  const qs = listQueryFromCatalog(q);
  const res = await apiPrototypeFetchRead(`/products${qs}`);
  if (!res.ok) {
    throw new Error(await readApiError(res));
  }
  return (await res.json()) as ProductListResponse;
}

export async function fetchPrototypeProductAttributeOptions(): Promise<ProductAttributeOptions> {
  const res = await apiPrototypeFetchRead("/products/attribute-options");
  if (!res.ok) {
    throw new Error(await readApiError(res));
  }
  return (await res.json()) as ProductAttributeOptions;
}

export async function fetchPrototypeProductDetail(id: number): Promise<ProductDetail | null> {
  const res = await apiPrototypeFetchRead(`/products/${id}`);
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(await readApiError(res));
  }
  return (await res.json()) as ProductDetail;
}

/** Imagem em disco servida por ``GET /products/{id}/image`` — data URL para ``<img src>`` no SSR. */
export async function fetchPrototypeProductDiskImageDataUrl(productId: number): Promise<string | null> {
  const res = await apiPrototypeFetchRead(`/products/${productId}/image`);
  if (!res.ok) return null;
  const mime = res.headers.get("content-type")?.split(";")[0]?.trim() || "image/jpeg";
  const buf = Buffer.from(await res.arrayBuffer());
  if (buf.length === 0) return null;
  return `data:${mime};base64,${buf.toString("base64")}`;
}
