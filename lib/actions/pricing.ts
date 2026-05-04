"use server";

import { revalidatePath } from "next/cache";
import { db, getTenantId, hasDatabaseUrl } from "@/lib/db";
import { computePricingTargets, type PricingKind } from "@/lib/pricing";

export type PricingState = { ok: boolean; message: string };

function num(value: FormDataEntryValue | null) {
  if (typeof value !== "string") return 0;
  return Number(value.replace(",", ".")) || 0;
}

function kind(value: FormDataEntryValue | null): PricingKind {
  return value === "1" ? 1 : 0;
}

/**
 * Equivalente a `services.product_service.save_sku_pricing_workflow`:
 *  - desativa registros anteriores do SKU
 *  - insere novo registro ativo
 *  - propaga preço para `sku_master.selling_price` e `products.price`
 * Cálculo idêntico a `compute_sku_pricing_targets`.
 */
export async function saveSkuPricing(
  _prev: PricingState,
  formData: FormData
): Promise<PricingState> {
  if (!hasDatabaseUrl) return { ok: false, message: "Banco não configurado." };

  const sku = String(formData.get("sku") || "").trim();
  if (!sku) return { ok: false, message: "Selecione um SKU." };

  const markupVal = num(formData.get("markup"));
  const taxesVal = num(formData.get("taxes"));
  const interestVal = num(formData.get("interest"));
  const markupKind = kind(formData.get("markup_kind"));
  const taxesKind = kind(formData.get("taxes_kind"));
  const interestKind = kind(formData.get("interest_kind"));

  const tenantId = getTenantId();
  const now = new Date().toISOString();

  try {
    const sql = db();
    await sql.begin(async (tx) => {
      const [master] = await tx`
        SELECT COALESCE(avg_unit_cost, 0) AS avg_unit_cost
        FROM sku_master
        WHERE tenant_id = ${tenantId} AND sku = ${sku}
        LIMIT 1;
      `;
      if (!master) throw new Error("SKU não encontrado no mestre.");
      const avgCost = Number(master.avg_unit_cost || 0);
      if (avgCost <= 0) {
        throw new Error("CMP zero — registre uma entrada de estoque antes de precificar.");
      }

      const targets = computePricingTargets(
        avgCost,
        markupVal,
        taxesVal,
        interestVal,
        { markupKind, taxesKind, interestKind }
      );
      if (targets.targetPrice <= 0) {
        throw new Error("Preço alvo inválido (<= 0).");
      }

      await tx`
        UPDATE sku_pricing_records
        SET is_active = 0
        WHERE tenant_id = ${tenantId} AND sku = ${sku} AND is_active = 1;
      `;

      await tx`
        INSERT INTO sku_pricing_records (
          tenant_id, sku, avg_cost_snapshot, markup_pct, taxes_pct, interest_pct,
          price_before_taxes, price_with_taxes, target_price,
          is_active, created_at, markup_kind, taxes_kind, interest_kind
        ) VALUES (
          ${tenantId}, ${sku}, ${avgCost}, ${markupVal}, ${taxesVal}, ${interestVal},
          ${targets.priceBefore}, ${targets.priceWithTaxes}, ${targets.targetPrice},
          1, ${now}, ${markupKind}, ${taxesKind}, ${interestKind}
        );
      `;

      await tx`
        UPDATE sku_master
        SET selling_price = ${targets.targetPrice}, updated_at = ${now}
        WHERE tenant_id = ${tenantId} AND sku = ${sku};
      `;

      await tx`
        UPDATE products
        SET price = ${targets.targetPrice}
        WHERE tenant_id = ${tenantId} AND sku = ${sku} AND deleted_at IS NULL;
      `;

      await tx`
        INSERT INTO price_history (tenant_id, sku, price, created_at, note)
        VALUES (${tenantId}, ${sku}, ${targets.targetPrice}, ${now}, 'pricing_workflow');
      `;
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
