"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { apiPrototypeFetch, gateMutation, readApiError } from "@/lib/api-prototype";
import { requireAdmin, requireOperator } from "@/lib/rbac";

export type CustomerFormState = { ok: boolean; message: string };

function str(value: FormDataEntryValue | null) {
  return typeof value === "string" ? value.trim() : "";
}

function customerJsonFromForm(formData: FormData) {
  return {
    name: str(formData.get("name")),
    cpf: str(formData.get("cpf")) || null,
    rg: str(formData.get("rg")) || null,
    phone: str(formData.get("phone")) || null,
    email: str(formData.get("email")) || null,
    instagram: str(formData.get("instagram")) || null,
    zip_code: str(formData.get("zip_code")) || null,
    street: str(formData.get("street")) || null,
    number: str(formData.get("number")) || null,
    neighborhood: str(formData.get("neighborhood")) || null,
    city: str(formData.get("city")) || null,
    state: str(formData.get("state")) || null,
    country:
      str(formData.get("country")) || process.env.ALIEH_DEFAULT_COUNTRY?.trim() || null,
  };
}

export async function createCustomer(
  _prev: CustomerFormState,
  formData: FormData
): Promise<CustomerFormState> {
  const rbac = await requireOperator();
  if (rbac) return rbac;

  const gate = await gateMutation();
  if (gate) return gate;

  const body = customerJsonFromForm(formData);
  if (!body.name) return { ok: false, message: "Nome é obrigatório." };

  try {
    const res = await apiPrototypeFetch("/customers", {
      method: "POST",
      json: body,
    });
    if (!res.ok) {
      return { ok: false, message: await readApiError(res) };
    }
    const data = (await res.json()) as { customer_code?: string };
    const code = typeof data.customer_code === "string" ? data.customer_code.trim() : "";
    revalidatePath("/customers");
    return {
      ok: true,
      message: code ? `Cliente cadastrado. Código ${code}.` : "Cliente cadastrado.",
    };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao cadastrar cliente.",
    };
  }
}

export async function updateCustomer(
  _prev: CustomerFormState,
  formData: FormData
): Promise<CustomerFormState> {
  const rbac = await requireOperator();
  if (rbac) return rbac;

  const gate = await gateMutation();
  if (gate) return gate;

  const id = Number(formData.get("customer_id"));
  if (!Number.isFinite(id) || id < 1) {
    return { ok: false, message: "Cliente inválido." };
  }

  const body = customerJsonFromForm(formData);
  if (!body.name) return { ok: false, message: "Nome é obrigatório." };

  try {
    const res = await apiPrototypeFetch(`/customers/${id}`, {
      method: "PUT",
      json: body,
    });
    if (!res.ok) {
      return { ok: false, message: await readApiError(res) };
    }
    revalidatePath("/customers");
    revalidatePath(`/customers/${id}/edit`);
    return { ok: true, message: "Cliente actualizado." };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao actualizar cliente.",
    };
  }
}

export async function deleteCustomerForm(
  _prev: CustomerFormState,
  formData: FormData
): Promise<CustomerFormState> {
  const rbac = await requireAdmin();
  if (rbac) return rbac;

  const gate = await gateMutation();
  if (gate) return gate;

  const id = Number(formData.get("customer_id"));
  if (!Number.isFinite(id) || id < 1) {
    return { ok: false, message: "Cliente inválido." };
  }

  let res: Response;
  try {
    res = await apiPrototypeFetch(`/customers/${id}`, { method: "DELETE" });
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao excluir cliente.",
    };
  }
  if (!res.ok) {
    return { ok: false, message: await readApiError(res) };
  }
  revalidatePath("/customers");
  redirect("/customers");
}
