import Link from "next/link";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchPrototypeCustomersList } from "@/lib/customers-api";
import type { CustomerApiRow } from "@/lib/customers-api";
import { resolveRole } from "@/lib/tenant";
import { CustomersSearchList } from "./customers-search-list";

export const revalidate = 30;

export default async function CustomersPage() {
  const role = await resolveRole();
  const isAdmin = role === "admin";

  let error: string | null = null;
  let customers: CustomerApiRow[] = [];

  try {
    customers = await fetchPrototypeCustomersList();
  } catch (e) {
    error = e instanceof Error ? e.message : "Não foi possível carregar clientes.";
  }

  return (
    <div className="space-y-8 pb-16">
      {/* Editorial header */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">CRM</p>
          <h1 className="mt-2 font-serif text-5xl font-semibold tracking-tight md:text-6xl">Clientes</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
            Busca instantânea por nome, CPF, telefone, email ou código. Edição com ViaCEP, exclusão protegida por
            confirmação (admin) — paridade total com o serviço Python.
          </p>
        </div>
        <Button asChild variant="luxury" className="gap-1.5">
          <Link href="/customers/new" prefetch>
            <Plus className="h-4 w-4" />
            Cadastrar cliente
          </Link>
        </Button>
      </header>

      {error ? (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-destructive">Erro ao carregar</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Verifique <code className="rounded bg-muted px-1">API_PROTOTYPE_URL</code> e a sessão (tenant / perfil).
          </CardContent>
        </Card>
      ) : null}

      {!error && customers.length === 0 ? (
        <EmptyCustomers />
      ) : null}

      {!error && customers.length > 0 ? (
        <CustomersSearchList customers={customers} isAdmin={isAdmin} />
      ) : null}
    </div>
  );
}

function EmptyCustomers() {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/[0.04] px-6 py-20 text-center">
      <p className="font-serif text-2xl tracking-tight text-foreground">Sem clientes ainda</p>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        Cadastre o primeiro cliente para começar a popular o CRM. ViaCEP preenche endereço automaticamente.
      </p>
      <Button asChild variant="luxury" className="mt-5 gap-1.5">
        <Link href="/customers/new" prefetch>
          <Plus className="h-4 w-4" />
          Cadastrar primeiro cliente
        </Link>
      </Button>
    </div>
  );
}
