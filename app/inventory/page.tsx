import { PageHero } from "@/components/page-hero";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCurrency, formatNumber } from "@/lib/format";
import { getInventory, getProducts } from "@/lib/queries";
import { WriteDownForm } from "./write-down-form";

export const revalidate = 120;

export default async function InventoryPage() {
  const [items, products] = await Promise.all([getInventory(), getProducts()]);
  const inStockLots = products.filter((product) => product.stock > 0);

  return (
    <div className="space-y-6">
      <PageHero
        eyebrow="Operação"
        title="Estoque"
        description="Resumo por SKU, lotes com estoque e baixa manual — equivalente à página Estoque (`apply_manual_stock_write_down`)."
      />

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Resumo por SKU</CardTitle>
            <CardDescription>Leitura server-side de `sku_master`.</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>SKU</TableHead>
                  <TableHead>Produto</TableHead>
                  <TableHead>Estoque</TableHead>
                  <TableHead>Custo médio</TableHead>
                  <TableHead>Preço</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.sku}>
                    <TableCell><Badge variant="gold">{item.sku}</Badge></TableCell>
                    <TableCell className="font-medium">{item.sampleName || "Sem produto vinculado"}</TableCell>
                    <TableCell>{formatNumber(item.totalStock)}</TableCell>
                    <TableCell>{formatCurrency(item.avgUnitCost)}</TableCell>
                    <TableCell>{formatCurrency(item.sellingPrice)}</TableCell>
                    <TableCell>
                      <Badge variant={item.totalStock <= 5 ? "gold" : "secondary"}>
                        {item.totalStock <= 5 ? "Baixo" : "OK"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Baixa manual de estoque</CardTitle>
            <CardDescription>Reduz apenas `products.stock`; custo e preço inalterados.</CardDescription>
          </CardHeader>
          <CardContent>
            <WriteDownForm lots={inStockLots} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
