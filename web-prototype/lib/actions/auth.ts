"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { sessionCookieOptions, signSessionToken, getSession } from "@/lib/auth/session";
import { SESSION_COOKIE_NAME } from "@/lib/auth/constants";
import { isPrototypeOpenEffective } from "@/lib/env/alieh-runtime";
import { logPrototypeAuditEvent, logPrototypeLoginIngest } from "@/lib/prototype-audit";
import { fetchUserByUsername, countUsers } from "@/lib/auth/users-db";
import {
  legacyCredentialsConfigured,
  legacyLoginOk,
  verifyPbkdf2Password,
} from "@/lib/auth/password";

export type LoginFormState = { ok: boolean; message: string };

const DEFAULT_ROLE = "operator";

function roleFromRow(role: string | null): string {
  const r = (role || "").trim().toLowerCase();
  return r || DEFAULT_ROLE;
}

async function establishSession(params: {
  userId: string;
  username: string;
  role: string;
  tenantId: string;
}): Promise<never> {
  await logPrototypeLoginIngest({
    tenantId: params.tenantId,
    username: params.username,
    userId: params.userId,
    success: true,
    action: "login_success",
    detail: { role: params.role },
  });
  const token = await signSessionToken({
    uid: params.userId,
    sub: params.username,
    role: params.role,
    tid: params.tenantId,
  });
  (await cookies()).set(SESSION_COOKIE_NAME, token, sessionCookieOptions());
  redirect("/dashboard");
}

export async function login(
  _prev: LoginFormState,
  formData: FormData
): Promise<LoginFormState> {
  if (isPrototypeOpenEffective()) {
    redirect("/dashboard");
  }

  const username = String(formData.get("username") || "").trim();
  const password = String(formData.get("password") || "");
  const tenantField = String(formData.get("tenant_id") || "").trim();

  if (!username || !password) {
    return { ok: false, message: "Utilizador e senha são obrigatórios." };
  }

  if (!process.env.AUTH_SESSION_SECRET?.trim()) {
    return { ok: false, message: "AUTH_SESSION_SECRET não configurado no servidor." };
  }

  const legacy = legacyCredentialsConfigured();

  /** Login legacy primeiro: evita esperar pela BD se `DATABASE_URL` estiver errada ou lenta. */
  if (legacy && legacyLoginOk(username, password)) {
    const row = await fetchUserByUsername("default", username);
    let userId = (process.env.ALIEH_AUTH_USER_ID || "").trim() || "legacy";
    let role = "admin";
    if (row) {
      userId = String(row.id);
      role = roleFromRow(row.role);
    }
    await establishSession({
      userId,
      username,
      role,
      tenantId: "default",
    });
  }

  const hasUsers = (await countUsers()) > 0;

  if (!hasUsers && !legacy) {
    return {
      ok: false,
      message:
        "Sem utilizadores na BD nem credencial legacy. Crie utilizadores ou defina ALIEH_AUTH_* / ALIEH_PROTOTYPE_OPEN=1.",
    };
  }

  const loginTenant = hasUsers ? (tenantField || "default") : "default";

  if (hasUsers) {
    const row = await fetchUserByUsername(loginTenant, username);
    if (row && verifyPbkdf2Password(password, row.password_hash)) {
      await establishSession({
        userId: String(row.id),
        username: row.username,
        role: roleFromRow(row.role),
        tenantId: String(row.tenant_id || "default"),
      });
    }
    await logPrototypeLoginIngest({
      tenantId: loginTenant,
      username,
      success: false,
      action: "login_failure",
      detail: { reason: "bad_credentials" },
    });
    return { ok: false, message: "Credenciais inválidas." };
  }

  const rowFallback = await fetchUserByUsername(loginTenant, username);
  if (rowFallback && verifyPbkdf2Password(password, rowFallback.password_hash)) {
    await establishSession({
      userId: String(rowFallback.id),
      username: rowFallback.username,
      role: roleFromRow(rowFallback.role),
      tenantId: String(rowFallback.tenant_id || "default"),
    });
  }

  await logPrototypeLoginIngest({
    tenantId: loginTenant,
    username,
    success: false,
    action: "login_failure",
    detail: { reason: "bad_credentials" },
  });
  return { ok: false, message: "Credenciais inválidas." };
}

export async function logout(): Promise<void> {
  const session = await getSession();
  if (session?.userId) {
    await logPrototypeAuditEvent("login", "logout", {
      username: session.username,
      tenant_id: session.tenantId,
    });
  }
  (await cookies()).delete(SESSION_COOKIE_NAME);
  redirect("/login");
}
