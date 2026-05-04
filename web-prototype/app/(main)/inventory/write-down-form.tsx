"use client";

import { useActionState, useCallback, useEffect, useMemo, useOptimistic, useRef, useState } from "react";
import { Minus } from "lucide-react";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { manualWriteDown, type InventoryState } from "@/lib/actions/inventory";
import { formatNumber, formatProductStock } from "@/lib/format";
import type { InventoryLotRow } from "@/lib/inventory-api";
import { cn } from "@/lib/utils";

const initialState: InventoryState = { ok: false, message: "" };

function mergeInventoryState(prev: InventoryState, patch: Partial<InventoryState>): InventoryState {
  return { ...prev, ...patch };
}

function parseWriteQty(value: FormDataEntryValue | null): number {
  if (typeof value !== "string") return 0;
  return Number(value.replace(",", ".")) || 0;
}

function applyWriteDownLots(
  prev: InventoryLotRow[],
  patch: { productId: number; quantity: number }
): InventoryLotRow[] {
  return prev.map((l) =>
    l.product_id === patch.productId
      ? { ...l, stock: Math.max(0, (Number(l.stock) || 0) - patch.quantity) }
      : l
  );
}

export function WriteDownForm({ lots }: { lots: InventoryLotRow[] }) {
  const [state, serverAction] = useActionState(manualWriteDown, initialState);
  const [displayState, addOptimisticState] = useOptimistic(state, mergeInventoryState);
  const [displayLots, addOptimisticLots] = useOptimistic(lots, applyWriteDownLots);

  const formAction = useCallback(
    (fd: FormData) => {
      const confirmed = fd.get("confirm_write_down");
      const productId = Number(fd.get("product_id"));
      const quantity = parseWriteQty(fd.get("quantity"));
      if (confirmed === "on" && productId > 0 && quantity > 0) {
        addOptimisticLots({ productId, quantity });
        addOptimisticState({ ok: false, message: "A registar baixa no servidor…" });
      }
      return serverAction(fd);
    },
    [serverAction, addOptimisticLots, addOptimisticState]
  );

  const sorted = useMemo(
    () =>
      [...displayLots].sort((a, b) => a.name.localeCompare(b.name, "pt") || a.product_id - b.product_id),
    [displayLots]
  );

  const [productId, setProductId] = useState(() =>
    sorted.length ? String(sorted[0].product_id) : ""
  );
  const [formNonce, setFormNonce] = useState(0);
  const lastSuccessMessage = useRef<string | null>(null);

  useEffect(() => {
    if (!state.ok) {
      lastSuccessMessage.current = null;
      return;
    }
    if (!state.message || lastSuccessMessage.current === state.message) return;
    lastSuccessMessage.current = state.message;
    const first = sorted.length ? String(sorted[0].product_id) : "";
    setProductId(first);
    setFormNonce((n) => n + 1);
  }, [state.ok, state.message, sorted]);

  const selected = sorted.find((l) => String(l.product_id) === productId);
  const maxStock = selected ? selected.stock : 0;

  if (!sorted.length) {
    return (
      <div className="rounded-xl border border-border/60 bg-muted/10 p-5 text-sm text-muted-foreground">
        Sem lotes com stock disponíveis para baixa.
      </div>
    );
  }

  return (
    <form key={formNonce} action={formAction} className="space-y-5">
      <FormAlert state={displayState.message ? displayState : undefined} />

      {/* Lot picker */}
      <div className="space-y-1.5">
        <Label htmlFor="product_id" className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
          Lote · stock &gt; 0
        </Label>
        <Select
          id="product_id"
          name="product_id"
          value={productId}
          onChange={(e) => setProductId(e.target.value)}
          className="h-11 font-mono text-xs"
        >
          {sorted.map((lot) => (
            <option key={lot.product_id} value={lot.product_id}>
              #{lot.product_id} · {lot.product_enter_code?.trim() || "—"} · {lot.name} · stock{" "}
              {formatProductStock(lot.stock)}
            </option>
          ))}
        </Select>
      </div>

      {/* Selected preview */}
      {selected ? (
        <div className="rounded-xl border border-border/60 bg-muted/[0.04] px-4 py-3">
          <div className="flex items-baseline justify-between gap-3">
            <p className="truncate text-sm font-medium text-foreground">{selected.name}</p>
            <span className="shrink-0 font-mono text-lg tabular-nums text-foreground">
              {formatProductStock(maxStock)}
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-muted-foreground">stock atual em estoque</p>
        </div>
      ) : null}

      {/* Quantity */}
      <div className="space-y-1.5">
        <div className="flex items-baseline justify-between">
          <Label htmlFor="quantity" className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            Quantidade a baixar
          </Label>
          <span className="text-[10px] tabular-nums text-muted-foreground">
            máx <span className="text-foreground">{formatNumber(maxStock)}</span>
          </span>
        </div>
        <Input
          id="quantity"
          name="quantity"
          type="number"
          min={0.0001}
          max={maxStock > 0 ? maxStock : undefined}
          step={0.0001}
          key={`${formNonce}-${productId}`}
          defaultValue={maxStock > 0 ? Math.min(1, maxStock) : 0}
          className="h-12 font-serif text-2xl tabular-nums tracking-tight"
        />
        <p className="text-[11px] text-muted-foreground">
          A API recusa quantidades acima do stock — sem stock negativo.
        </p>
      </div>

      {/* Confirmation card */}
      <ConfirmCard />

      <SubmitButton blockWhilePending={false} className="w-full justify-center gap-2">
        <Minus className="h-3.5 w-3.5" />
        Aplicar baixa
      </SubmitButton>
    </form>
  );
}

function ConfirmCard() {
  const [checked, setChecked] = useState(false);
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-xl border p-4 text-sm transition-colors",
        checked
          ? "border-[#c7a35b]/40 bg-[#c7a35b]/[0.06]"
          : "border-amber-500/30 bg-amber-500/[0.04] hover:bg-amber-500/[0.06]"
      )}
    >
      <input
        type="checkbox"
        name="confirm_write_down"
        required
        checked={checked}
        onChange={(e) => setChecked(e.target.checked)}
        className="mt-0.5 h-4 w-4 rounded border-input accent-[#c7a35b]"
      />
      <span className={cn("text-xs leading-5", checked ? "text-foreground" : "text-amber-200/90")}>
        Confirmo a baixa neste lote e quantidade.
        <br />
        <span className="text-muted-foreground">Operação irreversível pelo formulário.</span>
      </span>
    </label>
  );
}
