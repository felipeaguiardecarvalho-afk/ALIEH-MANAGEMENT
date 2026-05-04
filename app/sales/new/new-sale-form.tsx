"use client";

import { useActionState, useEffect, useMemo, useState, useTransition } from "react";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { recordSale, type SaleFormState } from "@/lib/actions/sales";
import { SALE_PAYMENT_OPTIONS } from "@/lib/domain";
import { formatCurrency } from "@/lib/format";
import type { Customer, ProductBatch, SaleableSku } from "@/lib/types";

const initialState: SaleFormState = { ok: false, message: "" };

export function NewSaleForm({
  skus,
  customers,
}: {
  skus: SaleableSku[];
  customers: Customer[];
}) {
  const [state, formAction] = useActionState(recordSale, initialState);
  const [selectedSku, setSelectedSku] = useState(skus[0]?.sku ?? "");
  const [batches, setBatches] = useState<ProductBatch[]>([]);
  const [productId, setProductId] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [discount, setDiscount] = useState(0);
  const [loadingBatches, startBatchLoad] = useTransition();

  const activeSku = useMemo(() => skus.find((sku) => sku.sku === selectedSku), [skus, selectedSku]);

  useEffect(() => {
    if (!selectedSku) {
      setBatches([]);
      setProductId("");
      return;
    }
    startBatchLoad(async () => {
      const res = await fetch(`/api/batches?sku=${encodeURIComponent(selectedSku)}`);
      const data = (await res.json()) as { batches: ProductBatch[] };
      setBatches(data.batches);
      setProductId(data.batches[0]?.id ? String(data.batches[0].id) : "");
    });
  }, [selectedSku]);

  const unitPrice = activeSku?.sellingPrice ?? 0;
  const gross = unitPrice * quantity;
  const finalTotal = Math.max(0, gross - discount);

  return (
    <form action={formAction} className="space-y-6">
      <FormAlert state={state.message ? state : undefined} />

      <div className="grid gap-5 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="sku_select">SKU disponível</Label>
          <Select
            id="sku_select"
            value={selectedSku}
            onChange={(event) => setSelectedSku(event.target.value)}
          >
            {skus.length === 0 ? <option value="">Nenhum SKU com estoque</option> : null}
            {skus.map((sku) => (
              <option key={sku.sku} value={sku.sku}>
                {sku.sku} — {sku.sampleName ?? "sem produto"} · {formatCurrency(sku.sellingPrice)} · estoque {sku.totalStock}
              </option>
            ))}
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="product_id">Lote</Label>
          <Select
            id="product_id"
            name="product_id"
            value={productId}
            onChange={(event) => setProductId(event.target.value)}
            disabled={loadingBatches || batches.length === 0}
          >
            {loadingBatches ? <option value="">Carregando lotes...</option> : null}
            {!loadingBatches && batches.length === 0 ? <option value="">Sem lotes disponíveis</option> : null}
            {batches.map((batch) => (
              <option key={batch.id} value={batch.id}>
                {batch.productEnterCode ?? `Lote ${batch.id}`} — estoque {batch.stock}
              </option>
            ))}
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="customer_id">Cliente</Label>
          <Select id="customer_id" name="customer_id" defaultValue="">
            <option value="">— selecionar cliente —</option>
            {customers.map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.customerCode} · {customer.name}
              </option>
            ))}
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="quantity">Quantidade</Label>
          <Input
            id="quantity"
            name="quantity"
            type="number"
            min={1}
            value={quantity}
            onChange={(event) => setQuantity(Math.max(1, Number(event.target.value) || 1))}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="discount_amount">Desconto (R$)</Label>
          <Input
            id="discount_amount"
            name="discount_amount"
            type="number"
            min={0}
            step="0.01"
            value={discount}
            onChange={(event) => setDiscount(Math.max(0, Number(event.target.value) || 0))}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="payment_method">Forma de pagamento</Label>
          <Select id="payment_method" name="payment_method" defaultValue={SALE_PAYMENT_OPTIONS[0]}>
            {SALE_PAYMENT_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div className="grid gap-3 rounded-2xl border border-border bg-muted/20 p-4 sm:grid-cols-3">
        <Summary label="Preço unitário" value={formatCurrency(unitPrice)} />
        <Summary label="Subtotal" value={formatCurrency(gross)} />
        <Summary label="Total final" value={formatCurrency(finalTotal)} highlight />
      </div>

      <div className="flex justify-end">
        <SubmitButton>Concluir venda</SubmitButton>
      </div>
    </form>
  );
}

function Summary({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{label}</p>
      <p className={`mt-2 font-serif text-2xl ${highlight ? "text-[#d4b36c]" : ""}`}>{value}</p>
    </div>
  );
}
