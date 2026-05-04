import { PageHero } from "@/components/page-hero";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCurrency, formatNumber } from "@/lib/format";
import { getProducts, getSkuMasterRows } from "@/lib/queries";
import { StockReceiptForm } from "./stock-receipt-form";
import { CostStructureForm } from "./cost-structure-form";

export const revalidate = 120;

export default async function CostsPage() {
  const [masters, products] = await Promise.all([getSkuMasterRows(), getProducts()]);

  return (
    <div className="space-y-6">
      <PageHero
        eyebrow="Operação"
        title="Custos"
        description="Composição de custo por SKU e entrada de estoque com custo médio ponderado (equivalente a `save_sku_cost_structure` + `add_stock_receipt`)."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Composição de custo</CardTitle>
            <CardDescription>Persiste 6 componentes por SKU e recomputa o total estruturado.</CardDescription>
          </CardHeader>
          <CardContent>
            <CostStructureForm skus={masters.map((row) => row.sku)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Entrada de estoque</CardTitle>
            <CardDescription>Atualiza `products.stock`, `sku_master.total_stock` e `avg_unit_cost` (CMP).</CardDescription>
          </CardHeader>
          <CardContent>
            <StockReceiptForm products={products} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Valorização atual por SKU</CardTitle>
          <CardDescription>Leitura de `sku_master` com totais e custo médio.</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>SKU</TableHead>
                <TableHead>Estoque</TableHead>
                <TableHead>CMP</TableHead>
                <TableHead>Total estruturado</TableHead>
                <TableHead>Valorização</TableHead>
                <TableHead>Preço atual</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {masters.map((row) => (
                <TableRow key={row.sku}>
                  <TableCell className="font-mono text-[#d4b36c]">{row.sku}</TableCell>
                  <TableCell>{formatNumber(row.totalStock)}</TableCell>
                  <TableCell>{formatCurrency(row.avgUnitCost)}</TableCell>
                  <TableCell>{formatCurrency(row.structuredCostTotal)}</TableCell>
                  <TableCell>{formatCurrency(row.totalStock * row.avgUnitCost)}</TableCell>
                  <TableCell>{formatCurrency(row.sellingPrice)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
