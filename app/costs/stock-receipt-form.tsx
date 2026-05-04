"use client";

import { useActionState, useMemo, useState } from "react";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { addStockReceipt, type InventoryState } from "@/lib/actions/inventory";
import type { Product } from "@/lib/types";

const initialState: InventoryState = { ok: false, message: "" };

export function StockReceiptForm({ products }: { products: Product[] }) {
  const [state, formAction] = useActionState(addStockReceipt, initialState);
  const uniqueSkus = useMemo(() => {
    const set = new Set<string>();
    products.forEach((product) => {
      if (product.sku) set.add(product.sku);
    });
    return Array.from(set).sort();
  }, [products]);
  const [sku, setSku] = useState(uniqueSkus[0] ?? "");

  const batches = products.filter((product) => product.sku === sku);

  return (
    <form action={formAction} className="space-y-4">
      <FormAlert state={state.message ? state : undefined} />

      <div className="space-y-2">
        <Label htmlFor="sku">SKU destino</Label>
        <Select
          id="sku"
          name="sku"
          value={sku}
          onChange={(event) => setSku(event.target.value)}
        >
          {uniqueSkus.length === 0 ? <option value="">Nenhum SKU cadastrado</option> : null}
          {uniqueSkus.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="product_id">Lote destinatário</Label>
        <Select id="product_id" name="product_id" defaultValue="">
          <option value="">— selecionar —</option>
          {batches.map((batch) => (
            <option key={batch.id} value={batch.id}>
              {batch.productEnterCode ?? `Lote ${batch.id}`} — estoque atual {batch.stock}
            </option>
          ))}
        </Select>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="quantity">Quantidade</Label>
          <Input id="quantity" name="quantity" type="number" min={1} step="1" defaultValue={1} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="unit_cost">Custo unitário (R$)</Label>
          <Input id="unit_cost" name="unit_cost" type="number" min={0} step="0.01" defaultValue={0} />
        </div>
      </div>

      <div className="flex justify-end">
        <SubmitButton>Registrar entrada</SubmitButton>
      </div>
    </form>
  );
}
