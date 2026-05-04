"use client";

import { useActionState } from "react";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { saveCostStructure, type CostState } from "@/lib/actions/costs";
import { SKU_COST_COMPONENT_DEFINITIONS } from "@/lib/domain";

const initialState: CostState = { ok: false, message: "" };

export function CostStructureForm({ skus }: { skus: string[] }) {
  const [state, formAction] = useActionState(saveCostStructure, initialState);

  return (
    <form action={formAction} className="space-y-4">
      <FormAlert state={state.message ? state : undefined} />

      <div className="space-y-2">
        <Label htmlFor="sku">SKU</Label>
        <Select id="sku" name="sku" defaultValue="">
          <option value="">— selecionar —</option>
          {skus.map((sku) => (
            <option key={sku} value={sku}>
              {sku}
            </option>
          ))}
        </Select>
      </div>

      <div className="space-y-3">
        {SKU_COST_COMPONENT_DEFINITIONS.map((component) => (
          <div key={component.key} className="grid gap-3 rounded-xl border border-border bg-muted/20 p-3 sm:grid-cols-[1fr_6rem_8rem]">
            <div>
              <p className="text-sm font-medium">{component.label}</p>
              <p className="text-xs text-muted-foreground">{component.key}</p>
            </div>
            <div className="space-y-1">
              <Label htmlFor={`qty_${component.key}`}>Qtd.</Label>
              <Input id={`qty_${component.key}`} name={`qty_${component.key}`} type="number" min={0} step="0.01" defaultValue={0} />
            </div>
            <div className="space-y-1">
              <Label htmlFor={`price_${component.key}`}>Preço unitário</Label>
              <Input id={`price_${component.key}`} name={`price_${component.key}`} type="number" min={0} step="0.01" defaultValue={0} />
            </div>
          </div>
        ))}
      </div>

      <div className="flex justify-end">
        <SubmitButton>Salvar composição</SubmitButton>
      </div>
    </form>
  );
}
