"use client";

import { usePathname } from "next/navigation";

import { TopNav } from "@/components/top-nav";

export function RootChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/login") {
    return <div className="min-h-screen">{children}</div>;
  }
  return (
    <>
      <TopNav />
      <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">{children}</main>
    </>
  );
}
