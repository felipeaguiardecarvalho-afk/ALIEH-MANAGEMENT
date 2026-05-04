"use server";

import { apiPrototypeFetch, gateMutation, readApiError } from "@/lib/api-prototype";

export type MintSignedUploadResult =
  | { ok: true; bucket: string; path: string; token: string }
  | { ok: false; message: string };

/** Mints a Supabase signed upload slot. File bytes never pass through this action. */
export async function mintProductImageSignedUpload(
  filename: string,
  contentType: string
): Promise<MintSignedUploadResult> {
  const gate = await gateMutation();
  if (gate) return { ok: false, message: gate.message };

  const ct = (contentType || "application/octet-stream").trim().toLowerCase();
  try {
    const res = await apiPrototypeFetch("/storage/signed-upload", {
      method: "POST",
      json: { filename, content_type: ct },
    });
    if (!res.ok) {
      return { ok: false, message: await readApiError(res) };
    }
    const data = (await res.json()) as {
      bucket?: string;
      path?: string;
      token?: string;
    };
    const bucket = String(data.bucket ?? "");
    const path = String(data.path ?? "");
    const token = String(data.token ?? "");
    if (!bucket || !path || !token) {
      return { ok: false, message: "Resposta inválida da API de armazenamento." };
    }
    return { ok: true, bucket, path, token };
  } catch (e) {
    return {
      ok: false,
      message: e instanceof Error ? e.message : "Falha ao obter URL de upload.",
    };
  }
}
