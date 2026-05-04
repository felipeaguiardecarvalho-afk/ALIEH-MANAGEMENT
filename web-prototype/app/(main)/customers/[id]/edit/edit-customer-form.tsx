"use client";

import { useActionState, useCallback, useOptimistic } from "react";
import Link from "next/link";
import { ShieldAlert, Trash2 } from "lucide-react";
import { CustomerCepBlock } from "@/components/customer-cep-block";
import { ConfirmDeleteForm } from "@/components/confirm-delete-form";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  deleteCustomerForm,
  updateCustomer,
  type CustomerFormState,
} from "@/lib/actions/customers";
import type { CustomerApiRow } from "@/lib/customers-api";

const initialState: CustomerFormState = { ok: false, message: "" };

function mergeCustomerFormState(
  prev: CustomerFormState,
  patch: Partial<CustomerFormState>
): CustomerFormState {
  return { ...prev, ...patch };
}

export function EditCustomerForm({
  customer,
  isAdmin,
}: {
  customer: CustomerApiRow;
  isAdmin: boolean;
}) {
  // ───── Logic preserved verbatim ─────
  const [state, serverUpdate] = useActionState(updateCustomer, initialState);
  const [display, addOptimistic] = useOptimistic(state, mergeCustomerFormState);
  const [deleteState, deleteAction] = useActionState(deleteCustomerForm, initialState);

  const formAction = useCallback(
    (fd: FormData) => {
      addOptimistic({ ok: false, message: "A guardar alterações no servidor…" });
      return serverUpdate(fd);
    },
    [serverUpdate, addOptimistic]
  );

  return (
    <div className="space-y-12">
      <form action={formAction} className="space-y-10">
        <input type="hidden" name="customer_id" value={String(customer.id)} />
        <FormAlert state={display.message ? display : undefined} />

        {/* Section 1: Identification */}
        <FormSection eyebrow="01 · Identificação" title="Quem é o cliente">
          <div className="space-y-1.5">
            <Label className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Código</Label>
            <Input value={customer.customer_code} readOnly className="h-10 bg-muted/40 font-mono text-xs" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="name" className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              Nome *
            </Label>
            <Input
              id="name"
              name="name"
              required
              defaultValue={customer.name}
              autoComplete="off"
              className="h-12 border-0 border-b border-border/60 bg-transparent px-0 font-serif text-2xl tracking-tight shadow-none focus-visible:border-[#c7a35b]/60 focus-visible:ring-0"
            />
          </div>
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            <Field label="CPF" name="cpf" defaultValue={customer.cpf ?? ""} placeholder="000.000.000-00" />
            <Field label="RG" name="rg" defaultValue={customer.rg ?? ""} />
            <Field label="Telefone" name="phone" defaultValue={customer.phone ?? ""} placeholder="(11) 9..." />
            <Field
              label="Email"
              name="email"
              type="email"
              defaultValue={customer.email ?? ""}
              placeholder="cliente@exemplo.com"
            />
            <Field label="Instagram" name="instagram" defaultValue={customer.instagram ?? ""} placeholder="@handle" />
          </div>
        </FormSection>

        {/* Section 2: Address */}
        <FormSection eyebrow="02 · Endereço" title="ViaCEP preenche automaticamente">
          <CustomerCepBlock
            initialZipCode={customer.zip_code ?? ""}
            addressDefaults={{
              street: customer.street ?? "",
              number: customer.number ?? "",
              neighborhood: customer.neighborhood ?? "",
              city: customer.city ?? "",
              state: customer.state ?? "",
              country: customer.country ?? "Brasil",
            }}
          />
        </FormSection>

        <div className="flex items-center justify-end gap-3 border-t border-border/40 pt-6">
          <Button type="button" variant="ghost" asChild>
            <Link href="/customers">Cancelar</Link>
          </Button>
          <SubmitButton blockWhilePending={false}>Guardar alterações</SubmitButton>
        </div>
      </form>

      {/* Danger zone — admin only */}
      {isAdmin ? (
        <section className="space-y-4 border-t border-destructive/30 pt-8">
          <header className="flex items-center gap-2">
            <ShieldAlert className="h-3.5 w-3.5 text-destructive/80" />
            <p className="text-[10px] uppercase tracking-[0.28em] text-destructive/90">Zona crítica</p>
          </header>
          <p className="max-w-2xl text-xs leading-5 text-muted-foreground">
            Eliminação permanente. A operação falha se existirem vendas vinculadas a este cliente (regra do
            serviço). Operação irreversível.
          </p>
          <ConfirmDeleteForm
            confirmMessage={`Eliminar definitivamente o cliente «${customer.name}» (${customer.customer_code})?`}
            action={deleteAction}
            className="space-y-3"
          >
            <input type="hidden" name="customer_id" value={String(customer.id)} />
            <FormAlert state={deleteState.message ? deleteState : undefined} />
            <SubmitButton
              type="submit"
              variant="outline"
              className="gap-2 border-destructive/50 text-destructive hover:bg-destructive/10 hover:text-destructive"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Eliminar cliente
            </SubmitButton>
          </ConfirmDeleteForm>
        </section>
      ) : null}
    </div>
  );
}

function FormSection({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-5">
      <header className="space-y-1">
        <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">{eyebrow}</p>
        <h2 className="font-serif text-2xl font-semibold tracking-tight">{title}</h2>
      </header>
      {children}
    </section>
  );
}

function Field({
  label,
  name,
  type = "text",
  defaultValue,
  required,
  maxLength,
  placeholder,
}: {
  label: string;
  name: string;
  type?: string;
  defaultValue?: string;
  required?: boolean;
  maxLength?: number;
  placeholder?: string;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={name} className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </Label>
      <Input
        id={name}
        name={name}
        type={type}
        defaultValue={defaultValue}
        required={required}
        maxLength={maxLength}
        placeholder={placeholder}
        className="h-10"
      />
    </div>
  );
}
