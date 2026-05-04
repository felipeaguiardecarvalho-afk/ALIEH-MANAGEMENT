import "server-only";
import { cookies } from "next/headers";

import { getSession } from "@/lib/auth/session";
import { defaultTenantIdFromEnv } from "@/lib/tenant-env";
import { isPrototypeOpenEffective } from "@/lib/env/alieh-runtime";
import type { Role } from "@/lib/role";

export type { Role } from "@/lib/role";

const TENANT_COOKIE = "alieh_tenant";

export async function resolveTenantId() {
  if (isPrototypeOpenEffective()) {
    return defaultTenantIdFromEnv();
  }
  const session = await getSession();
  if (session?.tenantId?.trim()) {
    return session.tenantId.trim();
  }
  const cookieStore = await cookies();
  const fromCookie = cookieStore.get(TENANT_COOKIE)?.value?.trim();
  if (fromCookie) return fromCookie;
  return defaultTenantIdFromEnv();
}

export async function resolveRole(): Promise<Role> {
  if (isPrototypeOpenEffective()) {
    const r = (process.env.ALIEH_PROTOTYPE_DEFAULT_ROLE || "").trim().toLowerCase();
    if (r === "admin" || r === "operator" || r === "viewer") return r;
    return "viewer";
  }
  const session = await getSession();
  if (session) {
    return session.role;
  }
  const cookieStore = await cookies();
  const raw = cookieStore.get("alieh_role")?.value;
  if (raw === "admin" || raw === "operator" || raw === "viewer") {
    return raw;
  }
  return "viewer";
}

export function canMutate(role: Role) {
  return role === "admin" || role === "operator";
}
