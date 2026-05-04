import { NewSaleForm } from "./new-sale-form";
import { PageHero } from "@/components/page-hero";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { mapCustomerApiRowsToCustomers } from "@/lib/customers-map";
import { fetchPrototypeCustomersList } from "@/lib/customers-api";
import { fetchPrototypeSaleableSkus } from "@/lib/sales-api";
import type { Customer, SaleableSku } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function NewSalePage() {
  let skus: SaleableSku[] = [];
  let customers: Customer[] = [];
  let loadError: string | null = null;

  try {
    const [skuData, custRows] = await Promise.all([
      fetchPrototypeSaleableSkus(),
      fetchPrototypeCustomersList(),
    ]);
    skus = skuData;
    customers = mapCustomerApiRowsToCustomers(custRows);
  } catch (e) {
    loadError = e instanceof Error ? e.message : "Falha ao carregar dados da API.";
  }

  return (
    <div className="space-y-6">
      <PageHero
        eyebrow="Comercial"
        title="Nova venda"
        description="Fluxo alinhado à app Streamlit: SKU → lote → cliente → quantidade → desconto (% ou R$) → pagamento → resumo no servidor → confirmação → gravação via api-prototype."
      />
      <Card>
        <CardHeader>
          <CardTitle>Execução de venda</CardTitle>
          <CardDescription>
            {loadError ? (
              <span className="text-destructive">{loadError}</span>
            ) : (
              <>
                {skus.length} SKU(s) elegíveis para venda · {customers.length} cliente(s) cadastrados.
              </>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <NewSaleForm skus={skus} customers={customers} />
        </CardContent>
      </Card>
    </div>
  );
}
