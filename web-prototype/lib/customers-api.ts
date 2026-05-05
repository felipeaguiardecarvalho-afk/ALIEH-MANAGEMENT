import "server-only";

import { cache } from "react";
import { apiPrototypeFetchRead, readApiError } from "@/lib/api-prototype";

export type CustomerApiRow = {
  id: number;
  customer_code: string;
  name: string;
  cpf: string | null;
  rg: string | null;
  phone: string | null;
  email: string | null;
  instagram: string | null;
  zip_code: string | null;
  street: string | null;
  number: string | null;
  neighborhood: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  created_at: string | null;
  /** Present when API returns it (`customers_read` + serialize). */
  updated_at?: string | null;
};

async function fetchPrototypeCustomersListUncached(): Promise<CustomerApiRow[]> {
  const res = await apiPrototypeFetchRead("/customers");
  if (!res.ok) throw new Error(await readApiError(res));
  const data = (await res.json()) as { items: CustomerApiRow[] };
  return data.items ?? [];
}

/** Dedupes identical calls within the same RSC render (e.g. layout + page). */
export const fetchPrototypeCustomersList = cache(fetchPrototypeCustomersListUncached);

async function fetchPrototypeCustomerUncached(id: number): Promise<CustomerApiRow | null> {
  const res = await apiPrototypeFetchRead(`/customers/${id}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(await readApiError(res));
  return (await res.json()) as CustomerApiRow;
}

export const fetchPrototypeCustomer = cache(fetchPrototypeCustomerUncached);
