import "server-only";

import { db, hasDatabaseUrl } from "@/lib/db";

export async function countUsers(): Promise<number> {
  if (!hasDatabaseUrl) return 0;
  try {
    const sql = db();
    const [row] = await sql`SELECT COUNT(*)::int AS c FROM users;`;
    return Number((row as { c?: number })?.c ?? 0);
  } catch {
    return 0;
  }
}

export async function listTenantIdsWithUsers(): Promise<string[]> {
  if (!hasDatabaseUrl) return [];
  try {
    const sql = db();
    const rows = await sql`
      SELECT DISTINCT tenant_id FROM users
      WHERE tenant_id IS NOT NULL AND TRIM(tenant_id) != ''
      ORDER BY LOWER(tenant_id);
    `;
    return Array.from(rows as Iterable<{ tenant_id: unknown }>)
      .map((r) => String(r.tenant_id ?? "").trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}

export type UserRow = {
  id: string | number;
  username: string;
  password_hash: string;
  role: string | null;
  tenant_id: string;
};

export async function fetchUserByUsername(
  tenantId: string,
  username: string
): Promise<UserRow | null> {
  if (!hasDatabaseUrl) return null;
  const u = (username || "").trim();
  if (!u) return null;
  const tid = (tenantId || "").trim() || "default";
  try {
    const sql = db();
    const [row] = await sql`
      SELECT id, username, password_hash, role, tenant_id
      FROM users
      WHERE tenant_id = ${tid} AND LOWER(username) = LOWER(${u})
      LIMIT 1;
    `;
    if (!row) return null;
    const r = row as Record<string, unknown>;
    return {
      id: r.id as string | number,
      username: String(r.username ?? ""),
      password_hash: String(r.password_hash ?? ""),
      role: r.role != null ? String(r.role) : null,
      tenant_id: String(r.tenant_id ?? "default"),
    };
  } catch {
    return null;
  }
}
