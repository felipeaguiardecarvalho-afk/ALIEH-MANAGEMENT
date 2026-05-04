import "server-only";
import { cookies } from "next/headers";
import { getTenantId as getDefaultTenantId } from "@/lib/db";

const TENANT_COOKIE = "alieh_tenant";

export async function resolveTenantId() {
  const cookieStore = await cookies();
  const fromCookie = cookieStore.get(TENANT_COOKIE)?.value?.trim();
  return fromCookie || getDefaultTenantId();
}

export type Role = "admin" | "operator" | "viewer";

/**
 * Em `next dev`, sem cookie `alieh_role`, o perfil vem de `ALIEH_DEV_ROLE` ou assume `admin`
 * para o protótipo local funcionar sem fluxo de login (produção continua `viewer` por omissão).
 */
export async function resolveRole(): Promise<Role> {
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
