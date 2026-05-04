"use client";

import { useActionState, useMemo, useState } from "react";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { saveSkuPricing, type PricingState } from "@/lib/actions/pricing";
import { computePricingTargets } from "@/lib/pricing";
import { formatCurrency } from "@/lib/format";
import type { SkuMasterRow } from "@/lib/types";

const initialState: PricingState = { ok: false, message: "" };

export function PricingWorkflow({ rows }: { rows: SkuMasterRow[] }) {
  const [state, formAction] = useActionState(saveSkuPricing, initialState);
  const [selectedSku, setSelectedSku] = useState(rows[0]?.sku ?? "");
  const [markup, setMarkup] = useState(80);
  const [taxes, setTaxes] = useState(0);
  const [interest, setInterest] = useState(0);
  const [markupKind, setMarkupKind] = useState<0 | 1>(0);
  const [taxesKind, setTaxesKind] = useState<0 | 1>(0);
  const [interestKind, setInterestKind] = useState<0 | 1>(0);

  const active = useMemo(
    () => rows.find((row) => row.sku === selectedSku),
    [rows, selectedSku]
  );

  const avgCost = active?.avgUnitCost ?? 0;
  const currentPrice = active?.sellingPrice ?? 0;
  const targets = computePricingTargets(avgCost, markup, taxes, interest, {
    markupKind,
    taxesKind,
    interestKind,
  });

  return (
    <form action={formAction} className="space-y-6">
      <FormAlert state={state.message ? state : undefined} />

      <div className="grid gap-5 md:grid-cols-[1fr_1fr]">
        <div className="space-y-2">
          <Label htmlFor="sku">SKU</Label>
          <Select
            id="sku"
            name="sku"
            value={selectedSku}
            onChange={(event) => setSelectedSku(event.target.value)}
          >
            {rows.length === 0 ? <option value="">Nenhum SKU cadastrado</option> : null}
            {rows.map((row) => (
              <option key={row.sku} value={row.sku}>
                {row.sku} · CMP {formatCurrency(row.avgUnitCost)} · estoque {row.totalStock}
              </option>
            ))}
          </Select>
        </div>

        <div className="grid gap-3 rounded-2xl border border-border bg-muted/20 p-3 sm:grid-cols-2">
          <Summary label="CMP atual" value={formatCurrency(avgCost)} />
          <Summary label="Preço ativo" value={formatCurrency(currentPrice)} />
        </div>
      </div>

      <ParameterRow
        label="Markup"
        field="markup"
        value={markup}
        onValueChange={setMarkup}
        kind={markupKind}
        onKindChange={setMarkupKind}
      />
      <ParameterRow
        label="Taxas"
        field="taxes"
        value={taxes}
        onValueChange={setTaxes}
        kind={taxesKind}
        onKindChange={setTaxesKind}
      />
      <ParameterRow
        label="Juros / adicional"
        field="interest"
        value={interest}
        onValueChange={setInterest}
        kind={interestKind}
        onKindChange={setInterestKind}
      />

      <div className="grid gap-3 rounded-2xl border border-[#c7a35b]/40 bg-[#c7a35b]/5 p-4 sm:grid-cols-3">
        <Summary label="Preço antes de impostos" value={formatCurrency(targets.priceBefore)} />
        <Summary label="Preço com impostos" value={formatCurrency(targets.priceWithTaxes)} />
        <Summary label="Preço alvo" value={formatCurrency(targets.targetPrice)} highlight />
      </div>

      <div className="flex justify-end">
        <SubmitButton>Salvar precificação</SubmitButton>
      </div>
    </form>
  );
}

function ParameterRow({
  label,
  field,
  value,
  onValueChange,
  kind,
  onKindChange,
}: {
  label: string;
  field: string;
  value: number;
  onValueChange: (value: number) => void;
  kind: 0 | 1;
  onKindChange: (kind: 0 | 1) => void;
}) {
  return (
    <div className="grid gap-3 rounded-2xl border border-border bg-muted/10 p-4 md:grid-cols-[1fr_auto]">
      <div className="space-y-2">
        <Label htmlFor={field}>{label}</Label>
        <Input
          id={field}
          name={field}
          type="number"
          step="0.01"
          min={0}
          value={value}
          onChange={(event) => onValueChange(Number(event.target.value) || 0)}
        />
      </div>
      <div className="space-y-2">
        <Label>Modo</Label>
        <div className="flex items-center gap-2 rounded-full border border-border bg-background p-1">
          <ModeButton active={kind === 0} onClick={() => onKindChange(0)}>
            Percentual (%)
          </ModeButton>
          <ModeButton active={kind === 1} onClick={() => onKindChange(1)}>
            Valor fixo (R$)
          </ModeButton>
        </div>
        <input type="hidden" name={`${field}_kind`} value={kind} />
      </div>
    </div>
  );
}

function ModeButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-1.5 text-xs transition-colors ${
        active ? "bg-white text-black" : "text-muted-foreground hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

function Summary({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{label}</p>
      <p className={`mt-2 font-serif text-2xl ${highlight ? "text-[#d4b36c]" : ""}`}>{value}</p>
    </div>
  );
}
