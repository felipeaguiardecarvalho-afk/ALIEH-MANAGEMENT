"use client";

import { useActionState, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronDown } from "lucide-react";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  addStockReceipt,
  loadStockEntryContextAction,
  parseStockQuantityTextAction,
  type InventoryState,
} from "@/lib/actions/inventory";
import { formatProductMoney } from "@/lib/format";
import type { SkuCostPickerOption, StockEntryBatch } from "@/lib/costs-types";
import { cn } from "@/lib/utils";
import { formatQtyDisplay4 } from "../format-qty";

const initial: InventoryState = { ok: false, message: "" };

type PickMode = "sku" | "name";

export function StockReceiptForm({
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
  const [state, formAction] = useActionState(addStockReceipt, initial);
  const [pickMode, setPickMode] = useState<PickMode>("sku");
  const [sku, setSku] = useState(skus[0] ?? "");
  const [quantityText, setQuantityText] = useState("");
  const [parseQty, setParseQty] = useState<{
    error: string | null;
    parsed: number | null;
    positive_ok: boolean;
  } | null>(null);
  const [selectedBatchId, setSelectedBatchId] = useState<string>("");
  const [confirmOk, setConfirmOk] = useState(false);

  const nameLabelToSku = useMemo(() => {
    const m = new Map<string, string>();
    for (const o of pickByName) m.set(o.label, o.sku);
    return m;
  }, [pickByName]);

  useEffect(() => {
    if (state.ok) {
      router.refresh();
    }
  }, [state.ok, router]);

  useEffect(() => {
    if (pickMode === "sku") {
      if (!sku || !skus.includes(sku)) setSku(skus[0] ?? "");
      return;
    }
    if (!pickByName.length) {
      setPickMode("sku");
      return;
    }
    if (!pickByName.some((o) => o.sku === sku)) setSku(pickByName[0].sku);
  }, [pickMode, pickByName, skus, sku]);

  useEffect(() => {
    setQuantityText("");
    setParseQty(null);
    setConfirmOk(false);
    setSelectedBatchId("");
  }, [sku]);

  const [ctx, setCtx] = useState<{
    structured_unit_cost: number;
    batches: StockEntryBatch[];
    components_readonly: { componente: string; preço_unit: number; qtd: number; linha: number }[];
  } | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  useEffect(() => {
    if (!sku.trim()) {
      setCtx(null);
      return;
    }
    let cancelled = false;
    setLoadErr(null);
    setCtx(null);
    void (async () => {
      try {
        const data = await loadStockEntryContextAction(sku.trim());
        if (!cancelled) setCtx(data);
      } catch (e) {
        if (!cancelled) {
          setCtx(null);
          setLoadErr(e instanceof Error ? e.message : "Falha ao carregar contexto.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sku]);

  const unitCost = ctx?.structured_unit_cost ?? 0;
  const batches = ctx?.batches ?? [];

  useEffect(() => {
    if (!batches.length) {
      setSelectedBatchId("");
      return;
    }
    setSelectedBatchId((prev) => {
      const ids = new Set(batches.map((b) => String(b.id)));
      if (prev && ids.has(prev)) return prev;
      return String(batches[0].id);
    });
  }, [batches]);

  useEffect(() => {
    let cancelled = false;
    const t = window.setTimeout(() => {
      void (async () => {
        try {
          const r = await parseStockQuantityTextAction(quantityText);
          if (!cancelled) setParseQty(r);
        } catch {
          if (!cancelled) setParseQty({ error: "Falha ao validar quantidade.", parsed: null, positive_ok: false });
        }
      })();
    }, 280);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [quantityText]);

  const selectedBatch = useMemo(
    () => batches.find((b) => String(b.id) === selectedBatchId),
    [batches, selectedBatchId]
  );
  const psku = (selectedBatch?.sku ?? "").trim();
  const skuMatch = Boolean(selectedBatch && psku === sku.trim());

  const totalEntry =
    parseQty?.positive_ok && parseQty.parsed != null && unitCost > 0
      ? Number((parseQty.parsed * unitCost).toFixed(2))
      : 0;

  const canFinalize =
    confirmOk &&
    parseQty?.positive_ok === true &&
    unitCost > 0 &&
    skuMatch &&
    Boolean(selectedBatchId);

  const submitDisabled = !isAdmin || !canFinalize || !batches.length || !skuMatch;

  const qtyEmptyMsg =
    batches.length > 0 && quantityText.trim() === "" && parseQty != null && !parseQty.error
      ? "Indique a quantidade (texto, até 4 decimais)."
      : null;

  if (!skus.length) {
    return (
      <div className="rounded-xl border border-border/60 bg-muted/10 p-5 text-sm text-muted-foreground">
        <p>Nenhum SKU disponível para entrada de estoque.</p>
        <p className="mt-2">
          Cadastre um produto em{" "}
          <Link href="/products" className="font-medium text-foreground underline-offset-4 hover:underline">
            Produtos
          </Link>{" "}
          e inclua estoque no mestre para continuar.
        </p>
      </div>
    );
  }

  return (
    <form
      action={formAction}
      className="space-y-7"
      onSubmit={(e) => {
        if (submitDisabled || !skuMatch) {
          e.preventDefault();
        }
      }}
    >
      <FormAlert state={state.message ? state : undefined} />
      {loadErr ? (
        <p className="rounded-lg border border-destructive/40 bg-destructive/[0.05] px-3 py-2 text-sm text-destructive">
          {loadErr}
        </p>
      ) : null}

      <input type="hidden" name="sku" value={sku} />
      <input type="hidden" name="product_id" value={selectedBatchId} />

      {/* ===== ETAPA 1 — Localizar produto ===== */}
      <Step n={1} title="Localizar produto" hint="Selecione por SKU ou nome (carrega componentes salvos)">
        {pickByName.length > 0 ? (
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
                  name="_pick_mode_stock"
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
                  name="_pick_mode_stock"
                  checked={pickMode === "name"}
                  onChange={() => setPickMode("name")}
                  className="sr-only"
                />
                Nome
              </label>
            </div>
          </div>
        ) : null}

        <div className="space-y-1.5">
          {pickMode === "sku" || !pickByName.length ? (
            <>
              <Label htmlFor="stock_entry_sku" className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                SKU
              </Label>
              <Select
                id="stock_entry_sku"
                value={sku}
                onChange={(e) => setSku(e.target.value)}
                aria-label="SKU destino"
                className="h-11 font-mono text-sm"
              >
                {skus.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </>
          ) : (
            <>
              <Label htmlFor="stock_entry_name" className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                Nome — cor da armação — cor da lente
              </Label>
              <Select
                id="stock_entry_name"
                value={pickByName.find((o) => o.sku === sku)?.label ?? pickByName[0]?.label ?? ""}
                onChange={(e) => {
                  const next = nameLabelToSku.get(e.target.value);
                  if (next) setSku(next);
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
            </>
          )}
        </div>

        {ctx && ctx.components_readonly.length > 0 ? (
          <details className="group rounded-xl border border-border/60 bg-muted/10">
            <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-2.5 text-xs text-muted-foreground transition-colors hover:text-foreground">
              <span>Componentes de custo deste SKU (somente leitura)</span>
              <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
            </summary>
            <div className="border-t border-border/40 px-4 py-3">
              <Table>
                <TableHeader>
                  <TableRow className="[&_th]:text-[10px] [&_th]:uppercase [&_th]:tracking-[0.14em] [&_th]:text-muted-foreground">
                    <TableHead>Componente</TableHead>
                    <TableHead className="text-right">Quantidade</TableHead>
                    <TableHead className="text-right">Custo unitário</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ctx.components_readonly.map((c, i) => (
                    <TableRow key={i} className="border-b-border/30">
                      <TableCell className="text-xs">{c.componente}</TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">
                        {formatQtyDisplay4(c.qtd) || "0"}
                      </TableCell>
                      <TableCell className="text-right text-xs tabular-nums text-muted-foreground">
                        {formatProductMoney(c.preço_unit)}
                      </TableCell>
                      <TableCell className="text-right text-xs tabular-nums">
                        {formatProductMoney(c.linha)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </details>
        ) : null}
      </Step>

      {/* ===== ETAPA 2 — Lote ===== */}
      <Step n={2} title="Lote destinatário" hint="Lote que recebe a mercadoria. Deve ser do mesmo SKU.">
        <div className="space-y-1.5">
          <Label htmlFor="product_id_select" className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            Lote
          </Label>
          <Select
            id="product_id_select"
            value={selectedBatchId}
            onChange={(e) => setSelectedBatchId(e.target.value)}
            aria-label="Lote destinatário"
            disabled={!batches.length}
            className="h-11"
          >
            <option value="">— selecionar —</option>
            {batches.map((b) => (
              <option key={b.id} value={String(b.id)}>
                {b.label}
              </option>
            ))}
          </Select>
          {!batches.length && sku ? (
            <p className="text-xs text-muted-foreground">Não há lotes para este SKU. Cadastre produtos primeiro.</p>
          ) : null}
        </div>
      </Step>

      {/* ===== ETAPA 3 — Quantidade ===== */}
      <Step n={3} title="Quantidade a adicionar" hint="Maior que zero · até 4 decimais · validação na API">
        <div className="space-y-1.5">
          <Label htmlFor="quantity_text" className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            Quantidade
          </Label>
          <Input
            id="quantity_text"
            name="quantity_text"
            inputMode="decimal"
            autoComplete="off"
            placeholder="ex.: 12,5  ou  1,0000"
            value={quantityText}
            onChange={(e) => setQuantityText(e.target.value)}
            className="h-12 font-serif text-2xl tabular-nums tracking-tight"
          />
          {parseQty?.error ? <p className="text-xs text-destructive">{parseQty.error}</p> : null}
          {qtyEmptyMsg ? <p className="text-xs text-destructive">{qtyEmptyMsg}</p> : null}
        </div>
      </Step>

      {/* ===== ETAPA 4 — Custo unitário (estrutura salva) ===== */}
      <Step n={4} title="Custo unitário" hint="Total da composição salva (não-editável)">
        <div className="grid gap-px overflow-hidden rounded-xl border border-border/60 bg-border/60 sm:grid-cols-2">
          <div className="bg-background px-5 py-4">
            <p className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">Custo unitário · estrutura</p>
            <p className="mt-2 font-serif text-3xl font-semibold tabular-nums tracking-tight text-[#d4b36c]">
              {formatProductMoney(unitCost)}
            </p>
            {unitCost <= 0 ? (
              <p className="mt-2 text-xs text-amber-300">
                Salve a composição de custo antes de dar entrada.
              </p>
            ) : null}
          </div>
          <div
            className={cn(
              "bg-background px-5 py-4 transition-opacity",
              !(parseQty?.positive_ok && parseQty.parsed != null && unitCost > 0) && "opacity-50"
            )}
          >
            <p className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">Custo total · entrada</p>
            <p className="mt-2 font-serif text-3xl font-semibold tabular-nums tracking-tight">
              {parseQty?.positive_ok && parseQty.parsed != null && unitCost > 0
                ? formatProductMoney(totalEntry)
                : "—"}
            </p>
            <p className="mt-1 text-[11px] text-muted-foreground">qtd × custo unitário</p>
          </div>
        </div>
      </Step>

      {/* ===== ETAPA 5 — Confirmação ===== */}
      <Step n={5} title="Confirmar e finalizar" hint="O CMP recalcula por média ponderada">
        {/* Summary */}
        <div className="overflow-hidden rounded-xl border border-border/60 bg-muted/[0.04]">
          <div className="border-b border-border/40 px-5 py-3">
            <p className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">Resumo</p>
          </div>
          <dl className="grid grid-cols-1 divide-y divide-border/30 sm:grid-cols-2 sm:divide-x sm:divide-y-0">
            <SummaryRow
              label="SKU"
              value={
                <code className="font-mono text-xs text-[#d4b36c]">{sku}</code>
              }
            />
            <SummaryRow
              label="Quantidade"
              value={
                parseQty?.positive_ok === true && parseQty.parsed != null ? (
                  <span className="font-mono text-sm tabular-nums">{formatQtyDisplay4(parseQty.parsed)}</span>
                ) : quantityText.trim() !== "" ? (
                  <code className="text-xs break-all text-muted-foreground">{quantityText}</code>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )
              }
            />
            <SummaryRow
              label="Custo unitário"
              value={
                unitCost > 0 ? (
                  <span className="text-sm tabular-nums text-foreground">{formatProductMoney(unitCost)}</span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )
              }
            />
            <SummaryRow
              label="Custo total"
              value={
                parseQty?.positive_ok === true && parseQty.parsed != null && parseQty.parsed > 0 && unitCost > 0 ? (
                  <span className="font-serif text-lg font-semibold tabular-nums text-[#d4b36c]">
                    {formatProductMoney(totalEntry)}
                  </span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )
              }
              accent
            />
          </dl>
          {!skuMatch && selectedBatchId ? (
            <p className="border-t border-destructive/30 bg-destructive/[0.05] px-5 py-3 text-xs text-destructive">
              O SKU do lote selecionado não coincide com o SKU da entrada. Selecione um lote do mesmo SKU ou
              corrija o produto.
            </p>
          ) : null}
        </div>

        {/* Confirm checkbox */}
        <label
          className={cn(
            "flex cursor-pointer items-start gap-3 rounded-xl border p-4 text-sm transition-colors",
            confirmOk
              ? "border-[#c7a35b]/40 bg-[#c7a35b]/[0.05]"
              : "border-border/60 bg-background hover:bg-muted/[0.04]"
          )}
        >
          <input
            type="checkbox"
            name="confirm_receipt"
            checked={confirmOk}
            onChange={(e) => setConfirmOk(e.target.checked)}
            value="on"
            className="mt-0.5 h-4 w-4 accent-[#c7a35b]"
          />
          <span className="text-foreground">Confirmo que esta entrada de estoque está correta.</span>
        </label>
      </Step>

      {/* CTA */}
      <div className="flex items-center justify-end border-t border-border/40 pt-6">
        <SubmitButton disabled={submitDisabled} title={!isAdmin ? "Apenas administradores." : undefined}>
          Finalizar entrada de stock
        </SubmitButton>
      </div>
    </form>
  );
}

// ──────── Step block ────────
function Step({
  n,
  title,
  hint,
  children,
}: {
  n: number;
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="grid gap-5 sm:grid-cols-[3.5rem_minmax(0,1fr)] sm:gap-6">
      <div className="flex sm:flex-col sm:items-center">
        <span className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[#c7a35b]/40 bg-[#c7a35b]/[0.06] font-mono text-sm font-semibold tabular-nums text-[#d4b36c]">
          {n}
        </span>
        <span className="ml-3 hidden h-full w-px bg-border/40 sm:ml-0 sm:mt-3 sm:block" />
      </div>
      <div className="space-y-4 pb-2 sm:pb-6">
        <header>
          <p className="text-[10px] uppercase tracking-[0.24em] text-[#d4b36c]">Etapa {n}</p>
          <h3 className="mt-0.5 font-serif text-xl font-semibold tracking-tight">{title}</h3>
          {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
        </header>
        {children}
      </div>
    </section>
  );
}

function SummaryRow({
  label,
  value,
  accent,
}: {
  label: string;
  value: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <div className={cn("px-5 py-4", accent && "bg-[#c7a35b]/[0.04]")}>
      <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
      <div className="mt-1.5">{value}</div>
    </div>
  );
}
