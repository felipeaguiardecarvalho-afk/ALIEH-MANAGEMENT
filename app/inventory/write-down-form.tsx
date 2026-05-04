"use client";

import { useActionState } from "react";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { manualWriteDown, type InventoryState } from "@/lib/actions/inventory";
import type { Product } from "@/lib/types";

const initialState: InventoryState = { ok: false, message: "" };

export function WriteDownForm({ lots }: { lots: Product[] }) {
  const [state, formAction] = useActionState(manualWriteDown, initialState);

  return (
    <form action={formAction} className="space-y-4">
      <FormAlert state={state.message ? state : undefined} />

      <div className="space-y-2">
        <Label htmlFor="product_id">Lote</Label>
        <Select id="product_id" name="product_id" defaultValue="">
          <option value="">— selecionar —</option>
          {lots.map((lot) => (
            <option key={lot.id} value={lot.id}>
              {lot.productEnterCode ?? `Lote ${lot.id}`} · {lot.name} · estoque {lot.stock}
            </option>
          ))}
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="quantity">Quantidade a baixar</Label>
        <Input id="quantity" name="quantity" type="number" min={1} step="1" defaultValue={1} />
      </div>

      <div className="pt-2">
        <SubmitButton>Aplicar baixa</SubmitButton>
      </div>
    </form>
  );
}
