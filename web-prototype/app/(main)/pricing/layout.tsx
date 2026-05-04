import { fetchCostsSkuOptions } from "@/lib/costs-api";
import { fetchPrototypeSkuMasterList } from "@/lib/pricing-api";

/** Warm pricing masters + SKU picker before `/pricing` interactive load. */
export default async function PricingLayout({ children }: { children: React.ReactNode }) {
  await Promise.all([
    fetchPrototypeSkuMasterList().catch(() => {}),
    fetchCostsSkuOptions().catch(() => {}),
  ]);
  return children;
}
