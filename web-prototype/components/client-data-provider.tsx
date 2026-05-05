"use client";

/**
 * Phase 1–2: global Zustand store + route-aware prefetch (await bundle before batch prefetch).
 */
import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useClientDataStore } from "@/lib/client-data/store";

export function ClientDataProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const ensureGlobalBundle = useClientDataStore((s) => s.ensureGlobalBundle);
  const prefetchSaleBatchCluster = useClientDataStore((s) => s.prefetchSaleBatchCluster);

  useEffect(() => {
    if (!pathname.startsWith("/sales")) return;
    void (async () => {
      await ensureGlobalBundle();
      const skus = useClientDataStore.getState().saleableSkus.data;
      if (pathname.startsWith("/sales") && skus?.length) {
        prefetchSaleBatchCluster(
          skus.map((x) => x.sku),
          28
        );
      }
    })();
  }, [pathname, ensureGlobalBundle, prefetchSaleBatchCluster]);

  return <>{children}</>;
}
