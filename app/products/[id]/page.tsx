import { redirect } from "next/navigation";

/** Compat: `/products/123` → lista com painel de detalhe (mesmo fluxo que `?detail=123`). */
export default async function ProductLegacyDetailRedirect({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const n = Number(id);
  if (!Number.isFinite(n) || n < 1) {
    redirect("/products");
  }
  redirect(`/products?detail=${encodeURIComponent(String(n))}`);
}
