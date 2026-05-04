import Link from "next/link";
import { Plus } from "lucide-react";
import { PageHero } from "@/components/page-hero";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCurrency, formatDate, formatNumber } from "@/lib/format";
import { getRecentSales } from "@/lib/queries";

export const revalidate = 120;

export default async function SalesPage() {
  const sales = await getRecentSales();

  return (
    <div className="space-y-6">
      <PageHero
        eyebrow="Comercial"
        title="Vendas"
        description="Registro de vendas e execução completa (SKU → lote → cliente → pagamento) via `services.sales_service.record_sale`."
        actions={
          <Button asChild variant="luxury">
            <Link href="/sales/new" prefetch>
              <Plus className="h-4 w-4" />
              Nova venda
            </Link>
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>Últimas vendas</CardTitle>
          <CardDescription>Leitura server-side da tabela `sales`.</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Venda</TableHead>
                <TableHead>SKU</TableHead>
                <TableHead>Qtd.</TableHead>
                <TableHead>Total</TableHead>
                <TableHead>Lucro</TableHead>
                <TableHead>Data</TableHead>
                <TableHead>Pagamento</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sales.map((sale) => (
                <TableRow key={sale.id}>
                  <TableCell className="font-mono text-[#d4b36c]">{sale.saleCode || sale.id}</TableCell>
                  <TableCell><Badge variant="secondary">{sale.sku || "SEM-SKU"}</Badge></TableCell>
                  <TableCell>{formatNumber(sale.quantity)}</TableCell>
                  <TableCell>{formatCurrency(sale.total)}</TableCell>
                  <TableCell>{formatCurrency(sale.profit)}</TableCell>
                  <TableCell>{formatDate(sale.soldAt)}</TableCell>
                  <TableCell>{sale.paymentMethod || "Não informado"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
