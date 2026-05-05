import "server-only";

import { apiPrototypeFetch } from "@/lib/api-prototype";

export type PrototypeAuditDomain = "sales" | "pricing" | "stock" | "login";

export async function logPrototypeAuditEvent(
  domain: PrototypeAuditDomain,
  action: string,
  detail: Record<string, unknown> = {}
): Promise<void> {
  try {
    const res = await apiPrototypeFetch("/audit/events", {
      method: "POST",
      json: { domain, action, detail },
    });
    void res;
  } catch {
    /* audit must not break mutations */
  }
}

type LoginIngestInput = {
  tenantId: string;
  username: string;
  userId?: string;
  success: boolean;
  action?: string;
  detail?: Record<string, unknown>;
};

export async function logPrototypeLoginIngest(input: LoginIngestInput): Promise<void> {
  try {
    const secret = process.env.PROTOTYPE_AUDIT_INGEST_SECRET?.trim();
    const raw = process.env.API_PROTOTYPE_URL?.trim();
    if (!secret || !raw) return;
    const base = raw.replace(/\/$/, "");

    const res = await fetch(`${base}/audit/login-ingest`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Prototype-Audit-Secret": secret,
      },
      body: JSON.stringify({
        tenant_id: input.tenantId,
        username: input.username,
        user_id: input.userId ?? "",
        success: input.success,
        action: input.action ?? (input.success ? "login_success" : "login_failure"),
        detail: { channel: "next-root", ...(input.detail ?? {}) },
      }),
    });
    void res;
  } catch {
    /* ignore */
  }
}
