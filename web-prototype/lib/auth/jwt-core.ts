import * as jose from "jose";

import type { Role } from "@/lib/role";

export type AuthSession = {
  userId: string;
  username: string;
  role: Role;
  tenantId: string;
};

function getJwtSecretBytes(): Uint8Array {
  const raw = process.env.AUTH_SESSION_SECRET?.trim();
  if (!raw || raw.length < 16) {
    throw new Error("AUTH_SESSION_SECRET missing or too short (min 16 chars).");
  }
  return new TextEncoder().encode(raw);
}

export async function signSessionToken(payload: {
  uid: string;
  sub: string;
  role: string;
  tid: string;
}): Promise<string> {
  const secret = getJwtSecretBytes();
  return new jose.SignJWT({
    uid: payload.uid,
    role: payload.role,
    tid: payload.tid,
  })
    .setSubject(payload.sub)
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("7d")
    .sign(secret);
}

export async function verifySessionToken(token: string): Promise<AuthSession | null> {
  try {
    const secret = getJwtSecretBytes();
    const { payload } = await jose.jwtVerify(token, secret);
    const uid = String(payload.uid ?? "").trim();
    const sub = String(payload.sub ?? "").trim();
    const tid = String(payload.tid ?? "").trim() || "default";
    let roleRaw = String(payload.role ?? "").trim().toLowerCase();
    if (roleRaw !== "admin" && roleRaw !== "operator" && roleRaw !== "viewer") {
      roleRaw = "operator";
    }
    const role = roleRaw as Role;
    if (!uid || !sub) return null;
    return { userId: uid, username: sub, role, tenantId: tid };
  } catch {
    return null;
  }
}

export async function verifySessionTokenEdge(
  token: string,
  secretString: string
): Promise<boolean> {
  try {
    if (!secretString || secretString.length < 16) return false;
    const secret = new TextEncoder().encode(secretString);
    await jose.jwtVerify(token, secret);
    return true;
  } catch {
    return false;
  }
}
