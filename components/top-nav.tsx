"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Gem, LogOut, Menu } from "lucide-react";
import { cn } from "@/lib/utils";
import { logout } from "@/lib/actions/auth";

const navItems = [
  { href: "/dashboard", label: "Painel" },
  { href: "/products", label: "Produtos" },
  { href: "/costs", label: "Custos" },
  { href: "/pricing", label: "Precificação" },
  { href: "/inventory", label: "Estoque" },
  { href: "/customers", label: "Clientes" },
  { href: "/sales", label: "Vendas" },
  { href: "/uat", label: "UAT" },
];

export function TopNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-black/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/dashboard" prefetch className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-full border border-[#c7a35b]/40 bg-[#c7a35b]/10">
            <Gem className="h-4 w-4 text-[#d4b36c]" />
          </span>
          <span>
            <span className="block font-serif text-xl leading-none tracking-wide">ALIEH</span>
            <span className="block text-[10px] uppercase tracking-[0.32em] text-muted-foreground">
              Management
            </span>
          </span>
        </Link>

        <nav className="hidden items-center gap-1 lg:flex">
          {navItems.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                prefetch
                className={cn(
                  "rounded-full px-3.5 py-2 text-sm text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground",
                  active && "bg-white text-black hover:bg-white hover:text-black"
                )}
              >
                {item.label}
              </Link>
            );
          })}
          <form action={logout} className="ml-2 border-l border-white/10 pl-3">
            <button
              type="submit"
              className="inline-flex items-center gap-1.5 rounded-full px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground"
              title="Terminar sessão"
            >
              <LogOut className="h-3.5 w-3.5" />
              Sair
            </button>
          </form>
        </nav>

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
                className="rounded-xl px-3 py-2 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground"
              >
                {item.label}
              </Link>
            ))}
            <form action={logout} className="border-t border-white/10 pt-2">
              <button
                type="submit"
                className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sair
              </button>
            </form>
          </div>
        </details>
      </div>
    </header>
  );
}
