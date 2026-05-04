"use client";

import {
  useActionState,
  useEffect,
  useMemo,
  useOptimistic,
  useState,
} from "react";
import { useFormStatus } from "react-dom";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { submitSaleForm, type SaleFormState, type SalePreview } from "@/lib/actions/sales";
import { useClientDataStore } from "@/lib/client-data/store";
import { SALE_PAYMENT_OPTIONS } from "@/lib/domain";
import { formatCurrency, formatNumber } from "@/lib/format";
import type { Customer, ProductBatch, SaleableSku } from "@/lib/types";

const initialState: SaleFormState = { ok: false, message: "", preview: null };

const EMPTY_BATCHES: ProductBatch[] = [];

const PREFETCH_SALE_SKU_CAP = 24;

function mergeSaleFormState(current: SaleFormState, patch: Partial<SaleFormState>): SaleFormState {
  return {
    ...current,
    ...patch,
    preview: patch.preview !== undefined ? patch.preview : current.preview,
  };
}

function StepTitle({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <h3 className="border-t border-white/10 pt-6 text-sm font-semibold tracking-wide text-muted-foreground first:border-0 first:pt-0">
      Etapa {n} — {children}
    </h3>
  );
}

export function NewSaleForm({
  skus,
  customers,
}: {
  skus: SaleableSku[];
  customers: Customer[];
}) {
  const [state, formAction] = useActionState(submitSaleForm, initialState);
  const [display, addOptimistic] = useOptimistic(state, mergeSaleFormState);

  const [selectedSku, setSelectedSku] = useState(skus[0]?.sku ?? "");
  const [productId, setProductId] = useState("");
  const [custSearch, setCustSearch] = useState("");

  const hydrateSalePage = useClientDataStore((s) => s.hydrateSalePage);
  const prefetchSaleBatchCluster = useClientDataStore((s) => s.prefetchSaleBatchCluster);
  const ensureSaleBatches = useClientDataStore((s) => s.ensureSaleBatches);
  const invalidateAllBatches = useClientDataStore((s) => s.invalidateAllBatches);

  const batchSlot = useClientDataStore((s) => {
    const sku = (selectedSku || "").trim();
    if (!sku) return null;
    return s.batchesBySku[sku] ?? null;
  });
  const batches = batchSlot?.data ?? EMPTY_BATCHES;
  const loadingBatches = Boolean(batchSlot?.promise) && !(batchSlot?.data?.length);

  const selectedBatch = useMemo(
    () => batches.find((b) => String(b.id) === productId),
    [batches, productId]
  );
  const batchStock = selectedBatch ? Math.max(0, Number(selectedBatch.stock) || 0) : 0;

  const filteredCustomers = useMemo(() => {
    const q = custSearch.trim().toLowerCase();
    if (!q) return customers;
    return customers.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        (c.customerCode || "").toLowerCase().includes(q)
    );
  }, [customers, custSearch]);

  useEffect(() => {
    hydrateSalePage({ customers, skus });
  }, [hydrateSalePage, customers, skus]);

  useEffect(() => {
    if (!skus.length) return;
    prefetchSaleBatchCluster(
      skus.slice(0, Math.min(PREFETCH_SALE_SKU_CAP, skus.length)).map((s) => s.sku),
      PREFETCH_SALE_SKU_CAP
    );
  }, [skus, prefetchSaleBatchCluster]);

  useEffect(() => {
    if (state.ok && state.preview === null && /registrada/i.test(state.message)) {
      invalidateAllBatches();
    }
  }, [state.ok, state.preview, state.message, invalidateAllBatches]);

  useEffect(() => {
    const sku = (selectedSku || "").trim();
    if (!sku) {
      setProductId("");
      return;
    }
    void ensureSaleBatches(sku);
  }, [selectedSku, ensureSaleBatches]);

  useEffect(() => {
    if (!batches.length) {
      setProductId("");
      return;
    }
    setProductId((prev) => {
      const still = batches.some((b) => String(b.id) === prev);
      if (still) return prev;
      return batches[0]?.id ? String(batches[0].id) : "";
    });
  }, [batches, selectedSku]);

  const prefetchOpenSkus = () => {
    prefetchSaleBatchCluster(
      skus.map((r) => r.sku),
      16
    );
  };

  const p = display.preview;

  return (
    <form
      action={formAction}
      onSubmit={(e) => {
        const fd = new FormData(e.currentTarget);
        if (fd.get("intent") === "submit") {
          addOptimistic({
            ok: false,
            message: "A concluir venda no servidor…",
            preview: state.preview,
          });
        }
      }}
      className="space-y-2"
    >
      <FormAlert state={display.message ? display : undefined} />

      <StepTitle n={1}>SKU e lote</StepTitle>
      <div className="grid gap-5 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="sku_select">SKU disponível</Label>
          <Select
            id="sku_select"
            value={selectedSku}
            onPointerDown={prefetchOpenSkus}
            onChange={(event) => setSelectedSku(event.target.value)}
          >
            {skus.length === 0 ? <option value="">Nenhum SKU com estoque</option> : null}
            {skus.map((sku) => (
              <option key={sku.sku} value={sku.sku}>
                {sku.sku} — {sku.sampleName ?? "sem produto"} · {formatCurrency(sku.sellingPrice)} ·
                estoque {sku.totalStock}
              </option>
            ))}
          </Select>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor="product_id">Lote</Label>
            {loadingBatches ? (
              <span className="text-[10px] text-muted-foreground" aria-live="polite">
                A sincronizar…
              </span>
            ) : null}
          </div>
          <Select
            id="product_id"
            name="product_id"
            value={productId}
            onChange={(event) => setProductId(event.target.value)}
            disabled={batches.length === 0}
          >
            {batches.length === 0 ? <option value="">Sem lotes disponíveis</option> : null}
            {batches.map((batch) => (
              <option key={batch.id} value={batch.id}>
                {batch.productEnterCode ?? `Lote ${batch.id}`} — estoque {batch.stock}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <StepTitle n={2}>Cliente</StepTitle>
      <div className="grid gap-5 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="cust_search">Buscar por nome ou código</Label>
          <Input
            id="cust_search"
            value={custSearch}
            onChange={(e) => setCustSearch(e.target.value)}
            placeholder="Filtrar a lista…"
            autoComplete="off"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="customer_id">Cliente</Label>
          <Select id="customer_id" name="customer_id" defaultValue="" required>
            <option value="">— selecionar cliente —</option>
            {filteredCustomers.map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.customerCode} · {customer.name}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <StepTitle n={3}>Quantidade</StepTitle>
      <div className="space-y-2 md:max-w-xs">
        <Label htmlFor="quantity">Quantidade a vender</Label>
        {productId && batchStock > 0 ? (
          <p className="text-xs text-muted-foreground">
            Disponível neste lote: <strong>{batchStock}</strong> (não venda acima do estoque).
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">Conclua a etapa 1 para informar a quantidade.</p>
        )}
        <Input
          key={`qty-${productId || "none"}`}
          id="quantity"
          name="quantity"
          type="number"
          min={1}
          max={batchStock > 0 ? batchStock : undefined}
          step={1}
          defaultValue={1}
          required
          disabled={!productId || batchStock < 1}
        />
      </div>

      <StepTitle n={4}>Desconto</StepTitle>
      <div className="space-y-4">
        <fieldset className="space-y-2">
          <legend className="text-sm text-muted-foreground">Tipo de desconto</legend>
          <div className="flex flex-wrap gap-4">
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input type="radio" name="discount_mode" value="percent" defaultChecked />
              Percentual (%)
            </label>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input type="radio" name="discount_mode" value="fixed" />
              Valor fixo (R$)
            </label>
          </div>
        </fieldset>
        <div className="space-y-2 md:max-w-xs">
          <Label htmlFor="discount_input">Valor (percentual ou R$, conforme tipo acima)</Label>
          <Input
            id="discount_input"
            name="discount_input"
            type="number"
            min={0}
            step={0.01}
            defaultValue={0}
          />
        </div>
      </div>

      <StepTitle n={5}>Forma de pagamento</StepTitle>
      <div className="space-y-2 md:max-w-md">
        <Label htmlFor="payment_method">Forma de pagamento</Label>
        <Select id="payment_method" name="payment_method" defaultValue={SALE_PAYMENT_OPTIONS[0]} required>
          {SALE_PAYMENT_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </Select>
      </div>

      <StepTitle n={6}>Conferência e confirmação</StepTitle>
      <p className="text-sm text-muted-foreground">
        O servidor <strong>sempre</strong> revalida totais ao concluir a venda. Use{" "}
        <strong>Atualizar resumo</strong> para conferir na tela antes de confirmar (recomendado após mudar
        quantidade, cliente, desconto ou pagamento).
      </p>

      <div className="space-y-4 rounded-2xl border border-border bg-muted/20 p-4 sm:p-5">
        {p ? <SalePreviewPanel preview={p} /> : (
          <p className="text-sm text-muted-foreground">
            Preencha as etapas anteriores. Opcionalmente clique em <strong>Atualizar resumo</strong> para ver o
            resumo validado no servidor antes de concluir.
          </p>
        )}
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-white/10 p-4">
        <label className="flex cursor-pointer items-start gap-3 text-sm">
          <input type="checkbox" name="confirm_sale" value="on" className="mt-1" />
          <span>
            Confirmo esta venda (o estoque será baixado e o registro de venda será criado).
          </span>
        </label>
      </div>

      <SaleFormActions canAct={Boolean(productId)} />
    </form>
  );
}

function SaleFormActions({ canAct }: { canAct: boolean }) {
  const { pending } = useFormStatus();
  return (
    <div className="flex flex-wrap justify-end gap-3 pt-2">
      <Button
        type="submit"
        name="intent"
        value="preview"
        formNoValidate
        variant="outline"
        disabled={!canAct || pending}
      >
        Atualizar resumo
      </Button>
      <SubmitButton name="intent" value="submit" disabled={!canAct || pending}>
        Concluir venda
      </SubmitButton>
    </div>
  );
}

function SalePreviewPanel({ preview: p }: { preview: SalePreview }) {
  const discountRule =
    p.discountMode === "percent"
      ? `${p.discountInput}% sobre o subtotal (teto: 100%; valor aplicado nunca ultrapassa o subtotal).`
      : `Valor fixo em reais (o aplicado é no máximo igual ao subtotal).`;

  return (
    <div className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-border/60 bg-background/60 p-4">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Produto e lote</h4>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">SKU</dt>
              <dd className="text-right font-medium text-foreground">{p.sku?.trim() || "—"}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Lote (produto)</dt>
              <dd className="text-right font-mono text-xs text-foreground">#{p.productId}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Stock disponível</dt>
              <dd className="text-right tabular-nums text-foreground">{formatNumber(p.stock)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Quantidade a vender</dt>
              <dd className="text-right font-semibold tabular-nums text-foreground">{formatNumber(p.quantity)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Preço unitário (ativo)</dt>
              <dd className="text-right font-medium tabular-nums text-foreground">{formatCurrency(p.unitPrice)}</dd>
            </div>
          </dl>
        </div>

        <div className="rounded-xl border border-border/60 bg-background/60 p-4">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Cliente e pagamento</h4>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Cliente</dt>
              <dd className="max-w-[min(100%,14rem)] text-right text-foreground">{p.customerLabel}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Pagamento</dt>
              <dd className="text-right text-foreground">{p.paymentMethod}</dd>
            </div>
          </dl>
        </div>
      </div>

      <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-4">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Desconto</h4>
        <p className="mt-2 text-sm text-foreground">{discountRule}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Entrada no formulário:{" "}
          <strong className="text-foreground">
            {p.discountMode === "percent" ? `${p.discountInput}%` : formatCurrency(p.discountInput)}
          </strong>{" "}
          → aplicado: <strong className="text-foreground">{formatCurrency(p.discountAmount)}</strong>
        </p>
      </div>

      <div className="border-t border-border/60 pt-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <Summary label="Subtotal (qtd × unitário)" value={formatCurrency(p.basePrice)} />
          <Summary label="Desconto aplicado" value={formatCurrency(p.discountAmount)} />
          <Summary label="Total a cobrar" value={formatCurrency(p.finalTotal)} highlight />
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Confirme os valores acima antes de marcar a caixa e concluir a venda.
        </p>
      </div>
    </div>
  );
}

function Summary({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{label}</p>
      <p className={`mt-2 font-serif text-2xl tabular-nums ${highlight ? "text-[#d4b36c]" : "text-foreground"}`}>
        {value}
      </p>
    </div>
  );
}
