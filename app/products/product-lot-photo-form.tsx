"use client";

import { useActionState, useEffect, useRef, useState } from "react";
import { ActionSuccessToast } from "@/components/action-success-toast";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { updateProductLotPhoto, type LotActionState } from "@/lib/actions/products";

const initial: LotActionState = { ok: false, message: "" };

export function ProductLotPhotoForm({
  productId,
  disabled,
}: {
  productId: number;
  disabled: boolean;
}) {
  const [state, formAction] = useActionState(updateProductLotPhoto, initial);
  const [toastOpen, setToastOpen] = useState(false);
  const lastSig = useRef("");

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
    <section className="space-y-3 border-t border-border/60 pt-6">
      <h3 className="text-sm font-medium text-foreground">Substituir foto do lote</h3>
      <p className="text-xs text-muted-foreground">
        JPG, PNG ou WebP até 8 MB. A foto pode ser substituída mesmo quando o lote está bloqueado para edição de
        atributos (paridade com Streamlit).
      </p>
      {disabled ? (
        <p className="text-xs text-amber-600/90 dark:text-amber-400/90">
          Apenas administradores podem substituir a foto deste lote.
        </p>
      ) : null}
      <form action={formAction} className="space-y-3">
        <input type="hidden" name="product_id" value={String(productId)} />
        <ActionSuccessToast
          message={state.ok && state.message ? state.message : ""}
          visible={toastOpen && Boolean(state.ok && state.message)}
          onDismiss={() => setToastOpen(false)}
          durationMs={4500}
        />
        <FormAlert state={!state.ok && state.message ? state : undefined} />
        <div className="space-y-2">
          <Label htmlFor={`lot-photo-${productId}`}>Nova imagem</Label>
          <Input
            id={`lot-photo-${productId}`}
            name="photo"
            type="file"
            accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
            disabled={disabled}
            required={!disabled}
          />
        </div>
        <SubmitButton type="submit" disabled={disabled}>
          Gravar nova foto
        </SubmitButton>
      </form>
    </section>
  );
}
