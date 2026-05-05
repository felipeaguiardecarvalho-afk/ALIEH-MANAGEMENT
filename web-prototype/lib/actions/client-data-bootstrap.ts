"use server";

/**
 * Single bundled read for client global store — one server round-trip from the browser,
 * parallel API calls on the server (same endpoints as antes; sem novos contratos).
 */
import { mapCustomerApiRowsToCustomers } from "@/lib/customers-map";
import { fetchPrototypeCustomersList } from "@/lib/customers-api";
import type { InventoryLotFilterOptions } from "@/lib/inventory-api";
import { fetchPrototypeSaleableSkus } from "@/lib/sales-api";
import type { Customer } from "@/lib/types";
import type { SaleableSku } from "@/lib/types";
import type { SkuMasterRow } from "@/lib/types";

export type GlobalReadBundle = {
  customers: Customer[];
  saleableSkus: SaleableSku[];
  inventoryLotOptions: InventoryLotFilterOptions | null;
  skuMasters: SkuMasterRow[];
};

export async function loadGlobalReadBundleAction(): Promise<GlobalReadBundle> {
  const settled = await Promise.allSettled([
    fetchPrototypeCustomersList(),
    fetchPrototypeSaleableSkus(),
  ]);

  const customersRaw = settled[0].status === "fulfilled" ? settled[0].value : [];
  const saleableSkus = settled[1].status === "fulfilled" ? settled[1].value : [];

  return {
    customers: mapCustomerApiRowsToCustomers(customersRaw),
    saleableSkus,
    inventoryLotOptions: null,
    skuMasters: [],
  };
}
