/**
 * Short-lived in-memory cache for client-only perceived performance (SWR-style).
 * Does not replace server validation; avoids redundant round-trips when navigating
 * or re-selecting the same SKU. TTL keeps data from going stale indefinitely.
 */
import type { ProductBatch } from "@/lib/types";

/** Longer TTL keeps “instant” revisits when navigating back to Nova venda. */
const BATCH_TTL_MS = 120_000;
const batches = new Map<string, { rows: ProductBatch[]; ts: number }>();

export function getCachedSaleBatches(sku: string): ProductBatch[] | null {
  const key = (sku || "").trim();
  if (!key) return null;
  const hit = batches.get(key);
  if (!hit) return null;
  if (Date.now() - hit.ts > BATCH_TTL_MS) {
    batches.delete(key);
    return null;
  }
  return hit.rows;
}

export function setCachedSaleBatches(sku: string, rows: ProductBatch[]): void {
  const key = (sku || "").trim();
  if (!key) return;
  batches.set(key, { rows, ts: Date.now() });
}

/** After a successful sale, batch stock may change — drop cached rows for that SKU. */
export function invalidateCachedSaleBatches(sku: string): void {
  batches.delete((sku || "").trim());
}

/** Clear all batch rows (e.g. after a confirmed sale — stock may have changed on several SKUs). */
export function clearAllCachedSaleBatches(): void {
  batches.clear();
}
