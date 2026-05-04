"use client";

import { useActionState, useState, useTransition } from "react";
import { Search } from "lucide-react";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createCustomer, type CustomerFormState } from "@/lib/actions/customers";

const initialState: CustomerFormState = { ok: false, message: "" };

type CepAddress = {
  logradouro: string;
  bairro: string;
  localidade: string;
  uf: string;
  erro?: boolean;
};

export function NewCustomerForm() {
  const [state, formAction] = useActionState(createCustomer, initialState);
  const [cep, setCep] = useState("");
  const [cepError, setCepError] = useState<string | null>(null);
  const [address, setAddress] = useState<Partial<CepAddress>>({});
  const [pending, startTransition] = useTransition();

  async function lookupCep() {
    const digits = cep.replace(/\D/g, "");
    if (digits.length !== 8) {
      setCepError("CEP precisa ter 8 dígitos.");
      return;
    }
    setCepError(null);
    startTransition(async () => {
      try {
        const res = await fetch(`https://viacep.com.br/ws/${digits}/json/`);
        const data = (await res.json()) as CepAddress;
        if (data.erro) {
          setCepError("CEP não encontrado.");
          return;
        }
        setAddress(data);
      } catch {
        setCepError("Falha na busca do CEP.");
      }
    });
  }

  return (
    <form action={formAction} className="space-y-6">
      <FormAlert state={state.message ? state : undefined} />

      <div className="grid gap-5 md:grid-cols-2">
        <Field label="Nome *" name="name" required />
        <Field label="CPF" name="cpf" />
        <Field label="RG" name="rg" />
        <Field label="Telefone" name="phone" />
        <Field label="Email" name="email" type="email" />
        <Field label="Instagram" name="instagram" />
      </div>

      <div className="rounded-2xl border border-border bg-muted/20 p-4">
        <Label className="text-[#d4b36c]">Endereço</Label>
        <div className="mt-3 grid gap-4 md:grid-cols-[1fr_auto]">
          <div className="space-y-2">
            <Label htmlFor="cep_lookup">CEP</Label>
            <Input
              id="cep_lookup"
              name="zip_code"
              value={cep}
              onChange={(event) => setCep(event.target.value)}
              placeholder="00000-000"
            />
            {cepError ? <p className="text-xs text-red-400">{cepError}</p> : null}
          </div>
          <div className="flex items-end">
            <Button type="button" variant="outline" onClick={lookupCep} disabled={pending}>
              <Search className="h-4 w-4" />
              {pending ? "Buscando..." : "Buscar CEP"}
            </Button>
          </div>
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="Rua" name="street" defaultValue={address.logradouro || ""} key={`street-${address.logradouro || ""}`} />
          <Field label="Número" name="number" />
          <Field label="Bairro" name="neighborhood" defaultValue={address.bairro || ""} key={`b-${address.bairro || ""}`} />
          <Field label="Cidade" name="city" defaultValue={address.localidade || ""} key={`c-${address.localidade || ""}`} />
          <Field label="Estado (UF)" name="state" maxLength={2} defaultValue={address.uf || ""} key={`uf-${address.uf || ""}`} />
          <Field label="País" name="country" defaultValue="Brasil" />
        </div>
      </div>

      <div className="flex justify-end">
        <SubmitButton>Salvar cliente</SubmitButton>
      </div>
    </form>
  );
}

function Field({
  label,
  name,
  type = "text",
  defaultValue,
  required,
  maxLength,
}: {
  label: string;
  name: string;
  type?: string;
  defaultValue?: string;
  required?: boolean;
  maxLength?: number;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={name}>{label}</Label>
      <Input
        id={name}
        name={name}
        type={type}
        defaultValue={defaultValue}
        required={required}
        maxLength={maxLength}
      />
    </div>
  );
}
