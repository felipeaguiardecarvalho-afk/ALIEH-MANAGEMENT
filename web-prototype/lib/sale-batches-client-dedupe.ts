"use client";

/**
 * Global in-flight dedupe for `loadSaleBatchesAction`: multiple components / effects
 * requesting the same SKU share one server round-trip (prefetch + form + Strict Mode).
 */
import { loadSaleBatchesAction } from "@/lib/actions/sales";
import type { ProductBatch } from "@/lib/types";

const inflight = new Map<string, Promise<ProductBatch[]>>();

export function loadSaleBatchesDeduped(sku: string): Promise<ProductBatch[]> {
  const key = (sku || "").trim();
  if (!key) return Promise.resolve([]);
  const existing = inflight.get(key);
  if (existing) return existing;
  const p = loadSaleBatchesAction(key).finally(() => {
    inflight.delete(key);
  });
  inflight.set(key, p);
  return p;
}
