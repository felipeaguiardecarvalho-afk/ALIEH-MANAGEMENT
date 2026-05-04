"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/** Aviso curto ao abrir detalhe (equivalente a `st.success` ao seleccionar no Streamlit). */
export function ProductSelectionToast({
  productId,
  name,
  sku,
  durationMs = 2800,
}: {
  productId: number;
  name: string;
  sku: string;
  durationMs?: number;
}) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    setVisible(true);
    const t = window.setTimeout(() => setVisible(false), durationMs);
    return () => window.clearTimeout(t);
  }, [productId, durationMs]);

  if (!visible) return null;

  const label = (name || "").trim() || "Produto";
  const sk = (sku || "").trim() || "—";

  return (
    <div
      role="status"
      className={cn(
        "pointer-events-none fixed bottom-6 left-1/2 z-[55] max-w-lg -translate-x-1/2 rounded-lg border border-primary/25 bg-background/95 px-4 py-2.5 text-center text-xs text-muted-foreground shadow-md backdrop-blur-sm"
      )}
    >
      Produto selecionado: <span className="font-medium text-foreground">{label}</span> (SKU:{" "}
      <span className="font-mono text-foreground">{sk}</span>)
    </div>
  );
}
