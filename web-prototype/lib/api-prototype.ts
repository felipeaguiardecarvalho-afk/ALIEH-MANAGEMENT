import "server-only";

import { getSession } from "@/lib/auth/session";
import { isPrototypeOpenEffective } from "@/lib/env/alieh-runtime";
import { canMutate, resolveRole, resolveTenantId } from "@/lib/tenant";

function attachInternalPrototypeSecret(headers: Headers): void {
  const secret = process.env.API_PROTOTYPE_INTERNAL_SECRET?.trim();
  if (secret) headers.set("X-Alieh-Internal", secret);
}

export type GateFail = { ok: false; message: string };
type PrototypeFetchInit = RequestInit & {
  json?: unknown;
  next?: { revalidate?: number; tags?: string[] };
};

/** Evita API_PROTOTYPE_URL=http://127.0.0.1:3000 (mesmo host/porta do Next) → 404 "Not Found" em /sales/... */
function assertPrototypeApiNotSamePortAsNext(base: string): void {
  let parsed: URL;
  try {
    parsed = new URL(base);
  } catch {
    throw new Error("API_PROTOTYPE_URL não é um URL válido.");
  }
  const host = parsed.hostname.toLowerCase();
  if (host !== "localhost" && host !== "127.0.0.1" && host !== "::1" && host !== "[::1]") {
    return;
  }
  const apiPort = parsed.port || (parsed.protocol === "https:" ? "443" : "80");
  const nextPort = (process.env.PORT || "3000").trim();
  if (apiPort === nextPort) {
    throw new Error(
      `API_PROTOTYPE_URL não pode usar a porta ${apiPort} (a mesma do Next.js). ` +
        "Defina a URL base da **api-prototype** FastAPI, por exemplo http://127.0.0.1:8000, e mantenha-a a correr."
    );
  }
}

export function getPrototypeApiBase(): string {
  const raw = process.env.API_PROTOTYPE_URL?.trim();
  if (!raw) {
    throw new Error("Defina API_PROTOTYPE_URL (URL base da api-prototype).");
  }
  const base = raw.replace(/\/$/, "");
  assertPrototypeApiNotSamePortAsNext(base);
  return base;
}

function isLikelyConnectionFailure(e: unknown): boolean {
  if (!(e instanceof Error)) return false;
  const msg = (e.message || "").toLowerCase();
  if (msg.includes("fetch failed") || msg.includes("network error")) return true;
  const c = e.cause;
  if (c instanceof Error) {
    const cm = (c.message || "").toLowerCase();
    if (cm.includes("econnrefused") || cm.includes("enotfound") || cm.includes("eai_again")) return true;
    const causeCode = (c as unknown as { code?: unknown }).code;
    const code = typeof causeCode === "string" ? causeCode : "";
    if (code === "ECONNREFUSED" || code === "ENOTFOUND" || code === "ETIMEDOUT") return true;
  }
  return false;
}

async function prototypeUndiciFetch(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (e) {
    if (isLikelyConnectionFailure(e)) {
      let origin: string;
      try {
        origin = new URL(url).origin;
      } catch {
        origin = "a API configurada em API_PROTOTYPE_URL";
      }
      throw new Error(
        `Sem ligação à api-prototype (${origin}). ` +
          "Na raiz do repositório: npm run dev:api (só FastAPI) ou npm run dev:stack (API + Next). " +
          "Confirme API_PROTOTYPE_URL em web-prototype/.env.local (ex.: http://127.0.0.1:8000).",
      );
    }
    throw e;
  }
}

/** Mutações via `apiPrototypeFetch` não exigem `DATABASE_URL` no Next — só a API. */
export function hasPrototypeApiUrl(): boolean {
  return Boolean(process.env.API_PROTOTYPE_URL?.trim());
}

export async function gateMutation(): Promise<GateFail | null> {
  const role = await resolveRole();
  if (!canMutate(role)) {
    return { ok: false, message: "Sem permissão para alterar dados." };
  }
  return null;
}

/** Headers para api-prototype: tenant e utilizador vêm da sessão (JWT httpOnly), sem literais. */
export async function prototypeAuthHeaders(): Promise<Headers> {
  const tenantId = (await resolveTenantId()).trim();
  if (!tenantId) {
    throw new Error("Inquilino (tenant) não resolvido: configure ALIEH_TENANT_ID / sessão.");
  }

  const role = await resolveRole();
  if (role !== "admin" && role !== "operator") {
    throw new Error("Perfil sem permissão para a API de negócio.");
  }

  const open = isPrototypeOpenEffective();
  const session = await getSession();
  const userId = session?.userId?.trim();
  const username = session?.username?.trim();
  if (!userId) {
    if (!open) {
      throw new Error("Sessão sem utilizador (user id); inicie sessão novamente.");
    }
    const fallback = process.env.API_PROTOTYPE_USER_ID?.trim();
    if (!fallback) {
      throw new Error("Em modo aberto, defina API_PROTOTYPE_USER_ID ou inicie sessão.");
    }
    const h = new Headers();
    h.set("X-User-Id", fallback);
    h.set("X-Tenant-Id", tenantId);
    h.set("X-Role", role);
    const openUser = process.env.API_PROTOTYPE_USERNAME?.trim();
    if (openUser) h.set("X-Username", openUser);
    return h;
  }

  const h = new Headers();
  h.set("X-User-Id", userId);
  h.set("X-Tenant-Id", tenantId);
  h.set("X-Role", role);
  if (username) h.set("X-Username", username);
  return h;
}

/** Leituras que aceitam viewer (ex.: lista de vendas recentes). */
export async function prototypeAuthHeadersRead(): Promise<Headers> {
  const tenantId = (await resolveTenantId()).trim();
  if (!tenantId) {
    throw new Error("Inquilino (tenant) não resolvido: configure ALIEH_TENANT_ID / sessão.");
  }

  const role = await resolveRole();
  if (role !== "admin" && role !== "operator" && role !== "viewer") {
    throw new Error("Perfil sem permissão para esta leitura na API.");
  }

  const open = isPrototypeOpenEffective();
  const session = await getSession();
  const userId = session?.userId?.trim();
  const username = session?.username?.trim();
  if (!userId) {
    if (!open) {
      throw new Error("Sessão sem utilizador (user id); inicie sessão novamente.");
    }
    const fallback = process.env.API_PROTOTYPE_USER_ID?.trim();
    if (!fallback) {
      throw new Error("Em modo aberto, defina API_PROTOTYPE_USER_ID ou inicie sessão.");
    }
    const h = new Headers();
    h.set("X-User-Id", fallback);
    h.set("X-Tenant-Id", tenantId);
    h.set("X-Role", role);
    const openUser = process.env.API_PROTOTYPE_USERNAME?.trim();
    if (openUser) h.set("X-Username", openUser);
    return h;
  }

  const h = new Headers();
  h.set("X-User-Id", userId);
  h.set("X-Tenant-Id", tenantId);
  h.set("X-Role", role);
  if (username) h.set("X-Username", username);
  return h;
}

export async function apiPrototypeFetchRead(
  path: string,
  init: PrototypeFetchInit = {}
): Promise<Response> {
  const { json, headers: extra, next, ...rest } = init;
  const url = `${getPrototypeApiBase()}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = await prototypeAuthHeadersRead();
  if (extra) {
    new Headers(extra as HeadersInit).forEach((v, k) => headers.set(k, v));
  }
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  attachInternalPrototypeSecret(headers);
  const method = String(rest.method || (json !== undefined ? "POST" : "GET")).toUpperCase();
  const isGet = method === "GET";
  // Node/undici reuses keep-alive connections to the same API host by default.
  return prototypeUndiciFetch(url, {
    ...rest,
    method,
    next: isGet
      ? { ...(next || {}), revalidate: next?.revalidate ?? 30 }
      : next,
    cache: isGet ? (rest.cache ?? "force-cache") : (rest.cache ?? "no-store"),
    signal: rest.signal ?? AbortSignal.timeout(isGet ? 8000 : 12000),
    headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
}

export async function apiPrototypeFetch(
  path: string,
  init: PrototypeFetchInit = {}
): Promise<Response> {
  const { json, headers: extra, next, ...rest } = init;
  const url = `${getPrototypeApiBase()}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = await prototypeAuthHeaders();
  if (extra) {
    new Headers(extra as HeadersInit).forEach((v, k) => headers.set(k, v));
  }
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  attachInternalPrototypeSecret(headers);
  const method = String(rest.method || (json !== undefined ? "POST" : "GET")).toUpperCase();
  // Node/undici reuses keep-alive connections to the same API host by default.
  return prototypeUndiciFetch(url, {
    ...rest,
    method,
    next,
    cache: rest.cache ?? "no-store",
    signal: rest.signal ?? AbortSignal.timeout(12000),
    headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
}

export async function readApiError(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const j = JSON.parse(text) as { detail?: unknown };
    if (typeof j.detail === "string") return j.detail;
    if (j.detail && typeof j.detail === "object" && !Array.isArray(j.detail)) {
      const d = j.detail as { message?: unknown; code?: unknown };
      if (typeof d.message === "string") return d.message;
    }
    if (Array.isArray(j.detail)) {
      return j.detail
        .map((x: { msg?: string }) => (typeof x?.msg === "string" ? x.msg : JSON.stringify(x)))
        .join("; ");
    }
  } catch {
    if (text) return text.slice(0, 500);
  }
  return res.statusText || "Erro na API.";
}
