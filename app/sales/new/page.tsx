import { NewSaleForm } from "./new-sale-form";
import { PageHero } from "@/components/page-hero";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getCustomers, getSaleableSkus } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function NewSalePage() {
  const [skus, customers] = await Promise.all([getSaleableSkus(), getCustomers()]);

  return (
    <div className="space-y-6">
      <PageHero
        eyebrow="Comercial"
        title="Nova venda"
        description="Seleção de SKU → lote com estoque → cliente → quantidade → desconto → pagamento. Transação equivalente a `insert_sale_and_decrement_stock`."
      />
      <Card>
        <CardHeader>
          <CardTitle>Execução de venda</CardTitle>
          <CardDescription>
            {skus.length} SKU(s) elegíveis para venda · {customers.length} cliente(s) cadastrados.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <NewSaleForm skus={skus} customers={customers} />
        </CardContent>
      </Card>
    </div>
  );
}
