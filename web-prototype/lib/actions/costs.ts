"use server";

import { revalidatePath } from "next/cache";
import { SKU_COST_COMPONENT_DEFINITIONS } from "@/lib/domain";
import { fetchCostsComposition, postPreviewComposition } from "@/lib/costs-api";
import { apiPrototypeFetch, gateMutation, readApiError } from "@/lib/api-prototype";
import type { PreviewCompositionResponse } from "@/lib/costs-types";
import { requireAdmin } from "@/lib/rbac";

export type CostState = { ok: boolean; message: string };

function num(value: FormDataEntryValue | null) {
  if (typeof value !== "string") return 0;
  return Number(value.replace(",", ".")) || 0;
}

/** Pré-visualização de totais — cálculo apenas na API. */
export async function previewCostCompositionAction(
  lines: { component_key: string; quantity_text: string; unit_price: number }[]
): Promise<PreviewCompositionResponse> {
  return postPreviewComposition(lines);
}

export async function loadCostCompositionAction(sku: string) {
  const s = sku.trim();
  if (!s) return null;
  return fetchCostsComposition(s);
}

export async function saveCostStructure(_prev: CostState, formData: FormData): Promise<CostState> {
  const admin = await requireAdmin();
  if (admin) return { ok: false, message: admin.message };

  const gate = await gateMutation();
  if (gate) return gate;

  const sku = String(formData.get("sku") || "").trim();
  if (!sku) return { ok: false, message: "Selecione um SKU." };

  const components = SKU_COST_COMPONENT_DEFINITIONS.map((component) => ({
    component_key: component.key,
    unit_price: num(formData.get(`price_${component.key}`)),
    quantity: 0,
    quantity_text: String(formData.get(`qty_${component.key}`) ?? ""),
  }));

  try {
    const res = await apiPrototypeFetch("/products/sku/cost-structure", {
      method: "POST",
      json: { sku, components },
    });
    if (!res.ok) {
      return { ok: false, message: await readApiError(res) };
    }
    revalidatePath("/costs");
    return { ok: true, message: "Composição de custo salva." };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao salvar composição.",
    };
  }
}
