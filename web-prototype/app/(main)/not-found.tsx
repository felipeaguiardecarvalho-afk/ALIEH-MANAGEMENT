import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <section className="mx-auto flex max-w-xl flex-col items-center py-24 text-center">
      <p className="text-xs uppercase tracking-[0.32em] text-[#d4b36c]">404</p>
      <h1 className="mt-6 font-serif text-5xl font-semibold tracking-tight">
        Esta rota não existe no catálogo.
      </h1>
      <p className="mt-4 text-sm text-muted-foreground">
        Verifique a URL ou volte ao painel executivo.
      </p>
      <Button asChild className="mt-8" variant="luxury">
        <Link href="/dashboard">Voltar ao dashboard</Link>
      </Button>
    </section>
  );
}
