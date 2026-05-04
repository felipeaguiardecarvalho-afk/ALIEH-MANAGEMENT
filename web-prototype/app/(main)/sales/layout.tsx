import { fetchPrototypeCustomersList } from "@/lib/customers-api";
import { fetchPrototypeInventoryLotOptions } from "@/lib/inventory-api";
import { fetchPrototypeSaleableSkus } from "@/lib/sales-api";

/**
 * Warm SKUs, customers, and inventory filter metadata for `/sales` and `/sales/new`
 * (and Estoque opens faster after visiting Vendas).
 */
export default async function SalesLayout({ children }: { children: React.ReactNode }) {
  await Promise.all([
    fetchPrototypeSaleableSkus().catch(() => {}),
    fetchPrototypeCustomersList().catch(() => {}),
    fetchPrototypeInventoryLotOptions().catch(() => {}),
  ]);
  return children;
}
