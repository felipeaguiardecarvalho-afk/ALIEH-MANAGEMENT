"use server";

import { revalidatePath } from "next/cache";
import { db, getTenantId, hasDatabaseUrl } from "@/lib/db";
import { UAT_STATUS_ORDER, type UatStatus } from "@/lib/domain";

export type UatState = { ok: boolean; message: string };

export async function upsertUatRecord(
  _prev: UatState,
  formData: FormData
): Promise<UatState> {
  if (!hasDatabaseUrl) return { ok: false, message: "Banco não configurado." };

  const testId = String(formData.get("test_id") || "").trim();
  const statusRaw = String(formData.get("status") || "pending");
  const notes = String(formData.get("notes") || "").trim() || null;

  if (!testId) return { ok: false, message: "Caso UAT inválido." };
  const status: UatStatus = UAT_STATUS_ORDER.includes(statusRaw as UatStatus)
    ? (statusRaw as UatStatus)
    : "pending";

  const tenantId = getTenantId();
  const now = new Date().toISOString();
  const recordedAt = status === "pending" ? null : now;

  try {
    await db()`
      INSERT INTO uat_manual_checklist (
        tenant_id, test_id, status, notes, result_recorded_at,
        recorded_by_username, recorded_by_user_id, recorded_by_role, updated_at
      ) VALUES (
        ${tenantId}, ${testId}, ${status}, ${notes}, ${recordedAt},
        'web', null, 'admin', ${now}
      );
    `;
    revalidatePath("/uat");
    return { ok: true, message: "Caso UAT registrado." };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao gravar caso UAT.",
    };
  }
}
