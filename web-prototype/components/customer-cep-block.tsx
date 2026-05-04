"use client";

import { useState, useTransition } from "react";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type CepAddress = {
  logradouro: string;
  bairro: string;
  localidade: string;
  uf: string;
  erro?: boolean;
};

export type AddressFieldDefaults = {
  street?: string;
  number?: string;
  neighborhood?: string;
  city?: string;
  state?: string;
  country?: string;
};

export function CustomerCepBlock({
  initialZipCode = "",
  addressDefaults = {},
}: {
  initialZipCode?: string;
  addressDefaults?: AddressFieldDefaults;
}) {
  const [cep, setCep] = useState(initialZipCode);
  const [cepError, setCepError] = useState<string | null>(null);
  const [address, setAddress] = useState<Partial<CepAddress>>({});
  const [pending, startTransition] = useTransition();

  const mergedStreet = address.logradouro ?? addressDefaults.street ?? "";
  const mergedNeighborhood = address.bairro ?? addressDefaults.neighborhood ?? "";
  const mergedCity = address.localidade ?? addressDefaults.city ?? "";
  const mergedState = address.uf ?? addressDefaults.state ?? "";
  const countryDefault = addressDefaults.country?.trim() || "Brasil";

  async function lookupCep() {
    const digits = cep.replace(/\D/g, "");
    if (digits.length !== 8) {
      setCepError("CEP precisa ter 8 dígitos.");
      return;
    }
    setCepError(null);
    startTransition(async () => {
      const ac = new AbortController();
      const t = window.setTimeout(() => ac.abort(), 8_000);
      try {
        const res = await fetch(`https://viacep.com.br/ws/${digits}/json/`, {
          signal: ac.signal,
        });
        const data = (await res.json()) as CepAddress;
        if (data.erro) {
          setCepError("CEP não encontrado.");
          return;
        }
        setAddress(data);
      } catch {
        setCepError("Falha na busca do CEP (rede ou tempo esgotado).");
      } finally {
        window.clearTimeout(t);
      }
    });
  }

  return (
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
        <AddressField
          label="Rua"
          name="street"
          defaultValue={mergedStreet}
          key={`street-${mergedStreet}`}
        />
        <AddressField
          label="Número"
          name="number"
          defaultValue={addressDefaults.number ?? ""}
          key={`num-${addressDefaults.number ?? ""}`}
        />
        <AddressField
          label="Bairro"
          name="neighborhood"
          defaultValue={mergedNeighborhood}
          key={`b-${mergedNeighborhood}`}
        />
        <AddressField
          label="Cidade"
          name="city"
          defaultValue={mergedCity}
          key={`c-${mergedCity}`}
        />
        <AddressField
          label="Estado (UF)"
          name="state"
          maxLength={2}
          defaultValue={mergedState}
          key={`uf-${mergedState}`}
        />
        <AddressField label="País" name="country" defaultValue={countryDefault} key={`ct-${countryDefault}`} />
      </div>
    </div>
  );
}

function AddressField({
  label,
  name,
  type = "text",
  defaultValue,
  maxLength,
}: {
  label: string;
  name: string;
  type?: string;
  defaultValue?: string;
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
        maxLength={maxLength}
      />
    </div>
  );
}
