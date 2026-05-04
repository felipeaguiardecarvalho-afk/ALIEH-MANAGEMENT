"use server";

import { revalidatePath } from "next/cache";
import { db, getTenantId, hasDatabaseUrl } from "@/lib/db";

export type InventoryState = { ok: boolean; message: string };

function num(value: FormDataEntryValue | null) {
  if (typeof value !== "string") return 0;
  return Number(value.replace(",", ".")) || 0;
}

/**
 * Equivalente a `services.product_service.apply_manual_stock_write_down`.
 * Apenas reduz `products.stock`; custo e preço inalterados.
 */
export async function manualWriteDown(
  _prev: InventoryState,
  formData: FormData
): Promise<InventoryState> {
  if (!hasDatabaseUrl) return { ok: false, message: "Banco não configurado." };

  const productId = Number(formData.get("product_id"));
  const qty = num(formData.get("quantity"));

  if (!productId) return { ok: false, message: "Selecione um lote." };
  if (qty <= 0) return { ok: false, message: "Quantidade inválida." };

  const tenantId = getTenantId();

  try {
    const sql = db();
    await sql.begin(async (tx) => {
      const [product] = await tx`
        SELECT stock, sku FROM products
        WHERE tenant_id = ${tenantId} AND id = ${productId}
        LIMIT 1;
      `;
      if (!product) throw new Error("Lote não encontrado.");
      const currentStock = Number(product.stock || 0);
      if (currentStock < qty) {
        throw new Error(`Estoque insuficiente (atual: ${currentStock}).`);
      }

      await tx`
        UPDATE products SET stock = stock - ${qty}
        WHERE tenant_id = ${tenantId} AND id = ${productId};
      `;
      if (product.sku) {
        await tx`
          UPDATE sku_master
          SET total_stock = GREATEST(0, total_stock - ${qty}),
              updated_at = ${new Date().toISOString()}
          WHERE tenant_id = ${tenantId} AND sku = ${product.sku};
        `;
      }
    });

    revalidatePath("/inventory");
    revalidatePath("/dashboard");
    return { ok: true, message: `Baixa de ${qty} unidade(s) aplicada.` };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha na baixa de estoque.",
    };
  }
}

/**
 * Equivalente a `services.product_service.add_stock_receipt`:
 * entrada de estoque com custo médio ponderado em `sku_master` e `products`.
 */
export async function addStockReceipt(
  _prev: InventoryState,
  formData: FormData
): Promise<InventoryState> {
  if (!hasDatabaseUrl) return { ok: false, message: "Banco não configurado." };

  const sku = String(formData.get("sku") || "").trim();
  const productId = Number(formData.get("product_id"));
  const qty = num(formData.get("quantity"));
  const unitCost = num(formData.get("unit_cost"));

  if (!sku || !productId) return { ok: false, message: "SKU e lote são obrigatórios." };
  if (qty <= 0 || unitCost <= 0) {
    return { ok: false, message: "Quantidade e custo unitário devem ser maiores que zero." };
  }

  const tenantId = getTenantId();
  try {
    const sql = db();
    await sql.begin(async (tx) => {
      const [master] = await tx`
        SELECT COALESCE(total_stock, 0) AS total_stock,
               COALESCE(avg_unit_cost, 0) AS avg_unit_cost
        FROM sku_master
        WHERE tenant_id = ${tenantId} AND sku = ${sku}
        LIMIT 1;
      `;
      const prevStock = Number(master?.total_stock || 0);
      const prevCost = Number(master?.avg_unit_cost || 0);
      const newStock = prevStock + qty;
      const newCost = newStock > 0 ? (prevStock * prevCost + qty * unitCost) / newStock : unitCost;

      await tx`
        INSERT INTO stock_cost_entries (
          tenant_id, sku, product_id, quantity, unit_cost,
          stock_before, stock_after, avg_cost_before, avg_cost_after, created_at
        ) VALUES (
          ${tenantId}, ${sku}, ${productId}, ${qty}, ${unitCost},
          ${prevStock}, ${newStock}, ${prevCost}, ${newCost},
          ${new Date().toISOString()}
        );
      `;

      await tx`
        UPDATE products SET stock = stock + ${qty}, cost = ${newCost}
        WHERE tenant_id = ${tenantId} AND id = ${productId};
      `;

      await tx`
        INSERT INTO sku_master (tenant_id, sku, total_stock, avg_unit_cost, selling_price, structured_cost_total, updated_at)
        VALUES (${tenantId}, ${sku}, ${newStock}, ${newCost}, 0, 0, ${new Date().toISOString()})
        ON CONFLICT (tenant_id, sku)
        DO UPDATE SET total_stock = ${newStock}, avg_unit_cost = ${newCost},
                      updated_at = ${new Date().toISOString()};
      `;
    });

    revalidatePath("/inventory");
    revalidatePath("/costs");
    revalidatePath("/dashboard");
    return { ok: true, message: `Entrada registrada: +${qty} un. a R$ ${unitCost.toFixed(2)}/un.` };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao registrar entrada.",
    };
  }
}
