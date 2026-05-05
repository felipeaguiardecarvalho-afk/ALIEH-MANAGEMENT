"use client";

/**
 * Phase 1–2: global Zustand store + route-aware prefetch (await bundle before batch prefetch).
 */
import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useClientDataStore } from "@/lib/client-data/store";

export function ClientDataProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const prefetchSaleBatchCluster = useClientDataStore((s) => s.prefetchSaleBatchCluster);

  useEffect(() => {
    if (!pathname.startsWith("/sales")) return;
    const skus = useClientDataStore.getState().saleableSkus.data;
    if (skus?.length) {
      prefetchSaleBatchCluster(
        skus.map((x) => x.sku),
        20
      );
    }
  }, [pathname, prefetchSaleBatchCluster]);

  return <>{children}</>;
}
