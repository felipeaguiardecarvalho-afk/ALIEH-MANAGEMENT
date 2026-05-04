import type { CustomerApiRow } from "@/lib/customers-api";
import type { Customer } from "@/lib/types";

/** Shared mapping for SSR pages and client global store (same shape as Nova venda). */
export function mapCustomerApiRowsToCustomers(rows: CustomerApiRow[]): Customer[] {
  return rows.map((r) => ({
    id: r.id,
    customerCode: r.customer_code,
    name: r.name,
    cpf: r.cpf,
    rg: r.rg,
    phone: r.phone,
    email: r.email,
    instagram: r.instagram,
    zipCode: r.zip_code,
    street: r.street,
    number: r.number,
    neighborhood: r.neighborhood,
    city: r.city,
    state: r.state,
    country: r.country,
    createdAt: r.created_at ?? "",
  }));
}
