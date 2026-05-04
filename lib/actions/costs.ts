"use server";

import { revalidatePath } from "next/cache";
import { db, getTenantId, hasDatabaseUrl } from "@/lib/db";
import { SKU_COST_COMPONENT_DEFINITIONS } from "@/lib/domain";

export type CostState = { ok: boolean; message: string };

function num(value: FormDataEntryValue | null) {
  if (typeof value !== "string") return 0;
  return Number(value.replace(",", ".")) || 0;
}

/**
 * Equivalente a `services.product_service.save_sku_cost_structure`:
 * persiste componentes por (tenant, sku, component_key) e recomputa
 * `sku_master.structured_cost_total`.
 */
export async function saveCostStructure(
  _prev: CostState,
  formData: FormData
): Promise<CostState> {
  if (!hasDatabaseUrl) return { ok: false, message: "Banco não configurado." };

  const sku = String(formData.get("sku") || "").trim();
  if (!sku) return { ok: false, message: "Selecione um SKU." };

  const tenantId = getTenantId();
  const now = new Date().toISOString();
  const inputs = SKU_COST_COMPONENT_DEFINITIONS.map((component) => ({
    key: component.key,
    label: component.label,
    unitPrice: num(formData.get(`price_${component.key}`)),
    quantity: num(formData.get(`qty_${component.key}`)),
  }));

  try {
    const sql = db();
    await sql.begin(async (tx) => {
      for (const input of inputs) {
        const lineTotal = Math.round(input.unitPrice * input.quantity * 100) / 100;
        await tx`
          INSERT INTO sku_cost_components (
            tenant_id, sku, component_key, label, unit_price, quantity, line_total, updated_at
          ) VALUES (
            ${tenantId}, ${sku}, ${input.key}, ${input.label}, ${input.unitPrice}, ${input.quantity}, ${lineTotal}, ${now}
          )
          ON CONFLICT (tenant_id, sku, component_key)
          DO UPDATE SET
            label = EXCLUDED.label,
            unit_price = EXCLUDED.unit_price,
            quantity = EXCLUDED.quantity,
            line_total = EXCLUDED.line_total,
            updated_at = EXCLUDED.updated_at;
        `;
      }

      const [sumRow] = await tx`
        SELECT COALESCE(SUM(line_total), 0) AS t
        FROM sku_cost_components
        WHERE tenant_id = ${tenantId} AND sku = ${sku};
      `;
      const total = Number(sumRow?.t ?? 0);

      await tx`
        UPDATE sku_master
        SET structured_cost_total = ${total}, updated_at = ${now}
        WHERE tenant_id = ${tenantId} AND sku = ${sku};
      `;
    });

    revalidatePath("/costs");
    return { ok: true, message: "Composição de custo salva." };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao salvar composição.",
    };
  }
}
