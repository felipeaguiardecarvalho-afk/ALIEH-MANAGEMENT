import Link from "next/link";
import { Edit3, ImagePlus, Package, ShieldAlert, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { LotActionState } from "@/lib/actions/products";
import type { ProductAttributeOptions, ProductDetail } from "@/lib/products-api";
import { mergeProductCatalogQuery, type ProductCatalogQuery } from "@/lib/products-url";
import { formatDate, formatProductMoney, formatProductStock } from "@/lib/format";
import { ProductLotEditForm } from "./product-lot-edit-form";
import { ProductLotPhotoForm } from "./product-lot-photo-form";
import { MarkdownHint } from "./product-markdown-hint";
import { ProductSkuDeleteForm } from "./product-sku-delete-form";

const initialLotState: LotActionState = { ok: false, message: "" };

function imageSrc(
  path: string | null | undefined,
  diskImageDataUrl: string | null | undefined
): string | null {
  if (diskImageDataUrl?.trim()) return diskImageDataUrl;
  const p = (path ?? "").trim();
  if (!p) return null;
  if (p.startsWith("https://") || p.startsWith("http://") || p.startsWith("/")) return p;
  return null;
}

function monogram(sku: string | null | undefined, name: string) {
  const s = (sku ?? "").trim();
  if (s) return s.split("-")[0]?.slice(0, 4).toUpperCase() || s.slice(0, 4).toUpperCase();
  const w = name.trim().split(/\s+/);
  return ((w[0]?.[0] ?? "") + (w[1]?.[0] ?? "")).toUpperCase() || "—";
}

function marginPct(price: number | string | null | undefined, cost: number | string | null | undefined) {
  const p = Number(price);
  const c = Number(cost);
  if (!Number.isFinite(p) || !Number.isFinite(c) || p <= 0) return null;
  return ((p - c) / p) * 100;
}

export function ProductDetailAside({
  product,
  options,
  listQuery,
  isAdmin,
  diskImageDataUrl,
}: {
  product: ProductDetail;
  options: ProductAttributeOptions;
  listQuery: ProductCatalogQuery;
  isAdmin: boolean;
  diskImageDataUrl?: string | null;
}) {
  const closeHref = `/products${mergeProductCatalogQuery(listQuery, { detail: null })}`;
  const sku = (product.sku ?? "").trim();
  const enterCode = (product.product_enter_code ?? "").trim();
  const imgUrl = imageSrc(product.product_image_path, diskImageDataUrl ?? null);
  const skuDeleteBlock = product.sku_delete_block_reason?.trim() || null;
  const lotEditBlock = product.lot_edit_block_reason?.trim() || null;
  const skuDeleteEnabled = isAdmin && Boolean(sku) && !skuDeleteBlock;
  const inventoryHref = sku !== "" ? `/inventory?skus=${encodeURIComponent(sku)}` : "/inventory";

  const margin = marginPct(product.sell_price, product.avg_cost);

  const attrPairs: Array<[string, string | null | undefined]> = [
    ["Armação", product.frame_color],
    ["Lente", product.lens_color],
    ["Gênero", product.gender],
    ["Paleta", product.palette],
    ["Estilo", product.style],
  ];

  return (
    <>
      <Link
        href={closeHref}
        className="fixed inset-0 z-40 bg-black/55 backdrop-blur-[2px] animate-in fade-in duration-200"
        aria-label="Fechar painel"
      />
      <aside
        className="fixed inset-x-0 bottom-0 top-auto z-50 flex h-[94vh] w-full flex-col rounded-t-2xl border-t border-border/80 bg-background shadow-2xl animate-in slide-in-from-bottom duration-300 ease-out md:inset-y-0 md:left-auto md:right-0 md:top-0 md:h-full md:max-w-2xl md:rounded-none md:border-l md:border-t-0 md:slide-in-from-right"
        role="dialog"
        aria-modal="true"
        aria-labelledby="product-panel-title"
      >
        {/* Sticky close strip */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border/40 bg-background/95 px-6 py-3 backdrop-blur supports-[backdrop-filter]:bg-background/75">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.28em] text-muted-foreground">
            <Link href="/products" className="transition-colors hover:text-foreground">Catálogo</Link>
            <span className="h-px w-4 bg-border/70" />
            <span className="text-[#d4b36c]">Detalhe</span>
          </div>
          <Button asChild variant="ghost" size="sm" className="h-8 w-8 p-0 text-muted-foreground">
            <Link href={closeHref} aria-label="Fechar painel">
              <X className="h-4 w-4" />
            </Link>
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* Hero */}
          <section className="px-6 pb-8 pt-7 md:px-8">
            <div className="grid gap-6 md:grid-cols-[200px_minmax(0,1fr)]">
              {/* Image */}
              <div className="relative aspect-square overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-br from-muted/30 via-background to-muted/5">
                {imgUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={imgUrl} alt="" className="absolute inset-0 h-full w-full object-cover" />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="font-serif text-5xl font-semibold tracking-tight text-foreground/15">
                      {monogram(product.sku, product.name)}
                    </span>
                  </div>
                )}
              </div>

              {/* Identity + key metrics */}
              <div className="min-w-0 space-y-5">
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="gold">{sku || "SEM-SKU"}</Badge>
                    {enterCode ? <Badge variant="outline">{enterCode}</Badge> : null}
                  </div>
                  <h2
                    id="product-panel-title"
                    className="font-serif text-3xl font-semibold leading-tight tracking-tight text-foreground md:text-4xl"
                  >
                    {product.name}
                  </h2>
                  <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                    registo <span className="text-foreground tabular-nums">{formatDate(product.registered_date)}</span>
                    {product.created_at ? (
                      <>
                        <span className="mx-2 inline-block h-px w-3 bg-border/60 align-middle" />
                        criado <span className="text-foreground tabular-nums">{formatDate(product.created_at)}</span>
                      </>
                    ) : null}
                  </p>
                </div>

                {/* Inline metrics */}
                <div className="grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-border/60 bg-border/60">
                  <Metric
                    label="Estoque"
                    value={formatProductStock(product.stock)}
                    tone={Number(product.stock) <= 0 ? "neg" : Number(product.stock) <= 5 ? "warn" : "default"}
                  />
                  <Metric label="Preço" value={formatProductMoney(product.sell_price)} accent />
                  <Metric
                    label="Margem"
                    value={margin == null ? "—" : `${margin.toFixed(1)}%`}
                    tone={margin != null && margin < 25 ? "warn" : "default"}
                  />
                </div>

                {/* Quick actions */}
                <div className="flex flex-wrap items-center gap-2">
                  <Button asChild variant="outline" size="sm" className="h-8 gap-1.5">
                    <Link href={inventoryHref}>
                      <Package className="h-3.5 w-3.5" /> Estoque
                    </Link>
                  </Button>
                  <Button asChild variant="ghost" size="sm" className="h-8">
                    <Link href="/costs">Custos</Link>
                  </Button>
                  <Button asChild variant="ghost" size="sm" className="h-8">
                    <Link href="/pricing">Precificação</Link>
                  </Button>
                  <Button asChild variant="luxury" size="sm" className="h-8">
                    <Link href="/sales/new">Nova venda</Link>
                  </Button>
                </div>
              </div>
            </div>
          </section>

          {/* Attributes */}
          <section className="border-t border-border/40 px-6 py-7 md:px-8">
            <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Atributos</p>
            <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
              {attrPairs.map(([k, v]) => (
                <div key={k} className="space-y-1">
                  <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{k}</p>
                  {v?.trim() ? (
                    <Badge variant="secondary" className="font-medium">{v}</Badge>
                  ) : (
                    <span className="text-sm text-muted-foreground/60">—</span>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* Cost & pricing block */}
          <section className="border-t border-border/40 px-6 py-7 md:px-8">
            <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Custo e preço (por SKU)</p>
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <DataRow label="Custo médio" value={formatProductMoney(product.avg_cost)} />
              <DataRow label="Preço de venda" value={formatProductMoney(product.sell_price)} accent />
            </div>
            <p className="mt-4 text-xs leading-5 text-muted-foreground">
              Custos, precificação e vendas ligam-se ao mesmo SKU. Para ajustar stock por lote use{" "}
              <Link href={inventoryHref} className="text-foreground underline-offset-4 hover:underline">
                Estoque
              </Link>
              .
            </p>
          </section>

          {/* Photo upload */}
          <section className="border-t border-border/40 px-6 py-7 md:px-8">
            <div className="mb-4 flex items-center gap-2">
              <ImagePlus className="h-3.5 w-3.5 text-[#d4b36c]" />
              <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Foto do lote</p>
            </div>
            <ProductLotPhotoForm productId={product.id} disabled={!isAdmin} />
          </section>

          {/* Edit form (admin) */}
          <section className="border-t border-border/40 px-6 py-7 md:px-8">
            <div className="mb-4 flex items-center gap-2">
              <Edit3 className="h-3.5 w-3.5 text-[#d4b36c]" />
              <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Editar lote</p>
            </div>
            {isAdmin ? (
              <ProductLotEditForm product={product} options={options} initialState={initialLotState} />
            ) : (
              <div className="space-y-3">
                {lotEditBlock ? (
                  <div className="rounded-lg border border-[#c7a35b]/30 bg-muted/20 px-3 py-2 text-xs text-muted-foreground [&_strong]:text-foreground">
                    <MarkdownHint text={lotEditBlock} />
                  </div>
                ) : null}
                <p className="text-xs text-muted-foreground">
                  Apenas administradores podem alterar nome, data e atributos ou gravar uma nova foto (paridade com Streamlit).
                </p>
              </div>
            )}
          </section>

          {/* Activity / meta + danger zone */}
          {sku ? (
            <section className="border-t border-border/40 px-6 py-7 md:px-8">
              <div className="mb-4 flex items-center gap-2">
                <ShieldAlert className="h-3.5 w-3.5 text-destructive/80" />
                <p className="text-[10px] uppercase tracking-[0.28em] text-destructive/90">Zona crítica</p>
              </div>
              <p className="text-xs leading-5 text-muted-foreground">
                Elimina todos os lotes e o registo mestre deste SKU no inquilino actual, apenas se não existirem
                vendas, stock, custos ou precificação associados. Operação irreversível.
              </p>
              {skuDeleteBlock ? (
                <div className="mt-3 rounded-md border border-border/60 bg-muted/20 px-3 py-2 text-xs text-muted-foreground [&_strong]:text-foreground">
                  <MarkdownHint text={skuDeleteBlock} />
                </div>
              ) : isAdmin ? (
                <p className="mt-3 text-xs text-muted-foreground">
                  Sem estoque, custos, preços ou vendas para este SKU — pode excluir definitivamente o cadastro.
                </p>
              ) : null}
              {!isAdmin ? (
                <p className="mt-3 text-xs text-muted-foreground">
                  A exclusão permanente de SKU é reservada a <strong className="text-foreground">administradores</strong>;
                  o botão permanece visível e bloqueado para operadores (como no Streamlit).
                </p>
              ) : null}
              <div className="mt-4">
                <ProductSkuDeleteForm
                  sku={sku}
                  disabled={!skuDeleteEnabled}
                  listReturnHref={`/products${mergeProductCatalogQuery(listQuery, { detail: null })}`}
                />
              </div>
            </section>
          ) : null}

          <div className="px-6 py-8 md:px-8">
            <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">
              ID interno · <span className="tabular-nums text-muted-foreground">{product.id}</span>
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}

function Metric({
  label,
  value,
  tone,
  accent,
}: {
  label: string;
  value: string;
  tone?: "default" | "warn" | "neg";
  accent?: boolean;
}) {
  const valueColor =
    tone === "neg"
      ? "text-destructive"
      : tone === "warn"
        ? "text-[#d4b36c]"
        : accent
          ? "text-foreground"
          : "text-foreground";
  return (
    <div className="bg-background p-4">
      <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
      <p className={`mt-1.5 font-serif text-xl font-semibold tabular-nums tracking-tight ${valueColor}`}>
        {value}
      </p>
    </div>
  );
}

function DataRow({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/30 pb-2 last:border-b-0 sm:border-0 sm:pb-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={`font-serif text-lg tabular-nums ${accent ? "text-foreground" : "text-foreground/90"}`}>
        {value}
      </span>
    </div>
  );
}
