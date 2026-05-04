import "server-only";

import { cookies } from "next/headers";

import { PROTOTYPE_OPEN_ENV } from "@/lib/auth/constants";
import { canMutate, resolveRole, resolveTenantId } from "@/lib/tenant";

export type GateFail = { ok: false; message: string };

/** Alinhado a `web-prototype/.env.example` e `api-prototype/requirements.txt` (uvicorn :8000). */
const DEV_DEFAULT_API_BASE = "http://127.0.0.1:8000";
const DEV_DEFAULT_USER_ID = "1";

function useDevPrototypeDefaults(): boolean {
  return process.env.NODE_ENV === "development";
}

export function getPrototypeApiBase(): string {
  const raw = (process.env.API_PROTOTYPE_URL?.trim() || (useDevPrototypeDefaults() ? DEV_DEFAULT_API_BASE : ""))
    .trim();
  if (!raw) {
    throw new Error("Defina API_PROTOTYPE_URL (URL base da api-prototype).");
  }
  return raw.replace(/\/$/, "");
}

export function hasPrototypeApiUrl(): boolean {
  if (process.env.API_PROTOTYPE_URL?.trim()) return true;
  return useDevPrototypeDefaults();
}

export async function gateMutation(): Promise<GateFail | null> {
  const role = await resolveRole();
  if (!canMutate(role)) {
    return { ok: false, message: "Sem permissão para alterar dados." };
  }
  return null;
}

async function resolveActorIds(): Promise<{ userId: string; username?: string }> {
  const cookieStore = await cookies();
  const fromCookie = cookieStore.get("alieh_user_id")?.value?.trim();
  const fromEnv = process.env.API_PROTOTYPE_USER_ID?.trim();
  const devFallback = useDevPrototypeDefaults() ? DEV_DEFAULT_USER_ID : "";
  const userId = fromCookie || fromEnv || devFallback;
  const username =
    cookieStore.get("alieh_username")?.value?.trim() ||
    process.env.API_PROTOTYPE_USERNAME?.trim() ||
    (useDevPrototypeDefaults() ? "dev-local" : undefined);
  const open = process.env[PROTOTYPE_OPEN_ENV] === "1";
  if (!userId) {
    if (open) {
      throw new Error("Em modo aberto defina API_PROTOTYPE_USER_ID (ou cookie alieh_user_id).");
    }
    throw new Error("Defina API_PROTOTYPE_USER_ID ou cookie alieh_user_id para usar a api-prototype.");
  }
  return { userId, username };
}

export async function prototypeAuthHeaders(): Promise<Headers> {
  const tenantId = (await resolveTenantId()).trim();
  if (!tenantId) {
    throw new Error("Inquilino (tenant) não resolvido: configure ALIEH_TENANT_ID / cookie alieh_tenant.");
  }

  const role = await resolveRole();
  if (role !== "admin" && role !== "operator") {
    throw new Error("Perfil sem permissão para a API de negócio (admin ou operador).");
  }

  const { userId, username } = await resolveActorIds();
  const h = new Headers();
  h.set("X-User-Id", userId);
  h.set("X-Tenant-Id", tenantId);
  h.set("X-Role", role);
  if (username) h.set("X-Username", username);
  return h;
}

export async function prototypeAuthHeadersRead(): Promise<Headers> {
  const tenantId = (await resolveTenantId()).trim();
  if (!tenantId) {
    throw new Error("Inquilino (tenant) não resolvido.");
  }

  const role = await resolveRole();
  if (role !== "admin" && role !== "operator" && role !== "viewer") {
    throw new Error("Perfil sem permissão para esta leitura na API.");
  }

  const { userId, username } = await resolveActorIds();
  const h = new Headers();
  h.set("X-User-Id", userId);
  h.set("X-Tenant-Id", tenantId);
  h.set("X-Role", role);
  if (username) h.set("X-Username", username);
  return h;
}

export async function apiPrototypeFetchRead(
  path: string,
  init: RequestInit & { json?: unknown } = {}
): Promise<Response> {
  const { json, headers: extra, ...rest } = init;
  const url = `${getPrototypeApiBase()}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = await prototypeAuthHeadersRead();
  if (extra) {
    new Headers(extra as HeadersInit).forEach((v, k) => headers.set(k, v));
  }
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(url, {
    ...rest,
    headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
}

export async function apiPrototypeFetch(
  path: string,
  init: RequestInit & { json?: unknown } = {}
): Promise<Response> {
  const { json, headers: extra, ...rest } = init;
  const url = `${getPrototypeApiBase()}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = await prototypeAuthHeaders();
  if (extra) {
    new Headers(extra as HeadersInit).forEach((v, k) => headers.set(k, v));
  }
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(url, {
    ...rest,
    headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
}

export async function readApiError(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const j = JSON.parse(text) as { detail?: unknown };
    if (typeof j.detail === "string") return j.detail;
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
