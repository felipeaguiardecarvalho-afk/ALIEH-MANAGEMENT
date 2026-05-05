import Link from "next/link";
import { Filter } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { fetchPrototypeDashboardFilters } from "@/lib/dashboard-api";
import { mergeDashboardQuery, type DashboardQuery } from "@/lib/dashboard-url";
import { cn } from "@/lib/utils";

function presetLink(query: DashboardQuery, preset: "7" | "30" | "90" | "custom", label: string) {
  const href =
    "/dashboard" +
    mergeDashboardQuery(query, {
      period_preset: preset,
      date_from: null,
      date_to: null,
    });
  const active =
    (preset === "custom" && query.period_preset === "custom") ||
    (preset !== "custom" && query.period_preset === preset);
  return (
    <Button key={preset} type="button" variant={active ? "default" : "outline"} size="sm" className="h-8" asChild>
      <Link href={href}>{label}</Link>
    </Button>
  );
}

export async function DashboardFilters({ query }: { query: DashboardQuery }) {
  let options: Awaited<ReturnType<typeof fetchPrototypeDashboardFilters>>;
  try {
    options = await fetchPrototypeDashboardFilters();
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Não foi possível carregar listas para filtro (API).";
    return (
      <Card className="border-destructive/50">
        <CardHeader>
          <CardTitle className="text-destructive">Filtros indisponíveis</CardTitle>
          <CardDescription className="whitespace-pre-wrap">{msg}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const isCustom = query.period_preset === "custom";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Filter className="h-4 w-4" />
          Filtros do painel
        </CardTitle>
        <CardDescription>Período, cliente, SKU e produto do painel.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-muted-foreground">Período</span>
          {presetLink(query, "7", "7 dias")}
          {presetLink(query, "30", "30 dias")}
          {presetLink(query, "90", "90 dias")}
          {presetLink(query, "custom", "Personalizado")}
        </div>

        <form method="get" action="/dashboard" className="grid gap-4 md:grid-cols-2 lg:grid-cols-6">
          <input type="hidden" name="period_preset" value={query.period_preset} />

          <div className={cn("space-y-2", !isCustom && "opacity-60")}>
            <Label htmlFor="date_from">Data inicial</Label>
            <Input
              id="date_from"
              name="date_from"
              type="date"
              defaultValue={query.date_from}
              disabled={!isCustom}
              required={isCustom}
            />
          </div>
          <div className={cn("space-y-2", !isCustom && "opacity-60")}>
            <Label htmlFor="date_to">Data final</Label>
            <Input
              id="date_to"
              name="date_to"
              type="date"
              defaultValue={query.date_to}
              disabled={!isCustom}
              required={isCustom}
            />
          </div>

          <div className="grid gap-4 md:col-span-2 md:grid-cols-2 lg:col-span-4">
            <div className="space-y-2">
              <Label htmlFor="active_customer_days">Clientes activos (dias)</Label>
              <Input
                id="active_customer_days"
                name="active_customer_days"
                type="number"
                min={7}
                max={365}
                defaultValue={query.active_customer_days || "90"}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="aging_min_days">Stock parado (dias mín.)</Label>
              <Input
                id="aging_min_days"
                name="aging_min_days"
                type="number"
                min={15}
                max={180}
                defaultValue={query.aging_min_days || "45"}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="sku">SKU</Label>
              <Select id="sku" name="sku" defaultValue={query.sku}>
                <option value="">Todos</option>
                {options.skus.map((s) => (
                  <option key={s} value={s}>
                    {s.length > 42 ? `${s.slice(0, 39)}…` : s}
                  </option>
                ))}
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="product_id">Produto (lote)</Label>
              <Select id="product_id" name="product_id" defaultValue={query.product_id}>
                <option value="">Todos</option>
                {options.products.map((p) => (
                  <option key={p.id} value={p.id}>
                    #{p.id} · {p.name.length > 36 ? `${p.name.slice(0, 33)}…` : p.name}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <div className="space-y-2 lg:col-span-2">
            <Label htmlFor="customer_id">Cliente</Label>
            <Select id="customer_id" name="customer_id" defaultValue={query.customer_id}>
              <option value="">Todos</option>
              {options.customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.customer_code} · {c.name.length > 28 ? `${c.name.slice(0, 25)}…` : c.name}
                </option>
              ))}
            </Select>
          </div>

          <div className="flex flex-wrap items-end gap-2 lg:col-span-6">
            <Button type="submit">Aplicar</Button>
            <Button type="button" variant="outline" asChild>
              <Link href="/dashboard">Repor padrão</Link>
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
