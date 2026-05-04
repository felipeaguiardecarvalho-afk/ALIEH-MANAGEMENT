"use server";

import { revalidatePath } from "next/cache";
import { apiPrototypeFetch, gateMutation, readApiError } from "@/lib/api-prototype";
import { logPrototypeAuditEvent } from "@/lib/prototype-audit";
import type {
  PriceHistoryApiRow,
  PricingRecordApiRow,
  PricingSnapshotApi,
} from "@/lib/pricing-api";
import type { PricingKind } from "@/lib/pricing";
import { requireAdminForPricing } from "@/lib/rbac";

export type PricingState = { ok: boolean; message: string };

export type ComputePreviewInput = {
  avgCost: number;
  markupVal: number;
  taxesVal: number;
  interestVal: number;
  markupKind: PricingKind;
  taxesKind: PricingKind;
  interestKind: PricingKind;
};

export type ComputePreviewResult = {
  price_before: number;
  price_with_taxes: number;
  target: number;
};

async function postComputeTargetsApi(input: ComputePreviewInput): Promise<ComputePreviewResult | null> {
  const res = await apiPrototypeFetch("/pricing/sku/compute-targets", {
    method: "POST",
    json: {
      avg_cost: input.avgCost,
      markup_val: input.markupVal,
      taxes_val: input.taxesVal,
      interest_val: input.interestVal,
      markup_absolute: input.markupKind === 1,
      taxes_absolute: input.taxesKind === 1,
      interest_absolute: input.interestKind === 1,
    },
  });
  if (!res.ok) return null;
  return (await res.json()) as ComputePreviewResult;
}

/** Preview alinhado ao backend (`compute_sku_pricing_targets`). */
export async function computeSkuPricingPreview(
  input: ComputePreviewInput
): Promise<ComputePreviewResult | null> {
  const rbac = await requireAdminForPricing();
  if (rbac) return null;
  return postComputeTargetsApi(input);
}

function encSkuPath(sku: string) {
  return encodeURIComponent(sku.trim());
}

export async function loadPricingSnapshot(sku: string): Promise<PricingSnapshotApi | null> {
  const s = sku.trim();
  if (!s) return null;
  try {
    const res = await apiPrototypeFetch(`/pricing/sku/${encSkuPath(s)}/snapshot`);
    if (!res.ok) return null;
    return (await res.json()) as PricingSnapshotApi;
  } catch {
    return null;
  }
}

export async function loadPricingRecords(sku: string): Promise<PricingRecordApiRow[]> {
  const s = sku.trim();
  if (!s) return [];
  try {
    const res = await apiPrototypeFetch(`/pricing/sku/${encSkuPath(s)}/pricing-records`);
    if (!res.ok) return [];
    const data = (await res.json()) as { items: PricingRecordApiRow[] };
    return data.items ?? [];
  } catch {
    return [];
  }
}

export async function loadPriceHistory(sku: string): Promise<PriceHistoryApiRow[]> {
  const s = sku.trim();
  if (!s) return [];
  try {
    const res = await apiPrototypeFetch(
      `/pricing/sku/${encSkuPath(s)}/price-history?limit=50`
    );
    if (!res.ok) return [];
    const data = (await res.json()) as { items: PriceHistoryApiRow[] };
    return data.items ?? [];
  } catch {
    return [];
  }
}

function num(value: FormDataEntryValue | null) {
  if (typeof value !== "string") return 0;
  return Number(value.replace(",", ".")) || 0;
}

function kind(value: FormDataEntryValue | null): PricingKind {
  return value === "1" ? 1 : 0;
}

export async function saveSkuPricing(
  _prev: PricingState,
  formData: FormData
): Promise<PricingState> {
  const rbac = await requireAdminForPricing();
  if (rbac) return rbac;

  const gate = await gateMutation();
  if (gate) return gate;

  const sku = String(formData.get("sku") || "").trim();
  if (!sku) return { ok: false, message: "Selecione um SKU." };

  const markupVal = num(formData.get("markup"));
  const taxesVal = num(formData.get("taxes"));
  const interestVal = num(formData.get("interest"));
  const markupKind = kind(formData.get("markup_kind"));
  const taxesKind = kind(formData.get("taxes_kind"));
  const interestKind = kind(formData.get("interest_kind"));

  const snap = await loadPricingSnapshot(sku);
  if (!snap || snap.sku_master.sku.trim() !== sku) {
    return { ok: false, message: "Não foi possível validar o SKU no servidor." };
  }
  const avgFromServer = Number(snap.sku_master.avg_unit_cost) || 0;
  if (avgFromServer <= 0) {
    return {
      ok: false,
      message:
        "O custo médio de estoque (CMP) não está disponível para este SKU. Registre entradas de estoque em Custos antes de precificar.",
    };
  }
  const pre = await postComputeTargetsApi({
    avgCost: avgFromServer,
    markupVal,
    taxesVal,
    interestVal,
    markupKind,
    taxesKind,
    interestKind,
  });
  if (!pre || pre.target <= 0) {
    return { ok: false, message: "O preço-alvo calculado deve ser maior que zero." };
  }

  try {
    const res = await apiPrototypeFetch("/pricing/sku/workflow", {
      method: "POST",
      json: {
        sku,
        markup_pct: markupVal,
        taxes_pct: taxesVal,
        interest_pct: interestVal,
        markup_kind: markupKind,
        taxes_kind: taxesKind,
        interest_kind: interestKind,
      },
    });
    if (!res.ok) {
      return { ok: false, message: await readApiError(res) };
    }
    await logPrototypeAuditEvent("pricing", "save_workflow", {
      sku,
      markup_pct: markupVal,
      taxes_pct: taxesVal,
      interest_pct: interestVal,
      markup_kind: markupKind,
      taxes_kind: taxesKind,
      interest_kind: interestKind,
    });
    revalidatePath("/pricing");
    revalidatePath("/products");
    revalidatePath("/inventory");
    return { ok: true, message: "Nova precificação ativada." };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao salvar precificação.",
    };
  }
}
