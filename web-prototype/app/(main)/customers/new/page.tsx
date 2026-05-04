import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { NewCustomerForm } from "./new-customer-form";

export default function NewCustomerPage() {
  return (
    <div className="space-y-10 pb-20">
      <header className="space-y-5">
        <Link
          href="/customers"
          className="inline-flex items-center gap-1.5 text-xs uppercase tracking-[0.18em] text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-3 w-3" /> Clientes
        </Link>
        <div className="border-b border-border/40 pb-6">
          <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">CRM · Novo cliente</p>
          <h1 className="mt-2 font-serif text-5xl font-semibold tracking-tight md:text-6xl">
            Cadastrar cliente
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
            Identificação e endereço com ViaCEP. Código sequencial é alocado pelo servidor — sem intervenção manual.
            Campos com <span className="text-foreground">*</span> são obrigatórios.
          </p>
        </div>
      </header>

      <NewCustomerForm />
    </div>
  );
}
