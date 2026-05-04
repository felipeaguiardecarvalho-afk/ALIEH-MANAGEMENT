"use client";

/**
 * Client-only SWR-style cache + in-flight dedupe for pricing insight fetches.
 * Cuts duplicate parallel triplets when components re-mount or SKU is re-selected.
 */
import {
  loadPriceHistory,
  loadPricingRecords,
  loadPricingSnapshot,
} from "@/lib/actions/pricing";
import type { PriceHistoryApiRow, PricingRecordApiRow, PricingSnapshotApi } from "@/lib/pricing-api";

export type PricingInsightBundle = {
  snap: PricingSnapshotApi | null;
  rec: PricingRecordApiRow[];
  ph: PriceHistoryApiRow[];
};

/** Client-only SWR window — longer = fewer repeat triplets when switching SKUs. */
const TTL_MS = 90_000;
const store = new Map<string, { ts: number; data: PricingInsightBundle }>();
const inflight = new Map<string, Promise<PricingInsightBundle>>();

export function invalidatePricingInsightCache(sku?: string): void {
  const k = (sku ?? "").trim();
  if (!k) store.clear();
  else store.delete(k);
}

async function fetchFresh(sku: string): Promise<PricingInsightBundle> {
  const [snap, rec, ph] = await Promise.all([
    loadPricingSnapshot(sku),
    loadPricingRecords(sku),
    loadPriceHistory(sku),
  ]);
  return { snap, rec, ph };
}

/** Returns cached bundle when fresh; otherwise one shared in-flight fetch per SKU. */
export function loadPricingInsightBundleCached(sku: string): Promise<PricingInsightBundle> {
  const key = sku.trim();
  if (!key) return Promise.resolve({ snap: null, rec: [], ph: [] });

  const hit = store.get(key);
  if (hit && Date.now() - hit.ts < TTL_MS) return Promise.resolve(hit.data);

  const existing = inflight.get(key);
  if (existing) return existing;

  const p = fetchFresh(key)
    .then((data) => {
      store.set(key, { ts: Date.now(), data });
      return data;
    })
    .finally(() => {
      inflight.delete(key);
    });
  inflight.set(key, p);
  return p;
}
