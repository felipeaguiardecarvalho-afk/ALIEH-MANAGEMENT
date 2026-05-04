"use server";

import { revalidatePath } from "next/cache";
import { fetchStockEntryContext } from "@/lib/costs-api";
import { formatProductStock } from "@/lib/format";
import { apiPrototypeFetch, apiPrototypeFetchRead, gateMutation, readApiError } from "@/lib/api-prototype";
import { logPrototypeAuditEvent } from "@/lib/prototype-audit";
import { requireAdminForPricing } from "@/lib/rbac";

export type InventoryState = { ok: boolean; message: string };

export async function loadStockEntryContextAction(sku: string) {
  const s = sku.trim();
  if (!s) return null;
  return fetchStockEntryContext(s);
}

export type ParseQuantityResult = {
  error: string | null;
  parsed: number | null;
  positive_ok: boolean;
};

/** Quantidade de entrada — validação idêntica ao Streamlit (`parse_cost_quantity_text` + regra > 0). */
export async function parseStockQuantityTextAction(quantityText: string): Promise<ParseQuantityResult> {
  try {
    const res = await apiPrototypeFetchRead("/costs/parse-quantity-text", {
      method: "POST",
      json: { quantity_text: quantityText },
    });
    if (!res.ok) {
      return { error: await readApiError(res), parsed: null, positive_ok: false };
    }
    return (await res.json()) as ParseQuantityResult;
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : "Falha ao validar quantidade.",
      parsed: null,
      positive_ok: false,
    };
  }
}

function num(value: FormDataEntryValue | null) {
  if (typeof value !== "string") return 0;
  return Number(value.replace(",", ".")) || 0;
}

export async function manualWriteDown(
  _prev: InventoryState,
  formData: FormData
): Promise<InventoryState> {
  const rbac = await requireAdminForPricing();
  if (rbac) return rbac;

  const gate = await gateMutation();
  if (gate) return gate;

  const confirmed = formData.get("confirm_write_down");
  if (confirmed !== "on") {
    return { ok: false, message: "Marque a confirmação antes de aplicar a baixa." };
  }

  const productId = Number(formData.get("product_id"));
  const qty = num(formData.get("quantity"));

  if (!productId) return { ok: false, message: "Selecione um lote." };
  if (qty <= 0) return { ok: false, message: "Quantidade inválida." };

  try {
    const res = await apiPrototypeFetch("/inventory/manual-write-down", {
      method: "POST",
      json: { product_id: productId, quantity: qty },
    });
    if (!res.ok) {
      return { ok: false, message: await readApiError(res) };
    }
    const body = (await res.json()) as { stock_after?: number };
    const rest = typeof body.stock_after === "number" ? body.stock_after : null;
    revalidatePath("/inventory");
    revalidatePath("/dashboard");
    if (rest != null) {
      return {
        ok: true,
        message: `Baixa aplicada. Stock restante deste lote: ${formatProductStock(rest)}.`,
      };
    }
    return { ok: true, message: `Baixa de ${qty} unidade(s) aplicada.` };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha na baixa de estoque.",
    };
  }
}

export async function excludeInventoryBatches(
  _prev: InventoryState,
  formData: FormData
): Promise<InventoryState> {
  const rbac = await requireAdminForPricing();
  if (rbac) return rbac;

  const gate = await gateMutation();
  if (gate) return gate;

  const raw = String(formData.get("codes_json") ?? "").trim();
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw || "[]");
  } catch {
    return { ok: false, message: "Lista de códigos inválida." };
  }
  if (!Array.isArray(parsed) || parsed.length === 0) {
    return { ok: false, message: "Seleccione pelo menos um lote com código de entrada." };
  }
  const cleaned = [
    ...new Set(
      parsed
        .map((c) => String(c ?? "").trim())
        .filter((c) => c.length > 0)
    ),
  ];
  if (cleaned.length > 1) {
    return { ok: false, message: "Seleccione apenas um lote por vez (paridade com o Streamlit)." };
  }
  if (!cleaned.length) {
    return { ok: false, message: "Nenhum código de lote válido." };
  }

  try {
    const res = await apiPrototypeFetch("/inventory/batches/exclude", {
      method: "POST",
      json: { product_enter_codes: cleaned },
    });
    if (!res.ok) {
      return { ok: false, message: await readApiError(res) };
    }
    await logPrototypeAuditEvent("stock", "exclude_batches", {
      product_enter_codes: cleaned,
    });
    revalidatePath("/inventory");
    revalidatePath("/products");
    revalidatePath("/dashboard");
    return {
      ok: true,
      message: `Exclusão de lote(s) aplicada (${cleaned.length} código(s)).`,
    };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha na exclusão em lote.",
    };
  }
}

export async function addStockReceipt(
  _prev: InventoryState,
  formData: FormData
): Promise<InventoryState> {
  const rbac = await requireAdminForPricing();
  if (rbac) return rbac;

  const gate = await gateMutation();
  if (gate) return gate;

  const sku = String(formData.get("sku") || "").trim();
  const productId = Number(formData.get("product_id"));
  const quantityText = String(formData.get("quantity_text") ?? "").trim();
  const confirmed =
    formData.get("confirm_receipt") === "on" ||
    formData.get("confirm_receipt") === "true" ||
    formData.get("confirm_receipt") === "1";

  if (!sku || !productId) return { ok: false, message: "SKU e lote são obrigatórios." };
  if (!quantityText) {
    return { ok: false, message: "Indique a quantidade (texto, até 4 decimais)." };
  }
  if (!confirmed) {
    return { ok: false, message: "Marque a confirmação antes de finalizar a entrada." };
  }

  try {
    const res = await apiPrototypeFetch("/inventory/stock-receipt", {
      method: "POST",
      json: {
        sku,
        product_id: productId,
        quantity_text: quantityText,
        quantity: 0,
        confirm_receipt: true,
      },
    });
    if (!res.ok) {
      return { ok: false, message: await readApiError(res) };
    }
    const body = (await res.json()) as { unit_cost_applied?: number; quantity?: number };
    const uc = typeof body.unit_cost_applied === "number" ? body.unit_cost_applied : 0;
    const q = typeof body.quantity === "number" ? body.quantity : 0;
    await logPrototypeAuditEvent("stock", "stock_receipt", {
      sku,
      product_id: productId,
      quantity: q,
      unit_cost_structured: uc,
    });
    revalidatePath("/inventory");
    revalidatePath("/costs");
    revalidatePath("/dashboard");
    return {
      ok: true,
      message: "Entrada registrada. Custo médio (CMP) do SKU atualizado.",
    };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao registrar entrada.",
    };
  }
}
