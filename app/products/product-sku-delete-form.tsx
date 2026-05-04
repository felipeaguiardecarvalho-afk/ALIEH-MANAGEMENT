"use client";

import { useActionState, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ActionSuccessToast } from "@/components/action-success-toast";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Button } from "@/components/ui/button";
import { deleteProductSku, type LotActionState } from "@/lib/actions/products";

const initial: LotActionState = { ok: false, message: "" };

export function ProductSkuDeleteForm({
  sku,
  disabled,
  listReturnHref,
}: {
  sku: string;
  disabled: boolean;
  listReturnHref: string;
}) {
  const router = useRouter();
  const [state, formAction] = useActionState(deleteProductSku, initial);
  const [confirming, setConfirming] = useState(false);
  const [toastOpen, setToastOpen] = useState(false);
  const navScheduled = useRef(false);

  useEffect(() => {
    if (state.message && !state.ok) {
      setConfirming(false);
    }
  }, [state]);

  useEffect(() => {
    if (!state.ok || !state.message) {
      navScheduled.current = false;
      return;
    }
    if (navScheduled.current) return;
    navScheduled.current = true;
    setToastOpen(true);
    const t = window.setTimeout(() => {
      router.replace(listReturnHref);
    }, 3500);
    return () => {
      window.clearTimeout(t);
      navScheduled.current = false;
    };
  }, [state.ok, state.message, listReturnHref, router]);

  if (disabled) {
    return (
      <SubmitButton type="button" variant="outline" disabled className="border-red-500/30 opacity-60">
        Excluir SKU (bloqueado)
      </SubmitButton>
    );
  }

  if (!confirming) {
    return (
      <div className="space-y-3">
        <ActionSuccessToast
          message={state.ok && state.message ? state.message : ""}
          visible={toastOpen && Boolean(state.ok && state.message)}
          onDismiss={() => setToastOpen(false)}
          durationMs={4500}
        />
        <FormAlert state={!state.ok && state.message ? state : undefined} />
        <Button
          type="button"
          variant="outline"
          className="border-red-500/50 text-red-400 hover:bg-red-500/10 hover:text-red-300"
          onClick={() => setConfirming(true)}
        >
          Excluir SKU
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-lg border border-amber-500/35 bg-amber-500/[0.07] p-4">
      <ActionSuccessToast
        message={state.ok && state.message ? state.message : ""}
        visible={toastOpen && Boolean(state.ok && state.message)}
        onDismiss={() => setToastOpen(false)}
        durationMs={4500}
      />
      <p className="text-sm text-foreground">
        Confirma a <strong>exclusão permanente</strong> de <strong>todos os lotes</strong> e do <strong>mestre</strong>{" "}
        deste SKU na base de dados? Não há como desfazer pelo aplicativo.
      </p>
      <FormAlert state={!state.ok && state.message ? state : undefined} />
      <form action={formAction} className="flex flex-wrap gap-2">
        <input type="hidden" name="sku" value={sku} />
        <SubmitButton
          type="submit"
          variant="default"
          className="bg-red-600 text-white hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-800"
        >
          Sim, excluir SKU
        </SubmitButton>
        <Button type="button" variant="outline" onClick={() => setConfirming(false)}>
          Cancelar
        </Button>
      </form>
    </div>
  );
}
