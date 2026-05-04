import Link from "next/link";
import { Plus } from "lucide-react";
import { PageHero } from "@/components/page-hero";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate } from "@/lib/format";
import { getCustomers } from "@/lib/queries";

export const revalidate = 120;

export default async function CustomersPage() {
  const customers = await getCustomers();

  return (
    <div className="space-y-6">
      <PageHero
        eyebrow="CRM"
        title="Clientes"
        description="Cadastro, edição e listagem — tenant-scoped. Equivalente à página Clientes do Streamlit."
        actions={
          <Button asChild variant="luxury">
            <Link href="/customers/new" prefetch>
              <Plus className="h-4 w-4" />
              Cadastrar cliente
            </Link>
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>Base de clientes</CardTitle>
          <CardDescription>{customers.length} clientes no tenant ativo.</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Código</TableHead>
                <TableHead>Nome</TableHead>
                <TableHead>Contato</TableHead>
                <TableHead>Localização</TableHead>
                <TableHead>Cadastro</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {customers.map((customer) => (
                <TableRow key={customer.id}>
                  <TableCell className="font-mono text-[#d4b36c]">{customer.customerCode}</TableCell>
                  <TableCell className="font-medium">{customer.name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {customer.email || customer.phone || customer.instagram || "Sem contato"}
                  </TableCell>
                  <TableCell>
                    {[customer.city, customer.state].filter(Boolean).join(" / ") || "Não informado"}
                  </TableCell>
                  <TableCell>{formatDate(customer.createdAt)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
