/**
 * Paridade com `utils/password_hash.py` (PBKDF2-HMAC-SHA256, formato iterations$salt_hex$dk_hex).
 * A tabela `users` usa esse esquema — não bcrypt.
 */

import { pbkdf2Sync, timingSafeEqual } from "node:crypto";

export function verifyPbkdf2Password(plain: string, stored: string): boolean {
  try {
    const parts = stored.split("$");
    if (parts.length !== 3) return false;
    const iterations = parseInt(parts[0], 10);
    if (!Number.isFinite(iterations) || iterations < 1) return false;
    const salt = Buffer.from(parts[1], "hex");
    const expected = Buffer.from(parts[2], "hex");
    if (!salt.length || !expected.length) return false;
    const dk = pbkdf2Sync(Buffer.from(plain, "utf8"), salt, iterations, expected.length, "sha256");
    return dk.length === expected.length && timingSafeEqual(dk, expected);
  } catch {
    return false;
  }
}

export function normalizeUsername(username: string): string {
  return (username || "").trim().toLowerCase();
}

export function legacyCredentialsConfigured(): boolean {
  const u = (process.env.ALIEH_AUTH_USERNAME || "").trim();
  const p = process.env.ALIEH_AUTH_PASSWORD;
  return Boolean(u && p != null && String(p).length > 0);
}

export function legacyLoginOk(username: string, password: string): boolean {
  const u = (process.env.ALIEH_AUTH_USERNAME || "").trim();
  const p = String(process.env.ALIEH_AUTH_PASSWORD ?? "");
  if (!u || !p) return false;
  const userIn = (username || "").trim();
  try {
    return (
      timingSafeEqual(Buffer.from(userIn, "utf8"), Buffer.from(u, "utf8")) &&
      timingSafeEqual(Buffer.from(password, "utf8"), Buffer.from(p, "utf8"))
    );
  } catch {
    return false;
  }
}
