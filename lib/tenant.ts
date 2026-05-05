import "server-only";
import { cookies } from "next/headers";
import { getTenantId as getDefaultTenantId } from "@/lib/db";
import { getSession } from "@/lib/auth/session";

import type { Role } from "@/lib/role";

export type { Role } from "@/lib/role";

const TENANT_COOKIE = "alieh_tenant";

export async function resolveTenantId() {
  const session = await getSession();
  if (session?.tenantId?.trim()) {
    return session.tenantId.trim();
  }
  const cookieStore = await cookies();
  const fromCookie = cookieStore.get(TENANT_COOKIE)?.value?.trim();
  return fromCookie || getDefaultTenantId();
}

/**
 * Prioridade: JWT de sessão → cookie legacy `alieh_role` → `next dev` (ALIEH_DEV_ROLE ou admin)
 * → produção sem sessão (`viewer`).
 */
export async function resolveRole(): Promise<Role> {
  const session = await getSession();
  if (session?.role) {
    return session.role;
  }
  const cookieStore = await cookies();
  const raw = cookieStore.get("alieh_role")?.value;
  if (raw === "admin" || raw === "operator" || raw === "viewer") {
    return raw;
  }
  if (process.env.NODE_ENV === "development") {
    const dev = process.env.ALIEH_DEV_ROLE?.trim().toLowerCase();
    if (dev === "admin" || dev === "operator" || dev === "viewer") {
      return dev;
    }
    return "admin";
  }
  return "viewer";
}

export function canMutate(role: Role) {
  return role === "admin" || role === "operator";
}
