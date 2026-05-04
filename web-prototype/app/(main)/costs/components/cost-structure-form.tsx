"use client";

import { useActionState, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  loadCostCompositionAction,
  previewCostCompositionAction,
  saveCostStructure,
  type CostState,
} from "@/lib/actions/costs";
import { SKU_COST_COMPONENT_DEFINITIONS } from "@/lib/domain";
import type { PreviewCompositionResponse, SkuCostPickerOption } from "@/lib/costs-types";
import { formatCurrency } from "@/lib/format";
import { cn } from "@/lib/utils";

const initialState: CostState = { ok: false, message: "" };

type PickMode = "sku" | "name";

export function CostStructureForm({
  skus,
  pickByName,
  isAdmin,
}: {
  skus: string[];
  pickByName: SkuCostPickerOption[];
  isAdmin: boolean;
}) {
  // ───── Logic preserved verbatim ─────
  const router = useRouter();
  const [state, formAction] = useActionState(saveCostStructure, initialState);
  const [pickMode, setPickMode] = useState<PickMode>("sku");
  const [selectedSku, setSelectedSku] = useState(skus[0] ?? "");
  const [rows, setRows] = useState<Record<string, { qty: string; price: string }>>({});
  const [lastSaved, setLastSaved] = useState(0);
  const [preview, setPreview] = useState<PreviewCompositionResponse | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const nameLabelToSku = useMemo(() => {
    const m = new Map<string, string>();
    for (const o of pickByName) m.set(o.label, o.sku);
    return m;
  }, [pickByName]);

  const loadSku = useCallback(async (sku: string) => {
    if (!sku.trim()) return;
    const data = await loadCostCompositionAction(sku);
    if (!data) return;
    setLastSaved(data.last_saved_structured_total);
    const next: Record<string, { qty: string; price: string }> = {};
    for (const c of data.components) {
      next[c.component_key] = {
        qty: c.quantity_text ?? (c.quantity ? String(c.quantity) : ""),
        price: String(c.unit_price ?? ""),
      };
    }
    setRows(next);
  }, []);

  useEffect(() => {
    void loadSku(selectedSku);
  }, [selectedSku, loadSku]);

  const runPreview = useCallback(async () => {
    const lines = SKU_COST_COMPONENT_DEFINITIONS.map((d) => ({
      component_key: d.key,
      quantity_text: rows[d.key]?.qty ?? "",
      unit_price: Number(String(rows[d.key]?.price ?? "").replace(",", ".")) || 0,
    }));
    try {
      const p = await previewCostCompositionAction(lines);
      setPreview(p);
    } catch {
      setPreview(null);
    }
  }, [rows]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void runPreview();
    }, 320);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [rows, runPreview]);

  useEffect(() => {
    if (state.ok) {
      router.refresh();
    }
  }, [state.ok, router]);

  if (!skus.length) {
    return (
      <div className="rounded-xl border border-border/60 bg-muted/10 p-5 text-sm text-muted-foreground">
        Ainda não há SKUs no cadastro mestre. Cadastre um produto em{" "}
        <Link href="/products" className="font-medium text-foreground underline-offset-4 hover:underline">
          Produtos
        </Link>{" "}
        e inclua estoque (ou confira <code className="rounded bg-muted px-1 text-xs">sku_master</code>).
      </div>
    );
  }

  return (
    <form action={formAction} className="space-y-7">
      <input type="hidden" name="sku" value={selectedSku} />

      <FormAlert state={state.message ? state : undefined} />

      {/* SKU picker — segmented control + select */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">Selecionar por</span>
          <div className="inline-flex items-center gap-0.5 rounded-lg border border-border/60 bg-background p-0.5">
            <label
              className={cn(
                "inline-flex h-7 cursor-pointer items-center rounded-md px-3 text-xs font-medium transition-colors",
                pickMode === "sku" ? "bg-muted/60 text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              <input
                type="radio"
                name="_pick_mode"
                checked={pickMode === "sku"}
                onChange={() => setPickMode("sku")}
                className="sr-only"
              />
              SKU
            </label>
            <label
              className={cn(
                "inline-flex h-7 cursor-pointer items-center rounded-md px-3 text-xs font-medium transition-colors",
                pickMode === "name" ? "bg-muted/60 text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              <input
                type="radio"
                name="_pick_mode"
                checked={pickMode === "name"}
                onChange={() => setPickMode("name")}
                className="sr-only"
              />
              Nome do produto
            </label>
          </div>
        </div>

        {pickMode === "sku" ? (
          <div className="space-y-1.5">
            <Label className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">SKU</Label>
            <Select
              value={selectedSku}
              onChange={(e) => setSelectedSku(e.target.value)}
              aria-label="Seleccionar SKU"
              className="h-11 font-mono text-sm"
            >
              {skus.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </div>
        ) : (
          <div className="space-y-1.5">
            <Label className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              Nome — cor da armação — cor da lente
            </Label>
            <Select
              value={pickByName.find((o) => o.sku === selectedSku)?.label ?? pickByName[0]?.label ?? ""}
              onChange={(e) => {
                const sku = nameLabelToSku.get(e.target.value);
                if (sku) setSelectedSku(sku);
              }}
              aria-label="Seleccionar por nome"
              className="h-11"
            >
              {pickByName.map((o) => (
                <option key={o.sku} value={o.label}>
                  {o.label}
                </option>
              ))}
            </Select>
          </div>
        )}
      </div>

      {/* Components — clean grid with column header */}
      <div className="space-y-2">
        <div className="hidden grid-cols-[1fr_8rem_8rem_7rem] gap-3 px-3 sm:grid">
          <span className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Componente</span>
          <span className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Qtd.</span>
          <span className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Preço unit.</span>
          <span className="text-right text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Total linha</span>
        </div>

        <div className="divide-y divide-border/40 overflow-hidden rounded-xl border border-border/60">
          {SKU_COST_COMPONENT_DEFINITIONS.map((component) => {
            const r = rows[component.key] ?? { qty: "", price: "0" };
            const pl = preview?.lines?.find((l) => l.component_key === component.key);
            const lineErr = pl?.quantity_error || pl?.price_error;
            const lineTotal = pl?.line_total;

            return (
              <div
                key={component.key}
                className={cn(
                  "grid gap-3 bg-background px-3 py-3.5 transition-colors hover:bg-muted/[0.03] sm:grid-cols-[1fr_8rem_8rem_7rem] sm:items-end",
                  lineErr && "bg-amber-500/[0.04]"
                )}
              >
                <div className="space-y-0.5">
                  <p className="text-sm font-medium text-foreground">{component.label}</p>
                  {lineErr ? <p className="text-xs text-amber-400">{lineErr}</p> : null}
                </div>
                <div className="space-y-1">
                  <Label
                    htmlFor={`qty_${component.key}`}
                    className="sm:hidden text-[10px] uppercase tracking-[0.14em] text-muted-foreground"
                  >
                    Qtd.
                  </Label>
                  <Input
                    id={`qty_${component.key}`}
                    name={`qty_${component.key}`}
                    inputMode="decimal"
                    autoComplete="off"
                    value={r.qty}
                    onChange={(e) =>
                      setRows((prev) => ({
                        ...prev,
                        [component.key]: { ...r, qty: e.target.value },
                      }))
                    }
                    className="h-9 font-mono tabular-nums"
                  />
                </div>
                <div className="space-y-1">
                  <Label
                    htmlFor={`price_${component.key}`}
                    className="sm:hidden text-[10px] uppercase tracking-[0.14em] text-muted-foreground"
                  >
                    Preço unit.
                  </Label>
                  <Input
                    id={`price_${component.key}`}
                    name={`price_${component.key}`}
                    type="number"
                    min={0}
                    step="0.01"
                    value={r.price}
                    onChange={(e) =>
                      setRows((prev) => ({
                        ...prev,
                        [component.key]: { ...r, price: e.target.value },
                      }))
                    }
                    className="h-9 font-mono tabular-nums"
                  />
                </div>
                <div className="flex items-end justify-end">
                  <p
                    className={cn(
                      "font-mono text-sm tabular-nums",
                      lineTotal != null && lineTotal > 0 ? "text-foreground" : "text-muted-foreground"
                    )}
                  >
                    {lineTotal != null ? formatCurrency(lineTotal) : "—"}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Total — dominant */}
      <div className="flex flex-col gap-4 rounded-2xl border border-[#c7a35b]/30 bg-gradient-to-br from-[#c7a35b]/[0.07] to-transparent px-6 py-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-[0.24em] text-[#d4b36c]">Custo total · ao vivo</p>
          <p className="font-serif text-4xl font-semibold tabular-nums tracking-tight md:text-5xl">
            {preview ? formatCurrency(preview.live_total) : "—"}
          </p>
          <p className="text-[11px] text-muted-foreground">
            último salvo · <span className="text-foreground tabular-nums">{formatCurrency(lastSaved)}</span>
          </p>
        </div>
        {preview?.has_errors ? (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/[0.06] px-3 py-2 text-xs text-amber-300">
            Corrija os erros acima antes de salvar.
          </div>
        ) : null}
      </div>

      <div className="flex justify-end">
        <SubmitButton disabled={!isAdmin} title={!isAdmin ? "Apenas administradores." : undefined}>
          Salvar composição de custo
        </SubmitButton>
      </div>
    </form>
  );
}
