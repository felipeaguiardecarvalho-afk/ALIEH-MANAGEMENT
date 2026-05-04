import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { NewProductForm } from "./new-product-form";
import { mergeDomainWithApiAttributeOptions } from "@/lib/product-attribute-presets";
import { fetchPrototypeProductAttributeOptions } from "@/lib/products-api";
import { resolveRole } from "@/lib/tenant";

export default async function NewProductPage() {
  const role = await resolveRole();
  const isAdmin = role === "admin";

  let merged = mergeDomainWithApiAttributeOptions(null);
  try {
    const api = await fetchPrototypeProductAttributeOptions();
    merged = mergeDomainWithApiAttributeOptions(api);
  } catch {
    /* domain-only presets */
  }

  return (
    <div className="space-y-10 pb-20">
      {/* Editorial header */}
      <header className="space-y-5 pt-2">
        <Link
          href="/products"
          className="inline-flex items-center gap-1.5 text-xs uppercase tracking-[0.18em] text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-3 w-3" /> Catálogo
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-6 border-b border-border/40 pb-6">
          <div className="max-w-2xl">
            <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">Novo lote</p>
            <h1 className="mt-2 font-serif text-5xl font-semibold tracking-tight md:text-6xl">
              Cadastrar produto
            </h1>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              Estoque inicial é zero — registre uma entrada em <strong className="text-foreground">Custos</strong>{" "}
              depois. O SKU é gerado pelo servidor a partir do nome e atributos. Não é possível cadastrar dois lotes
              com o mesmo corpo (nome + data + atributos) nem com o mesmo SKU.
            </p>
          </div>
        </div>
      </header>

      <NewProductForm attributeOptions={merged} isAdmin={isAdmin} />
    </div>
  );
}
