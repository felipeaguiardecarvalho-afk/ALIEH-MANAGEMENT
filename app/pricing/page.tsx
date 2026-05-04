import { PageHero } from "@/components/page-hero";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getSkuMasterRows } from "@/lib/queries";
import { PricingWorkflow } from "./pricing-workflow";

export const dynamic = "force-dynamic";

export default async function PricingPage() {
  const masters = await getSkuMasterRows();

  return (
    <div className="space-y-6">
      <PageHero
        eyebrow="Financeiro"
        title="Precificação"
        description="Markup, taxas e juros (percentual ou absoluto) sobre o CMP — equivalente a `compute_sku_pricing_targets` + `save_sku_pricing_workflow`."
      />

      <Card>
        <CardHeader>
          <CardTitle>Workflow</CardTitle>
          <CardDescription>
            Selecione um SKU; o cálculo é feito em tempo real. Ao salvar, o preço ativo é propagado para
            `sku_master.selling_price` e `products.price`.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <PricingWorkflow rows={masters} />
        </CardContent>
      </Card>
    </div>
  );
}
