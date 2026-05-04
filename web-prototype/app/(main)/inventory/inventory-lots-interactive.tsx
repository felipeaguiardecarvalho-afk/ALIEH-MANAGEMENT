"use client";

import { memo, useActionState, useCallback, useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Badge } from "@/components/ui/badge";
import { excludeInventoryBatches, type InventoryState } from "@/lib/actions/inventory";
import { formatCurrency, formatDate, formatProductStock } from "@/lib/format";
import type { InventoryLotRow } from "@/lib/inventory-api";
import { ConfirmDeleteForm } from "@/components/confirm-delete-form";
import { cn } from "@/lib/utils";

const initialBatch: InventoryState = { ok: false, message: "" };

function enterCode(row: InventoryLotRow): string | null {
  const c = (row.product_enter_code ?? "").trim();
  return c || null;
}

function stockTone(s: number) {
  if (s <= 0) return "text-destructive";
  if (s <= 5) return "text-[#d4b36c]";
  return "text-foreground";
}

type LotRowProps = {
  row: InventoryLotRow;
  isAdmin: boolean;
  code: string | null;
  selected: boolean;
  onSelectCode: (code: string) => void;
};

const InventoryLotTableRow = memo(
  function InventoryLotTableRow({ row, isAdmin, code, selected, onSelectCode }: LotRowProps) {
    const handleClick = code ? () => onSelectCode(code) : undefined;
    return (
      <tr
        onClick={handleClick}
        className={cn(
          "group border-b border-border/30 transition-colors",
          code ? "cursor-pointer" : "",
          selected
            ? "bg-[#c7a35b]/[0.06]"
            : code
              ? "hover:bg-[#c7a35b]/[0.04]"
              : "opacity-70"
        )}
      >
        {/* Selection indicator (gold left bar) */}
        <td className={cn("relative w-1 p-0", selected && "bg-[#c7a35b]")} aria-hidden />

        {isAdmin ? (
          <td className="px-3 py-3">
            {code ? (
              <input
                type="radio"
                name="inventory_batch_pick"
                className="sr-only"
                checked={selected}
                onChange={() => onSelectCode(code)}
                aria-label={`Seleccionar lote ${code}`}
              />
            ) : null}
            <span
              className={cn(
                "block h-3.5 w-3.5 rounded-full border transition-colors",
                selected ? "border-[#c7a35b] bg-[#c7a35b]" : "border-border bg-background"
              )}
            />
          </td>
        ) : null}

        <td className="px-3 py-3">
          <div className="max-w-[220px] truncate font-medium leading-tight text-foreground">{row.name}</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {(
              [
                ["frame", row.frame_color] as const,
                ["lens", row.lens_color] as const,
                ["gender", row.gender] as const,
              ]
                .filter(([, v]) => Boolean((v ?? "").trim()))
                .map(([slot, v]) => (
                  <Badge key={slot} variant="outline" className="text-[10px] font-normal text-muted-foreground">
                    {v}
                  </Badge>
                )))}
          </div>
        </td>
        <td className="px-3 py-3">
          <Badge variant="gold">{row.sku?.trim() || "—"}</Badge>
        </td>
        <td className="px-3 py-3 font-mono text-xs text-muted-foreground">{code || "—"}</td>
        <td className={cn("px-3 py-3 text-right font-mono text-sm tabular-nums", stockTone(row.stock))}>
          {formatProductStock(row.stock)}
        </td>
        <td className="px-3 py-3 text-right text-sm tabular-nums text-muted-foreground">
          {formatCurrency(row.cost)}
        </td>
        <td className="px-3 py-3 text-right text-sm tabular-nums">{formatCurrency(row.price)}</td>
        <td className="px-3 py-3 text-xs text-muted-foreground">{formatDate(row.registered_date)}</td>
      </tr>
    );
  },
  (prev, next) =>
    prev.row === next.row &&
    prev.isAdmin === next.isAdmin &&
    prev.code === next.code &&
    prev.onSelectCode === next.onSelectCode &&
    prev.selected === next.selected
);

export function InventoryLotsInteractive({
  items,
  isAdmin,
}: {
  items: InventoryLotRow[];
  isAdmin: boolean;
}) {
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [batchState, batchAction] = useActionState(excludeInventoryBatches, initialBatch);

  const onSelectCode = useCallback((c: string) => {
    setSelectedCode((prev) => (prev === c ? null : c));
  }, []);

  useEffect(() => {
    if (batchState.ok) setSelectedCode(null);
  }, [batchState.ok]);

  const batchJson = JSON.stringify(selectedCode ? [selectedCode] : []);
  const selectedRow = items.find((r) => enterCode(r) === selectedCode) ?? null;

  return (
    <div className="space-y-4">
      {/* Desktop / tablet table */}
      <div className="hidden overflow-hidden rounded-2xl border border-border/60 bg-background md:block">
        <div className="max-h-[68vh] overflow-auto">
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
              <tr className="border-b border-border/60 [&>th]:px-3 [&>th]:py-3 [&>th]:text-[10px] [&>th]:font-medium [&>th]:uppercase [&>th]:tracking-[0.16em] [&>th]:text-muted-foreground">
                <th className="w-1 p-0" />
                {isAdmin ? <th className="w-10 text-left">Sel.</th> : null}
                <th className="text-left">Produto</th>
                <th className="text-left">SKU</th>
                <th className="text-left">Cód. entrada</th>
                <th className="text-right">Stock</th>
                <th className="text-right">Custo</th>
                <th className="text-right">Preço</th>
                <th className="text-left">Registo</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => {
                const code = enterCode(row);
                return (
                  <InventoryLotTableRow
                    key={`${row.product_id}-${code ?? "nocode"}`}
                    row={row}
                    isAdmin={isAdmin}
                    code={code}
                    selected={selectedCode != null && selectedCode === code}
                    onSelectCode={onSelectCode}
                  />
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Mobile cards */}
      <div className="space-y-2 md:hidden">
        {items.map((row) => {
          const code = enterCode(row);
          const selected = selectedCode != null && selectedCode === code;
          return (
            <button
              type="button"
              key={`${row.product_id}-${code ?? "nocode"}-card`}
              onClick={code ? () => onSelectCode(code) : undefined}
              className={cn(
                "block w-full rounded-xl border p-4 text-left transition-colors",
                selected
                  ? "border-[#c7a35b]/50 bg-[#c7a35b]/[0.06]"
                  : "border-border/60 bg-background hover:bg-muted/[0.03]"
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="gold">{row.sku?.trim() || "—"}</Badge>
                    {code ? (
                      <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                        {code}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 truncate font-serif text-base font-medium tracking-tight">{row.name}</p>
                </div>
                <span className={cn("font-mono text-base tabular-nums", stockTone(row.stock))}>
                  {formatProductStock(row.stock)}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 border-t border-border/40 pt-3 text-center">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Custo</p>
                  <p className="mt-0.5 text-xs tabular-nums text-muted-foreground">{formatCurrency(row.cost)}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Preço</p>
                  <p className="mt-0.5 text-xs tabular-nums">{formatCurrency(row.price)}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Registo</p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">{formatDate(row.registered_date)}</p>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Selection + delete action — admin only */}
      {isAdmin ? (
        <ConfirmDeleteForm
          confirmMessage={
            selectedCode
              ? `Confirmar exclusão do lote com código «${selectedCode}»? Isso remove o lote inteiro do estoque (stock=0, custo=0, preço=0).`
              : "Seleccione um lote com código de entrada antes de excluir."
          }
          action={batchAction}
          className="space-y-3 rounded-2xl border border-border/60 bg-background p-4"
        >
          <input type="hidden" name="codes_json" value={batchJson} />
          <FormAlert state={batchState.message ? batchState : undefined} />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-[10px] uppercase tracking-[0.24em] text-[#d4b36c]">Lote selecionado</p>
              {selectedRow ? (
                <p className="mt-1 truncate text-sm">
                  <span className="font-mono text-xs text-[#d4b36c]">{enterCode(selectedRow)}</span>
                  <span className="mx-2 text-muted-foreground">·</span>
                  <span className="text-foreground">{selectedRow.name}</span>
                  <span className="mx-2 text-muted-foreground">·</span>
                  <span className={cn("font-mono tabular-nums", stockTone(selectedRow.stock))}>
                    {formatProductStock(selectedRow.stock)}
                  </span>
                </p>
              ) : (
                <p className="mt-1 text-xs text-muted-foreground">
                  Clique numa linha (com código de entrada) para selecionar.
                </p>
              )}
            </div>
            <SubmitButton
              type="submit"
              variant="outline"
              className="gap-2 border-destructive/50 text-destructive hover:bg-destructive/10 hover:text-destructive"
              disabled={!selectedCode}
            >
              <Trash2 className="h-3.5 w-3.5" />
              Excluir lote
            </SubmitButton>
          </div>
        </ConfirmDeleteForm>
      ) : null}
    </div>
  );
}
