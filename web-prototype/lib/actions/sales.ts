"use server";

import { revalidatePath } from "next/cache";
import {
  apiPrototypeFetch,
  gateMutation,
  hasPrototypeApiUrl,
  readApiError,
} from "@/lib/api-prototype";
import { formatProductMoney } from "@/lib/format";
import { fetchPrototypeBatchesForSkuCached } from "@/lib/inventory-api";
import { logPrototypeAuditEvent } from "@/lib/prototype-audit";
import { requireOperator } from "@/lib/rbac";
import { SALE_PAYMENT_OPTIONS } from "@/lib/domain";
import type { ProductBatch } from "@/lib/types";

const DISCOUNT_INPUT_EPS = 1e-4;

export type SalePreview = {
  basePrice: number;
  discountAmount: number;
  finalTotal: number;
  unitPrice: number;
  stock: number;
  sku: string;
  quantity: number;
  productId: number;
  customerId: number;
  discountMode: "percent" | "fixed";
  discountInput: number;
  paymentMethod: string;
  customerLabel: string;
};

export type SaleFormState = {
  ok: boolean;
  message: string;
  preview: SalePreview | null;
};

function str(value: FormDataEntryValue | null) {
  return typeof value === "string" ? value.trim() : "";
}

function num(value: FormDataEntryValue | null) {
  if (typeof value !== "string") return 0;
  return Number(value.replace(",", ".")) || 0;
}

function parseDiscountMode(raw: FormDataEntryValue | null): "percent" | "fixed" {
  return typeof raw === "string" && raw.trim() === "fixed" ? "fixed" : "percent";
}

type SalePreviewApi = {
  product_id: number;
  customer_id?: number;
  base_price: number;
  discount_amount: number;
  final_total: number;
  unit_price: number;
  stock: number;
  sku: string;
  quantity: number;
  discount_mode: string;
  discount_input: number;
  payment_method: string;
  customer_label: string;
};

function mapPreviewApiToSalePreview(p: SalePreviewApi, customerIdFallback: number): SalePreview {
  const dm = p.discount_mode === "fixed" ? "fixed" : "percent";
  return {
    productId: p.product_id,
    customerId: Math.floor(Number(p.customer_id ?? customerIdFallback)),
    basePrice: Number(p.base_price),
    discountAmount: Number(p.discount_amount),
    finalTotal: Number(p.final_total),
    unitPrice: Number(p.unit_price),
    stock: Number(p.stock),
    sku: String(p.sku ?? ""),
    quantity: Math.floor(Number(p.quantity)),
    discountMode: dm,
    discountInput: Number(p.discount_input),
    paymentMethod: String(p.payment_method ?? ""),
    customerLabel: String(p.customer_label ?? ""),
  };
}

function paymentMatches(a: string, b: string) {
  return a.trim() === b.trim();
}

/** O resumo mostrado ainda corresponde aos campos actuais do formulário? */
function previewStaleMatchesForm(
  stale: SalePreview,
  productId: number,
  customerId: number,
  quantity: number,
  discountMode: "percent" | "fixed",
  discountInput: number,
  paymentMethod: string
): boolean {
  if (stale.productId !== productId) return false;
  if (stale.customerId !== customerId) return false;
  if (stale.quantity !== quantity) return false;
  if (stale.discountMode !== discountMode) return false;
  if (Math.abs(stale.discountInput - discountInput) > DISCOUNT_INPUT_EPS) return false;
  if (!paymentMatches(stale.paymentMethod, paymentMethod)) return false;
  return true;
}

async function postSalePreview(body: {
  product_id: number;
  quantity: number;
  customer_id: number;
  discount_mode: string;
  discount_input: number;
  payment_method: string;
}): Promise<SalePreviewApi> {
  const res = await apiPrototypeFetch("/sales/preview", {
    method: "POST",
    json: body,
  });
  if (!res.ok) {
    const detail = await readApiError(res);
    throw new Error(detail);
  }
  return (await res.json()) as SalePreviewApi;
}

export async function loadSaleBatchesAction(sku: string): Promise<ProductBatch[]> {
  const s = (sku || "").trim();
  if (!s || !hasPrototypeApiUrl()) return [];
  try {
    return await fetchPrototypeBatchesForSkuCached(s);
  } catch {
    return [];
  }
}

export async function submitSaleForm(
  _prev: SaleFormState,
  formData: FormData
): Promise<SaleFormState> {
  const emptyPreview: SaleFormState = {
    ok: false,
    message: "",
    preview: _prev.preview ?? null,
  };

  if (!hasPrototypeApiUrl()) {
    return {
      ...emptyPreview,
      ok: false,
      message: "Defina API_PROTOTYPE_URL (vendas via api-prototype).",
    };
  }

  const rbac = await requireOperator();
  if (rbac) return { ...emptyPreview, ok: false, message: rbac.message };

  const gate = await gateMutation();
  if (gate) return { ...emptyPreview, ok: false, message: gate.message };

  const intent = str(formData.get("intent")) || "submit";

  const productId = Math.floor(Number(str(formData.get("product_id"))));
  const customerId = Math.floor(Number(str(formData.get("customer_id"))));
  const quantity = Math.max(1, Math.floor(num(formData.get("quantity"))));
  const discountMode = parseDiscountMode(formData.get("discount_mode"));
  const discountInput = Math.max(0, num(formData.get("discount_input")));
  const paymentMethodRaw = str(formData.get("payment_method"));
  const paymentMethod = (
    paymentMethodRaw ? paymentMethodRaw : SALE_PAYMENT_OPTIONS[0]
  ) as (typeof SALE_PAYMENT_OPTIONS)[number];

  if (!productId) {
    return { ...emptyPreview, ok: false, message: "Selecione um lote (produto)." };
  }
  if (!customerId) {
    return { ...emptyPreview, ok: false, message: "Selecione um cliente." };
  }

  if (intent === "preview") {
    let previewApi: SalePreviewApi;
    try {
      previewApi = await postSalePreview({
        product_id: productId,
        quantity,
        customer_id: customerId,
        discount_mode: discountMode,
        discount_input: discountInput,
        payment_method: paymentMethod,
      });
    } catch (e) {
      return {
        ...emptyPreview,
        ok: false,
        message: e instanceof Error ? e.message : "Falha ao validar venda no servidor.",
      };
    }
    const preview = mapPreviewApiToSalePreview(previewApi, customerId);
    if (!SALE_PAYMENT_OPTIONS.includes(preview.paymentMethod as (typeof SALE_PAYMENT_OPTIONS)[number])) {
      return { ok: false, message: "Forma de pagamento inválida.", preview };
    }
    return {
      ok: true,
      message: "Resumo atualizado (conferência no servidor).",
      preview,
    };
  }

  if (!SALE_PAYMENT_OPTIONS.includes(paymentMethod)) {
    return {
      ok: false,
      message: "Forma de pagamento inválida.",
      preview: _prev.preview ?? null,
    };
  }

  const confirmed = formData.get("confirm_sale") === "on";
  if (!confirmed) {
    return {
      ok: false,
      message:
        "Marque a confirmação para concluir a venda (o estoque será baixado e o registro criado).",
      preview: _prev.preview ?? null,
    };
  }

  if (!_prev.preview) {
    return {
      ok: false,
      message: "Clique em «Atualizar resumo» antes de concluir a venda.",
      preview: null,
    };
  }

  if (
    !previewStaleMatchesForm(
      _prev.preview,
      productId,
      customerId,
      quantity,
      discountMode,
      discountInput,
      paymentMethod
    )
  ) {
    return {
      ok: false,
      message:
        "Os dados do formulário mudaram em relação ao resumo mostrado. Clique em «Atualizar resumo» e confirme de novo.",
      preview: _prev.preview,
    };
  }

  const idempotencyKey = crypto.randomUUID();
  try {
    const res = await apiPrototypeFetch("/sales/submit", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      json: {
        product_id: productId,
        quantity,
        customer_id: customerId,
        discount_mode: discountMode,
        discount_input: discountInput,
        payment_method: paymentMethod,
      },
    });
    if (!res.ok) {
      return {
        ok: false,
        message: await readApiError(res),
        preview: _prev.preview,
      };
    }
    const data = (await res.json()) as { sale_code?: string; final_total?: number };
    const saleCode = String(data.sale_code ?? "");
    const total = Number(data.final_total ?? _prev.preview.finalTotal);
    await logPrototypeAuditEvent("sales", "record_sale", {
      sale_code: saleCode,
      product_id: productId,
      customer_id: customerId,
      quantity: _prev.preview.quantity,
      payment_method: _prev.preview.paymentMethod,
      discount_amount: _prev.preview.discountAmount,
      final_total: total,
    });
    revalidatePath("/sales");
    revalidatePath("/dashboard");
    revalidatePath("/inventory");
    return {
      ok: true,
      message: `Venda ${saleCode} registrada. Total: ${formatProductMoney(total)}`,
      preview: null,
    };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao registrar venda.",
      preview: _prev.preview,
    };
  }
}
