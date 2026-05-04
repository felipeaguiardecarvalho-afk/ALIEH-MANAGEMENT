import { fetchPrototypeCustomersList } from "@/lib/customers-api";

/**
 * Warm React.cache + API read cache before `/customers/*` pages render (perceived instant list).
 */
export default async function CustomersLayout({ children }: { children: React.ReactNode }) {
  await fetchPrototypeCustomersList().catch(() => {});
  return children;
}
