"use client";

/**
 * Global client data layer (Zustand): survives client-side navigations, TTL + in-flight
 * dedupe per slice. Batches per SKU mirror `prototype-client-cache` updates for compat.
 */
import { create } from "zustand";
import { loadGlobalReadBundleAction } from "@/lib/actions/client-data-bootstrap";
import { loadSaleBatchesDeduped } from "@/lib/sale-batches-client-dedupe";
import {
  clearAllCachedSaleBatches,
  setCachedSaleBatches,
} from "@/lib/prototype-client-cache";
import type { InventoryLotFilterOptions } from "@/lib/inventory-api";
import type { Customer, ProductBatch, SaleableSku, SkuMasterRow } from "@/lib/types";

const TTL_MAIN_MS = 120_000;
const TTL_BATCH_MS = 120_000;

type Slice<T> = {
  data: T | null;
  ts: number;
  isFetching: boolean;
};

type BatchSlot = {
  data: ProductBatch[] | null;
  ts: number;
  promise: Promise<ProductBatch[]> | null;
};

const emptySlice = <T,>(): Slice<T> => ({ data: null, ts: 0, isFetching: false });

function fresh(ts: number, ttl: number) {
  return ts > 0 && Date.now() - ts < ttl;
}

let bundleInflight: Promise<void> | null = null;

export type GlobalClientDataState = {
  customers: Slice<Customer[]>;
  saleableSkus: Slice<SaleableSku[]>;
  inventoryLotOptions: Slice<InventoryLotFilterOptions | null>;
  skuMasters: Slice<SkuMasterRow[]>;
  batchesBySku: Record<string, BatchSlot>;

  /** SSR snapshot — avoids refetch right after hard navigation to Nova venda. */
  hydrateSalePage: (p: { customers: Customer[]; skus: SaleableSku[] }) => void;

  /** One bundled server action when slices are stale (deduped globally). */
  ensureGlobalBundle: (opts?: { force?: boolean }) => Promise<void>;

  /** Per-SKU batches with TTL + shared promise (SWR-style). */
  ensureSaleBatches: (sku: string) => Promise<ProductBatch[]>;

  /** Fire-and-forget top SKUs (used on mount / pointer / nav). */
  prefetchSaleBatchCluster: (skus: string[], limit?: number) => void;

  invalidateAllBatches: () => void;
};

export const useClientDataStore = create<GlobalClientDataState>((set, get) => ({
  customers: emptySlice(),
  saleableSkus: emptySlice(),
  inventoryLotOptions: emptySlice(),
  skuMasters: emptySlice(),
  batchesBySku: {},

  hydrateSalePage: ({ customers, skus }) => {
    const now = Date.now();
    set({
      customers: { data: customers, ts: now, isFetching: false },
      saleableSkus: { data: skus, ts: now, isFetching: false },
    });
  },

  ensureGlobalBundle: async (opts) => {
    const st = get();
    if (
      !opts?.force &&
      st.customers.data &&
      st.saleableSkus.data &&
      fresh(st.customers.ts, TTL_MAIN_MS)
    ) {
      return;
    }
    if (bundleInflight) {
      await bundleInflight;
      return;
    }
    bundleInflight = (async () => {
      try {
        const b = await loadGlobalReadBundleAction();
        const now = Date.now();
        set({
          customers: { data: b.customers, ts: now, isFetching: false },
          saleableSkus: { data: b.saleableSkus, ts: now, isFetching: false },
          inventoryLotOptions: {
            data: b.inventoryLotOptions,
            ts: now,
            isFetching: false,
          },
          skuMasters: { data: b.skuMasters, ts: now, isFetching: false },
        });
      } catch {
        const s = get();
        set({
          customers: { ...s.customers, isFetching: false },
          saleableSkus: { ...s.saleableSkus, isFetching: false },
          inventoryLotOptions: { ...s.inventoryLotOptions, isFetching: false },
          skuMasters: { ...s.skuMasters, isFetching: false },
        });
      } finally {
        bundleInflight = null;
      }
    })();
    await bundleInflight;
  },

  ensureSaleBatches: async (rawSku) => {
    const sku = (rawSku || "").trim();
    if (!sku) return [];
    const slot = get().batchesBySku[sku] ?? {
      data: null,
      ts: 0,
      promise: null,
    };
    if (slot.data != null && fresh(slot.ts, TTL_BATCH_MS) && !slot.promise) {
      return slot.data;
    }
    if (slot.promise) return slot.promise;

    const p = loadSaleBatchesDeduped(sku).then((rows) => {
      setCachedSaleBatches(sku, rows);
      set((s) => ({
        batchesBySku: {
          ...s.batchesBySku,
          [sku]: { data: rows, ts: Date.now(), promise: null },
        },
      }));
      return rows;
    });
    set((s) => ({
      batchesBySku: {
        ...s.batchesBySku,
        [sku]: { data: slot.data, ts: slot.ts, promise: p },
      },
    }));
    return p;
  },

  prefetchSaleBatchCluster: (skus, limit = 24) => {
    const slice = skus.slice(0, limit);
    for (const sku of slice) {
      const s = (sku || "").trim();
      if (!s) continue;
      const slot = get().batchesBySku[s];
      if (slot?.promise || (slot?.data && fresh(slot.ts, TTL_BATCH_MS))) continue;
      void get().ensureSaleBatches(s);
    }
  },

  invalidateAllBatches: () => {
    clearAllCachedSaleBatches();
    set({ batchesBySku: {} });
  },
}));
