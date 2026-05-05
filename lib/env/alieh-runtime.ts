import { PROTOTYPE_OPEN_ENV } from "@/lib/auth/constants";

export type AliehEnv = "development" | "staging" | "production";

export function getAliehEnv(): AliehEnv {
  const explicit = (process.env.ALIEH_ENV || "").trim().toLowerCase();
  if (explicit === "production" || explicit === "prod") return "production";
  if (explicit === "staging" || explicit === "stg") return "staging";
  if (explicit === "development" || explicit === "dev") return "development";

  const vercel = (process.env.VERCEL_ENV || "").trim().toLowerCase();
  if (vercel === "production") return "production";
  if (vercel === "preview") return "staging";

  if (process.env.NODE_ENV === "production") return "production";
  return "development";
}

export function isProductionTier(): boolean {
  return getAliehEnv() === "production";
}

export function isStagingTier(): boolean {
  return getAliehEnv() === "staging";
}

export function isPrototypeOpenEffective(): boolean {
  if (isProductionTier()) return false;
  if (process.env[PROTOTYPE_OPEN_ENV] === "1") return true;
  // `next dev` sem AUTH_SESSION_SECRET: mesmo comportamento que modo aberto (só tier development).
  if (
    getAliehEnv() === "development" &&
    !(process.env.AUTH_SESSION_SECRET || "").trim()
  ) {
    return true;
  }
  return false;
}
