import "server-only";

import { isPrototypeOpenEffective } from "@/lib/env/alieh-runtime";
import { legacyCredentialsConfigured } from "@/lib/auth/password";
import { countUsers } from "@/lib/auth/users-db";
import { resolveRole } from "@/lib/tenant";

export type RbacFail = { ok: false; message: string };

/** Espelha ``is_auth_configured`` + ``require_*`` sem efeito quando não há login configurado. */
export async function isAuthConfigured(): Promise<boolean> {
  try {
    return (await countUsers()) > 0 || legacyCredentialsConfigured();
  } catch {
    return legacyCredentialsConfigured();
  }
}

/**
 * Paridade com ``utils.rbac.require_admin`` (precificação, estoque, exclusões irrevogáveis, …).
 */
export async function requireAdmin(): Promise<RbacFail | null> {
  if (isPrototypeOpenEffective()) return null;
  if (!(await isAuthConfigured())) return null;
  const role = await resolveRole();
  if (role === "admin") return null;
  return { ok: false, message: "Apenas administradores podem executar esta ação." };
}

/**
 * Precificação: com autenticação configurada, exige **admin** mesmo com
 * `ALIEH_PROTOTYPE_OPEN=1` (paridade com Streamlit em produção). Sem auth
 * configurada, mantém o bypass do protótipo (sem utilizadores / credenciais).
 */
export async function requireAdminForPricing(): Promise<RbacFail | null> {
  if (!(await isAuthConfigured())) return null;
  const role = await resolveRole();
  if (role === "admin") return null;
  return { ok: false, message: "Apenas administradores podem executar esta ação." };
}

/**
 * Paridade com ``utils.rbac.require_operator_or_admin`` (vendas, cadastro operacional, …).
 */
export async function requireOperator(): Promise<RbacFail | null> {
  if (isPrototypeOpenEffective()) return null;
  if (!(await isAuthConfigured())) return null;
  const role = await resolveRole();
  if (role === "admin" || role === "operator") return null;
  return { ok: false, message: "Operador ou administrador necessário." };
}
