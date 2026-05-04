import Link from "next/link";
import { Plus } from "lucide-react";
import { PageHero } from "@/components/page-hero";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatCurrency, formatDate, formatNumber } from "@/lib/format";
import { fetchPrototypeRecentSales, STREAMLIT_RECENT_SALES_LIMIT } from "@/lib/sales-api";

export const revalidate = 120;

export default async function SalesPage() {
  let error: string | null = null;
  let items: Awaited<ReturnType<typeof fetchPrototypeRecentSales>>["items"] = [];

  try {
    const res = await fetchPrototypeRecentSales(STREAMLIT_RECENT_SALES_LIMIT);
    items = res.items;
  } catch (e) {
    error = e instanceof Error ? e.message : "Não foi possível carregar vendas recentes.";
  }

  return (
    <div className="space-y-6">
      <PageHero
        eyebrow="Comercial"
        title="Vendas"
        description="Registro de vendas via API e as últimas 20 linhas com data, SKU, cliente, quantidade, total e pagamento."
        actions={
          <Button asChild variant="luxury">
            <Link href="/sales/new" prefetch>
              <Plus className="h-4 w-4" />
              Nova venda
            </Link>
          </Button>
        }
      />

      {error ? (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-destructive">Erro ao carregar vendas</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Verifique <code className="rounded bg-muted px-1">API_PROTOTYPE_URL</code> e a sessão (admin, operador ou
            leitor para esta lista).
          </CardContent>
        </Card>
      ) : null}

      {!error ? (
        <Card>
          <CardHeader>
            <CardTitle>Vendas recentes</CardTitle>
            <CardDescription>
              Últimas 20 vendas via <code className="rounded bg-muted px-1">GET /sales/recent?limit=20</code> — mesma
              origem que o serviço de vendas.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {items.length === 0 ? (
              <p className="py-10 text-center text-sm text-muted-foreground">Ainda não há vendas registadas.</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-border/60">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Data</TableHead>
                      <TableHead>SKU</TableHead>
                      <TableHead>Cliente</TableHead>
                      <TableHead className="text-right">Qtd.</TableHead>
                      <TableHead className="text-right">Total</TableHead>
                      <TableHead>Pagamento</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((sale, rowIndex) => (
                      <TableRow key={sale.id != null ? String(sale.id) : `sale-${rowIndex}`}>
                        <TableCell className="align-top text-sm">
                          <div className="font-medium text-foreground">{formatDate(sale.sold_at ?? null)}</div>
                          {sale.sale_code ? (
                            <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                              {String(sale.sale_code)}
                            </div>
                          ) : null}
                        </TableCell>
                        <TableCell className="align-top">
                          <Badge variant="secondary">
                            {String(sale.sku ?? "")
                              .trim() || "SEM-SKU"}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-[14rem] align-top text-sm text-foreground">
                          <span
                            className="line-clamp-2"
                            title={String(sale.customer_label ?? "").trim() || undefined}
                          >
                            {String(sale.customer_label ?? "").trim() || "—"}
                          </span>
                        </TableCell>
                        <TableCell className="align-top text-right tabular-nums">
                          {formatNumber(Number(sale.quantity ?? 0))}
                        </TableCell>
                        <TableCell className="align-top text-right font-medium tabular-nums">
                          {formatCurrency(Number(sale.total ?? 0))}
                        </TableCell>
                        <TableCell className="align-top text-sm">
                          {String(sale.payment_method ?? "").trim() || "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
