import "server-only";

import { PROTOTYPE_OPEN_ENV } from "@/lib/auth/constants";
import { resolveRole } from "@/lib/tenant";

export type RbacFail = { ok: false; message: string };

/** Administrador ou modo aberto (`ALIEH_PROTOTYPE_OPEN=1`). */
export async function requireAdmin(): Promise<RbacFail | null> {
  if (process.env[PROTOTYPE_OPEN_ENV] === "1") return null;
  const role = await resolveRole();
  if (role === "admin") return null;
  return { ok: false, message: "Apenas administradores podem executar esta ação." };
}

export async function requireOperator(): Promise<RbacFail | null> {
  if (process.env[PROTOTYPE_OPEN_ENV] === "1") return null;
  const role = await resolveRole();
  if (role === "admin" || role === "operator") return null;
  return { ok: false, message: "Operador ou administrador necessário." };
}
