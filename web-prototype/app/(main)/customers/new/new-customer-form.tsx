"use client";

import Link from "next/link";
import { useActionState, useCallback, useOptimistic } from "react";
import { CustomerCepBlock } from "@/components/customer-cep-block";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createCustomer, type CustomerFormState } from "@/lib/actions/customers";

const initialState: CustomerFormState = { ok: false, message: "" };

function mergeCustomerFormState(
  prev: CustomerFormState,
  patch: Partial<CustomerFormState>
): CustomerFormState {
  return { ...prev, ...patch };
}

export function NewCustomerForm() {
  // ───── Logic preserved verbatim ─────
  const [state, serverAction] = useActionState(createCustomer, initialState);
  const [display, addOptimistic] = useOptimistic(state, mergeCustomerFormState);

  const formAction = useCallback(
    (fd: FormData) => {
      addOptimistic({ ok: false, message: "A registar cliente no servidor…" });
      return serverAction(fd);
    },
    [serverAction, addOptimistic]
  );

  return (
    <form action={formAction} className="space-y-10">
      <FormAlert state={display.message ? display : undefined} />

      {/* Section 1: Identification */}
      <FormSection eyebrow="01 · Identificação" title="Quem é o cliente">
        {/* Name — dominant */}
        <div className="space-y-1.5">
          <Label htmlFor="name" className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            Nome *
          </Label>
          <Input
            id="name"
            name="name"
            required
            autoComplete="off"
            placeholder="Nome completo"
            className="h-12 border-0 border-b border-border/60 bg-transparent px-0 font-serif text-2xl tracking-tight shadow-none focus-visible:border-[#c7a35b]/60 focus-visible:ring-0"
          />
        </div>
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          <Field label="CPF" name="cpf" placeholder="000.000.000-00" />
          <Field label="RG" name="rg" />
          <Field label="Telefone" name="phone" placeholder="(11) 9..." />
          <Field label="Email" name="email" type="email" placeholder="cliente@exemplo.com" />
          <Field label="Instagram" name="instagram" placeholder="@handle" />
        </div>
      </FormSection>

      {/* Section 2: Address (ViaCEP) */}
      <FormSection eyebrow="02 · Endereço" title="ViaCEP preenche automaticamente">
        <CustomerCepBlock />
      </FormSection>

      <div className="flex items-center justify-end gap-3 border-t border-border/40 pt-6">
        <Button type="button" variant="ghost" asChild>
          <Link href="/customers">Cancelar</Link>
        </Button>
        <SubmitButton blockWhilePending={false}>Salvar cliente</SubmitButton>
      </div>
    </form>
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
