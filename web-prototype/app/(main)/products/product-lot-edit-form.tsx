"use client";

import { useActionState, useEffect, useRef, useState } from "react";
import { ActionSuccessToast } from "@/components/action-success-toast";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { AttributeSelectWithOther } from "@/components/attribute-select-with-other";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { updateProductLotAttributes, type LotActionState } from "@/lib/actions/products";
import type { ProductAttributeOptions, ProductDetail } from "@/lib/products-api";
import { MarkdownHint } from "./product-markdown-hint";

function opt(values: string[], fallback: string | null | undefined) {
  const set = new Set(values.filter(Boolean));
  if (fallback?.trim()) set.add(fallback.trim());
  return Array.from(set).sort((a, b) => a.localeCompare(b, "pt"));
}

function registeredDateInputValue(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = iso.trim();
  if (!s) return "";
  return s.slice(0, 10);
}

export function ProductLotEditForm({
  product,
  options,
  initialState,
}: {
  product: ProductDetail;
  options: ProductAttributeOptions;
  initialState: LotActionState;
}) {
  const [state, formAction] = useActionState(updateProductLotAttributes, initialState);
  const [toastOpen, setToastOpen] = useState(false);
  const lastSig = useRef("");
  const pid = product.id;
  const block = product.lot_edit_block_reason?.trim() || null;

  useEffect(() => {
    if (!state.ok) {
      lastSig.current = "";
      return;
    }
    if (!state.message) return;
    const sig = `${state.ok}:${state.message}`;
    if (sig === lastSig.current) return;
    lastSig.current = sig;
    setToastOpen(true);
  }, [state]);

  return (
    <section className="space-y-4 border-t border-border/60 pt-6">
      <h3 className="text-sm font-medium text-foreground">Editar produto (lote)</h3>
      <p className="text-xs text-muted-foreground">
        O SKU é derivado no servidor a partir do nome e dos atributos. Use &quot;Outro…&quot; para valores fora da
        lista.
      </p>
      {block ? (
        <div className="rounded-lg border border-[#c7a35b]/30 bg-muted/30 px-3 py-2 text-xs text-muted-foreground [&_strong]:text-foreground">
          <MarkdownHint text={block} />
        </div>
      ) : (
        <form action={formAction} className="space-y-4">
          <input type="hidden" name="product_id" value={String(product.id)} />
          <ActionSuccessToast
            message={state.ok && state.message ? state.message : ""}
            visible={toastOpen && Boolean(state.ok && state.message)}
            onDismiss={() => setToastOpen(false)}
            durationMs={4500}
          />
          <FormAlert state={!state.ok && state.message ? state : undefined} />
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor={`prod-edit-name-${pid}`}>Nome do produto</Label>
              <Input
                id={`prod-edit-name-${pid}`}
                name="name"
                defaultValue={product.name}
                required
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor={`prod-edit-reg-${pid}`}>Data de registo</Label>
              <Input
                id={`prod-edit-reg-${pid}`}
                name="registered_date"
                type="date"
                defaultValue={registeredDateInputValue(product.registered_date)}
                required
              />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <AttributeSelectWithOther
              key={`${pid}-frame_color`}
              name="frame_color"
              label="Cor da armação"
              presetOptions={opt(options.frame_color, product.frame_color)}
              initialValue={product.frame_color}
              emptyLabel="— vazio —"
            />
            <AttributeSelectWithOther
              key={`${pid}-lens_color`}
              name="lens_color"
              label="Cor da lente"
              presetOptions={opt(options.lens_color, product.lens_color)}
              initialValue={product.lens_color}
              emptyLabel="— vazio —"
            />
            <AttributeSelectWithOther
              key={`${pid}-gender`}
              name="gender"
              label="Gênero"
              presetOptions={opt(options.gender, product.gender)}
              initialValue={product.gender}
              emptyLabel="— vazio —"
            />
            <AttributeSelectWithOther
              key={`${pid}-palette`}
              name="palette"
              label="Paleta"
              presetOptions={opt(options.palette, product.palette)}
              initialValue={product.palette}
              emptyLabel="— vazio —"
            />
            <AttributeSelectWithOther
              key={`${pid}-style`}
              name="style"
              label="Estilo"
              presetOptions={opt(options.style, product.style)}
              initialValue={product.style}
              emptyLabel="— vazio —"
            />
          </div>
          <SubmitButton type="submit">Salvar alterações nos dados do lote</SubmitButton>
        </form>
      )}
    </section>
  );
}
