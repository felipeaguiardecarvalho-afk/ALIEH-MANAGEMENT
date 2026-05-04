"use server";

import { revalidatePath } from "next/cache";
import { db, getTenantId, hasDatabaseUrl } from "@/lib/db";
import { SALE_PAYMENT_OPTIONS } from "@/lib/domain";

export type SaleFormState = { ok: boolean; message: string };

function num(value: FormDataEntryValue | null) {
  if (typeof value !== "string") return 0;
  return Number(value.replace(",", ".")) || 0;
}

function str(value: FormDataEntryValue | null) {
  return typeof value === "string" ? value.trim() : "";
}

/**
 * Transação equivalente a `services.sales_service.record_sale` +
 * `insert_sale_and_decrement_stock`:
 *   - valida cliente/produto/estoque
 *   - lê preço de venda e CMP de `sku_master`
 *   - grava `sales` com `sale_code` sequencial e decrementa `products.stock`
 *   - sincroniza `sku_master.total_stock`
 */
export async function recordSale(
  _prev: SaleFormState,
  formData: FormData
): Promise<SaleFormState> {
  if (!hasDatabaseUrl) {
    return { ok: false, message: "Banco não configurado." };
  }

  const productId = Number(str(formData.get("product_id")));
  const customerId = Number(str(formData.get("customer_id")));
  const quantity = Math.max(1, Math.floor(num(formData.get("quantity"))));
  const discountAmount = Math.max(0, num(formData.get("discount_amount")));
  const paymentMethod = str(formData.get("payment_method")) as (typeof SALE_PAYMENT_OPTIONS)[number];

  if (!productId || !customerId) {
    return { ok: false, message: "Selecione produto e cliente." };
  }
  if (!SALE_PAYMENT_OPTIONS.includes(paymentMethod)) {
    return { ok: false, message: "Forma de pagamento inválida." };
  }

  const tenantId = getTenantId();

  try {
    const sql = db();
    let saleCode = "";
    let finalTotal = 0;

    await sql.begin(async (tx) => {
      const [customer] = await tx`
        SELECT id FROM customers
        WHERE tenant_id = ${tenantId} AND id = ${customerId}
        LIMIT 1;
      `;
      if (!customer) throw new Error("Cliente não encontrado.");

      const [product] = await tx`
        SELECT id, sku, stock FROM products
        WHERE tenant_id = ${tenantId} AND id = ${productId} AND deleted_at IS NULL
        LIMIT 1;
      `;
      if (!product) throw new Error("Produto não encontrado.");
      const stock = Number(product.stock || 0);
      if (stock < quantity) throw new Error(`Estoque insuficiente (atual: ${stock}).`);

      const sku = String(product.sku || "");
      const [master] = await tx`
        SELECT COALESCE(selling_price, 0) AS selling_price,
               COALESCE(avg_unit_cost, 0) AS avg_unit_cost
        FROM sku_master
        WHERE tenant_id = ${tenantId} AND sku = ${sku}
        LIMIT 1;
      `;
      const sellingPrice = Number(master?.selling_price || 0);
      const avgUnitCost = Number(master?.avg_unit_cost || 0);
      if (sellingPrice <= 0) throw new Error("SKU sem preço de venda ativo.");

      const gross = sellingPrice * quantity;
      finalTotal = Math.max(0, gross - discountAmount);
      const cogsTotal = avgUnitCost * quantity;

      const [seq] = await tx`
        INSERT INTO sale_sequence_counter (tenant_id, id, last_value)
        VALUES (${tenantId}, 1, 1)
        ON CONFLICT (tenant_id, id)
        DO UPDATE SET last_value = sale_sequence_counter.last_value + 1
        RETURNING last_value;
      `;
      const seqNum = Number(seq?.last_value ?? 1);
      saleCode = `${String(seqNum).padStart(5, "0")}V`;

      await tx`
        INSERT INTO sales (
          tenant_id, product_id, quantity, total, sold_at, cogs_total, sku,
          sale_code, customer_id, unit_price, discount_amount, base_amount, payment_method
        ) VALUES (
          ${tenantId}, ${productId}, ${quantity}, ${finalTotal},
          ${new Date().toISOString()}, ${cogsTotal}, ${sku},
          ${saleCode}, ${customerId}, ${sellingPrice}, ${discountAmount},
          ${gross}, ${paymentMethod}
        );
      `;

      await tx`
        UPDATE products SET stock = stock - ${quantity}
        WHERE tenant_id = ${tenantId} AND id = ${productId};
      `;

      await tx`
        UPDATE sku_master
        SET total_stock = GREATEST(0, total_stock - ${quantity}),
            updated_at = ${new Date().toISOString()}
        WHERE tenant_id = ${tenantId} AND sku = ${sku};
      `;
    });

    revalidatePath("/sales");
    revalidatePath("/dashboard");
    revalidatePath("/inventory");
    return { ok: true, message: `Venda ${saleCode} registrada. Total: R$ ${finalTotal.toFixed(2)}` };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao registrar venda.",
    };
  }
}
