import { fetchPrototypeInventoryLotOptions } from "@/lib/inventory-api";

/** Warm filter options (light) before heavy `/inventory` page work. */
export default async function InventoryLayout({ children }: { children: React.ReactNode }) {
  await fetchPrototypeInventoryLotOptions().catch(() => {});
  return children;
}
