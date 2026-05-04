"use client";

import { useActionState } from "react";
import Link from "next/link";
import { Pencil } from "lucide-react";
import { ConfirmDeleteForm } from "@/components/confirm-delete-form";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Button } from "@/components/ui/button";
import { deleteCustomerForm, type CustomerFormState } from "@/lib/actions/customers";

const initial: CustomerFormState = { ok: false, message: "" };

export function CustomerRowActions({
  customerId,
  customerCode,
  name,
  isAdmin,
}: {
  customerId: number;
  customerCode: string;
  name: string;
  isAdmin: boolean;
}) {
  const [deleteState, deleteAction] = useActionState(deleteCustomerForm, initial);

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Button variant="ghost" size="sm" className="gap-1" asChild>
        <Link href={`/customers/${customerId}/edit`}>
          <Pencil className="h-3.5 w-3.5" />
          Editar
        </Link>
      </Button>
      {isAdmin ? (
        <ConfirmDeleteForm
          confirmMessage={`Eliminar definitivamente o cliente «${name}» (${customerCode})?`}
          action={deleteAction}
          className="inline-flex flex-col items-end gap-2"
        >
          <input type="hidden" name="customer_id" value={String(customerId)} />
          <FormAlert state={deleteState.message ? deleteState : undefined} />
          <SubmitButton
            type="submit"
            variant="outline"
            size="sm"
            className="border-red-500/50 text-red-400 hover:bg-red-500/10 hover:text-red-300"
          >
            Eliminar
          </SubmitButton>
        </ConfirmDeleteForm>
      ) : null}
    </div>
  );
}
