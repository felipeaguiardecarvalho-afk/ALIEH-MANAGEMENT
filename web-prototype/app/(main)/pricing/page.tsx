import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchCostsSkuOptions } from "@/lib/costs-api";
import { fetchPrototypeSkuMasterList } from "@/lib/pricing-api";
import { requireAdminForPricing } from "@/lib/rbac";
import { PricingWorkflow } from "./pricing-workflow";

export const dynamic = "force-dynamic";

export default async function PricingPage() {
  const denied = await requireAdminForPricing();
  if (denied) {
    return (
      <div className="space-y-8 pb-16">
        <PricingHeader />
        <Card className="border-border/80">
          <CardHeader>
            <CardTitle>Acesso negado</CardTitle>
            <CardDescription>{denied.message}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  let error: string | null = null;
  let masters: Awaited<ReturnType<typeof fetchPrototypeSkuMasterList>> = [];
  let pickByName: Awaited<ReturnType<typeof fetchCostsSkuOptions>>["pick_by_name"] = [];

  try {
    [masters, { pick_by_name: pickByName }] = await Promise.all([
      fetchPrototypeSkuMasterList(),
      fetchCostsSkuOptions(),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : "Não foi possível carregar SKUs.";
  }

  const emptySkus = !error && masters.length === 0;

  return (
    <div className="space-y-8 pb-16">
      <PricingHeader />

      {error ? (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-destructive">Erro ao carregar</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Verifique <code className="rounded bg-muted px-1">API_PROTOTYPE_URL</code> e a sessão.
          </CardContent>
        </Card>
      ) : null}

      {emptySkus ? (
        <Card>
          <CardHeader>
            <CardTitle>Sem SKUs</CardTitle>
            <CardDescription className="text-foreground/90">
              Ainda não há SKUs. Cadastre produtos em{" "}
              <Link href="/products" className="text-foreground underline-offset-4 hover:underline">
                Produtos
              </Link>{" "}
              primeiro.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : null}

      {!error && !emptySkus ? (
        <PricingWorkflow rows={masters} pickByName={pickByName} />
      ) : null}
    </div>
  );
}

function PricingHeader() {
  return (
    <header>
      <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">Financeiro · Precificação</p>
      <h1 className="mt-2 font-serif text-5xl font-semibold tracking-tight md:text-6xl">Pricing engine</h1>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">
        Configure margem, impostos e encargos por SKU. O cálculo usa o mesmo motor que persiste; ao salvar, o
        preço alvo propaga para <code className="rounded bg-muted px-1 text-xs">sku_master.selling_price</code> e{" "}
        <code className="rounded bg-muted px-1 text-xs">products.price</code>.
      </p>
    </header>
  );
}
