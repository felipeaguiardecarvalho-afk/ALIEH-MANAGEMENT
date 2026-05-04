import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  fetchPrototypeProductAttributeOptions,
  fetchPrototypeProductDetail,
  fetchPrototypeProductDiskImageDataUrl,
  fetchPrototypeProductList,
} from "@/lib/products-api";
import { mergeDomainWithApiAttributeOptions } from "@/lib/product-attribute-presets";
import { mergeProductCatalogQuery, normalizeProductCatalogParams, type ProductCatalogQuery } from "@/lib/products-url";
import { resolveRole } from "@/lib/tenant";
import { NewProductForm } from "./new/new-product-form";
import { ProductDetailAside } from "./product-detail-aside";
import { ProductSelectionToast } from "./product-selection-toast";
import { ProductsCommandHeader } from "./products-command-header";
import { ProductsFilterBar } from "./products-filter-bar";
import { ProductsGallery } from "./products-gallery";
import { ProductsPaginationBar } from "./products-filters";
import { ProductsTable } from "./products-table";

export const revalidate = 30;

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const normalized = normalizeProductCatalogParams(raw);
  const listQuery: ProductCatalogQuery = { ...normalized };
  if (!listQuery.page) listQuery.page = "1";

  const rawView = typeof raw.view === "string" ? raw.view : Array.isArray(raw.view) ? raw.view[0] : undefined;
  const view: "table" | "gallery" = rawView === "gallery" ? "gallery" : "table";

  const role = await resolveRole();
  const isAdmin = role === "admin";

  const listQueryNoDetail: ProductCatalogQuery = { ...listQuery };
  delete listQueryNoDetail.detail;
  const cadastroBase = `/products${mergeProductCatalogQuery(listQueryNoDetail, {})}`;
  const cadastroAnchorHref = `${cadastroBase}${cadastroBase.includes("?") ? "&" : "?"}${
    view === "gallery" ? "view=gallery" : ""
  }`.replace(/[?&]$/, "") + "#cadastro-produto";

  let listError: string | null = null;
  let detailError: string | null = null;
  let list: Awaited<ReturnType<typeof fetchPrototypeProductList>> | null = null;
  let detail: Awaited<ReturnType<typeof fetchPrototypeProductDetail>> | null | undefined = undefined;
  let detailDiskImageDataUrl: string | null = null;

  const [attrOutcome, listOutcome] = await Promise.allSettled([
    fetchPrototypeProductAttributeOptions(),
    fetchPrototypeProductList(listQuery),
  ]);
  const attributeOptions = mergeDomainWithApiAttributeOptions(
    attrOutcome.status === "fulfilled" ? attrOutcome.value : null
  );
  if (listOutcome.status === "rejected") {
    const e = listOutcome.reason;
    listError =
      e instanceof Error && e.message.trim()
        ? e.message
        : "Não foi possível carregar produtos. Verifique a ligação à API.";
  } else {
    list = listOutcome.value;
  }

  const detailIdRaw = normalized.detail?.trim();
  const detailId = detailIdRaw ? Number(detailIdRaw) : NaN;
  const detailRequested = Boolean(list && Number.isFinite(detailId) && detailId > 0);
  if (detailRequested) {
    try {
      detail = await fetchPrototypeProductDetail(detailId);
      const p = detail?.product_image_path?.trim();
      if (detail && p && !/^https?:\/\//i.test(p)) {
        detailDiskImageDataUrl = await fetchPrototypeProductDiskImageDataUrl(detailId);
      }
    } catch (e) {
      detailError = e instanceof Error ? e.message : "Falha ao carregar detalhe.";
    }
  }

  return (
    <div className="space-y-10 pb-16">
      {listError ? (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-destructive">Erro ao carregar lista</CardTitle>
            <CardDescription>{listError}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>
              Em <code className="rounded bg-muted px-1">next dev</code> a URL e o utilizador da API têm valores por
              omissão (<code className="rounded bg-muted px-1">http://127.0.0.1:8000</code> e id{" "}
              <code className="rounded bg-muted px-1">1</code>). É preciso a FastAPI a correr: na raiz do repo execute{" "}
              <code className="rounded bg-muted px-1">npm run dev:api</code>.
            </p>
            <p>
              Em produção defina <code className="rounded bg-muted px-1">API_PROTOTYPE_URL</code> e{" "}
              <code className="rounded bg-muted px-1">API_PROTOTYPE_USER_ID</code> (ou cookies de sessão).
            </p>
          </CardContent>
        </Card>
      ) : null}

      {detailError ? (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-destructive">Erro ao carregar detalhe</CardTitle>
            <CardDescription>{detailError}</CardDescription>
          </CardHeader>
        </Card>
      ) : null}

      {!listError && list ? (
        <>
          <ProductsCommandHeader
            query={listQuery}
            rows={list.items}
            total={list.total}
            view={view}
            cadastroAnchorHref={cadastroAnchorHref}
          />

          <div className="space-y-4">
            <ProductsFilterBar options={attributeOptions} query={listQuery} view={view === "gallery" ? "gallery" : undefined} />

            {view === "gallery" ? (
              <ProductsGallery rows={list.items} listQuery={listQuery} view="gallery" />
            ) : (
              <ProductsTable rows={list.items} listQuery={listQuery} />
            )}

            <ProductsPaginationBar
              query={listQuery}
              total={list.total}
              page={list.page}
              pageSize={list.page_size}
              view={view === "gallery" ? "gallery" : undefined}
            />
          </div>
        </>
      ) : null}

      {!detailError && detail ? (
        <>
          <ProductSelectionToast productId={detail.id} name={detail.name} sku={detail.sku ?? ""} />
          <ProductDetailAside
            product={detail}
            options={attributeOptions}
            listQuery={listQuery}
            isAdmin={isAdmin}
            diskImageDataUrl={detailDiskImageDataUrl}
          />
        </>
      ) : null}

      {!detailError && detailRequested && detail === null && list ? (
        <Card className="border-amber-500/40">
          <CardContent className="py-6 text-sm text-muted-foreground">
            Produto não encontrado ou excluído. Atualize a busca e seleccione de novo.{" "}
            <Button variant="ghost" className="h-auto px-0 text-primary underline-offset-4 hover:underline" asChild>
              <Link href={`/products${mergeProductCatalogQuery(listQuery, { detail: null })}`}>Voltar à lista</Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {/* Cadastro section — distinct visual zone */}
      <section
        id="cadastro-produto"
        className="scroll-mt-24 space-y-5 border-t border-border/40 pt-10"
      >
        <div className="space-y-1.5">
          <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">Novo lote</p>
          <h2 className="font-serif text-3xl font-semibold tracking-tight">Cadastro de produto</h2>
          <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
            Cadastre apenas <strong className="text-foreground">novos lotes</strong> (identidade + atributos;{" "}
            <strong className="text-foreground">foto opcional</strong>). Exclusão de stock é feita em{" "}
            <strong className="text-foreground">Estoque</strong>. Não é possível cadastrar de novo o mesmo{" "}
            <strong className="text-foreground">nome + data + atributos</strong> nem um lote com o mesmo{" "}
            <strong className="text-foreground">SKU</strong> (corpo idêntico). O SKU é gerado no servidor.{" "}
            <strong className="text-foreground">Estoque</strong> e <strong className="text-foreground">custo</strong>{" "}
            entram em <strong className="text-foreground">Custos</strong> (média por SKU).
          </p>
          <p className="text-xs text-muted-foreground">
            Também pode abrir{" "}
            <Link className="text-primary underline-offset-4 hover:underline" href="/products/new">
              só o formulário de cadastro
            </Link>{" "}
            noutra vista.
          </p>
        </div>
        <NewProductForm attributeOptions={attributeOptions} isAdmin={isAdmin} />
      </section>
    </div>
  );
}
