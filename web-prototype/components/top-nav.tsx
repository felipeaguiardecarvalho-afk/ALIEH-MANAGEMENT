"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Gem, LogOut, Menu } from "lucide-react";
import { cn } from "@/lib/utils";
import { logout } from "@/lib/actions/auth";
import { useClientDataStore } from "@/lib/client-data/store";
import { Button } from "@/components/ui/button";

const navItems = [
  { href: "/dashboard", label: "Painel" },
  { href: "/products", label: "Produtos" },
  { href: "/costs", label: "Custos" },
  { href: "/pricing", label: "Precificação" },
  { href: "/inventory", label: "Estoque" },
  { href: "/customers", label: "Clientes" },
  { href: "/sales", label: "Vendas" },
];

/** When user aims at Vendas, warm JS routes + client store (SKUs + lotes em prefetch). */
function prefetchSalesCluster(router: ReturnType<typeof useRouter>) {
  router.prefetch("/sales");
  router.prefetch("/sales/new");
  router.prefetch("/customers");
  router.prefetch("/inventory");
  const st = useClientDataStore.getState();
  void st.ensureGlobalBundle().then(() => {
    const skus = useClientDataStore.getState().saleableSkus.data;
    if (skus?.length) st.prefetchSaleBatchCluster(skus.map((x) => x.sku), 28);
  });
}

export function TopNav() {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-black/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/dashboard" prefetch className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-full border border-[#c7a35b]/50 bg-[#c7a35b]/12">
            <Gem className="h-4 w-4 text-[#d4b36c]" />
          </span>
          <span>
            <span className="block font-serif text-xl leading-none tracking-wide">ALIEH</span>
            <span className="block text-[10px] uppercase tracking-[0.32em] text-muted-foreground">
              Management
            </span>
          </span>
        </Link>

        <nav className="hidden items-center gap-0.5 lg:flex">
          {navItems.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                prefetch
                onMouseEnter={() => {
                  router.prefetch(item.href);
                  if (item.href === "/sales") prefetchSalesCluster(router);
                }}
                onFocus={() => {
                  router.prefetch(item.href);
                  if (item.href === "/sales") prefetchSalesCluster(router);
                }}
                className={cn(
                  "rounded-full px-3.5 py-2 text-sm text-muted-foreground transition-colors hover:bg-white/10 hover:text-foreground",
                  active && "bg-white text-black hover:bg-white hover:text-black"
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-2">
          <form action={logout}>
            <Button
              type="submit"
              variant="ghost"
              size="sm"
              className="hidden rounded-full text-muted-foreground hover:bg-white/10 hover:text-foreground lg:inline-flex"
              title="Terminar sessão"
            >
              <LogOut className="h-4 w-4" />
              <span className="sr-only">Sair</span>
            </Button>
          </form>

          <details className="relative lg:hidden">
            <summary className="flex h-10 w-10 list-none items-center justify-center rounded-full border border-white/10">
              <Menu className="h-4 w-4" />
            </summary>
            <div className="absolute right-0 mt-3 grid w-56 gap-1 rounded-2xl border border-white/10 bg-black p-2 shadow-xl">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  prefetch
                  onMouseEnter={() => {
                    router.prefetch(item.href);
                    if (item.href === "/sales") prefetchSalesCluster(router);
                  }}
                  onFocus={() => {
                    router.prefetch(item.href);
                    if (item.href === "/sales") prefetchSalesCluster(router);
                  }}
                  className="rounded-xl px-3 py-2 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground"
                >
                  {item.label}
                </Link>
              ))}
              <form action={logout} className="border-t border-white/10 pt-1">
                <button
                  type="submit"
                  className="w-full rounded-xl px-3 py-2 text-left text-sm text-muted-foreground hover:bg-white/10 hover:text-foreground"
                >
                  Sair
                </button>
              </form>
            </div>
          </details>
        </div>
      </div>
    </header>
  );
}
