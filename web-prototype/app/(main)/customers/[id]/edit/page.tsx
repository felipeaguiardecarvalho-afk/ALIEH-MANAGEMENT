import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchPrototypeCustomer } from "@/lib/customers-api";
import { resolveRole } from "@/lib/tenant";
import { EditCustomerForm } from "./edit-customer-form";

export const revalidate = 30;

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "—";
}

export default async function EditCustomerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: idRaw } = await params;
  const id = Number(idRaw);
  if (!Number.isFinite(id) || id < 1) notFound();

  let customer: Awaited<ReturnType<typeof fetchPrototypeCustomer>>;
  let loadError: string | null = null;
  try {
    customer = await fetchPrototypeCustomer(id);
  } catch (e) {
    loadError = e instanceof Error ? e.message : "Falha ao carregar cliente.";
    customer = null;
  }

  if (loadError) {
    return (
      <div className="space-y-8 pb-16">
        <header className="space-y-3">
          <Link
            href="/customers"
            className="inline-flex items-center gap-1.5 text-xs uppercase tracking-[0.18em] text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-3 w-3" /> Clientes
          </Link>
          <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">CRM · Editar cliente</p>
          <h1 className="font-serif text-4xl font-semibold tracking-tight md:text-5xl">Erro ao carregar</h1>
        </header>
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-destructive">Erro</CardTitle>
            <CardDescription>{loadError}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" asChild>
              <Link href="/customers">Voltar à lista</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!customer) notFound();

  const role = await resolveRole();
  const isAdmin = role === "admin";

  return (
    <div className="space-y-10 pb-20">
      <header className="space-y-5">
        <Link
          href="/customers"
          className="inline-flex items-center gap-1.5 text-xs uppercase tracking-[0.18em] text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-3 w-3" /> Clientes
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border/40 pb-6">
          <div className="flex items-start gap-5">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-[#c7a35b]/40 bg-[#c7a35b]/[0.08] font-mono text-base font-semibold text-[#d4b36c]">
              {initials(customer.name)}
            </div>
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">
                CRM · {customer.customer_code}
              </p>
              <h1 className="mt-1.5 truncate font-serif text-4xl font-semibold tracking-tight md:text-5xl">
                {customer.name}
              </h1>
              <p className="mt-2 text-xs text-muted-foreground">
                Edite identificação e endereço (ViaCEP). Alterações são propagadas via{" "}
                <code className="rounded bg-muted px-1 text-[10px]">PUT /customers/{id}</code>.
              </p>
            </div>
          </div>
        </div>
      </header>

      <EditCustomerForm customer={customer} isAdmin={isAdmin} />
    </div>
  );
}
