import { PROTOTYPE_OPEN_ENV } from "@/lib/auth/constants";

export type AliehEnv = "development" | "staging" | "production";

/**
 * Canonical deployment tier. Prefer explicit `ALIEH_ENV`; otherwise infer from Vercel / Node.
 */
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

/**
 * Modo aberto (sem login) só em desenvolvimento/staging — nunca em produção, mesmo se a env estiver errada.
 */
export function isPrototypeOpenEffective(): boolean {
  if (isProductionTier()) return false;
  return process.env[PROTOTYPE_OPEN_ENV] === "1";
}

function requireNonEmpty(name: string, value: string | undefined, context: string): void {
  if (!value?.trim()) {
    throw new Error(`${name} é obrigatório em ${context}.`);
  }
}

/**
 * Falha no arranque do servidor Node (instrumentation) se o tier for produção e faltar config crítica.
 * Não altera lógica de negócio — só validação de ambiente.
 */
export function assertProductionServerEnv(): void {
  if (!isProductionTier()) return;

  requireNonEmpty("AUTH_SESSION_SECRET", process.env.AUTH_SESSION_SECRET, "produção (ALIEH_ENV=production / tier produção)");
  const secret = process.env.AUTH_SESSION_SECRET!.trim();
  if (secret.length < 32) {
    throw new Error("AUTH_SESSION_SECRET em produção deve ter pelo menos 32 caracteres.");
  }

  requireNonEmpty("API_PROTOTYPE_URL", process.env.API_PROTOTYPE_URL, "produção");
  requireNonEmpty("DATABASE_URL", process.env.DATABASE_URL || process.env.SUPABASE_DB_URL, "produção");

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  if (supabaseUrl) {
    requireNonEmpty("NEXT_PUBLIC_SUPABASE_ANON_KEY", process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY, "produção");
  }

  const openVal = (process.env[PROTOTYPE_OPEN_ENV] ?? "").trim();
  if (openVal !== "0") {
    throw new Error(
      `Em produção defina explicitamente ${PROTOTYPE_OPEN_ENV}=0 (modo fechado). Valor actual: "${openVal || "(ausente)"}".`
    );
  }
}

/**
 * Quando `ALIEH_STRICT_QA_ENV=1` (jobs de gate / pré-deploy com E2E na mesma máquina),
 * exige o conjunto completo de variáveis — **não** usar em servidores de produção reais
 * (lá não existem credenciais E2E nem `ALIEH_API_TEST_URL`).
 */
export function assertStrictQaOrchestrationEnv(): void {
  if ((process.env.ALIEH_STRICT_QA_ENV || "").trim() !== "1") {
    return;
  }
  const need = [
    "AUTH_SESSION_SECRET",
    "API_PROTOTYPE_URL",
    "DATABASE_URL",
    PROTOTYPE_OPEN_ENV,
    "ALIEH_API_TEST_URL",
    "ALIEH_E2E_USERNAME",
    "ALIEH_E2E_PASSWORD",
  ] as const;
  const missing: string[] = [];
  for (const name of need) {
    if (name === "DATABASE_URL") {
      if (!(process.env.DATABASE_URL?.trim() || process.env.SUPABASE_DB_URL?.trim())) {
        missing.push("DATABASE_URL ou SUPABASE_DB_URL");
      }
      continue;
    }
    if (!(process.env[name] ?? "").trim()) {
      missing.push(name);
    }
  }
  if (missing.length) {
    throw new Error(
      `ALIEH_STRICT_QA_ENV=1: defina todas as variáveis de orquestração QA. Em falta: ${missing.join(", ")}.`
    );
  }
  const secret = process.env.AUTH_SESSION_SECRET!.trim();
  if (secret.length < 32) {
    throw new Error("ALIEH_STRICT_QA_ENV=1: AUTH_SESSION_SECRET deve ter pelo menos 32 caracteres.");
  }
  const open = (process.env[PROTOTYPE_OPEN_ENV] ?? "").trim();
  if (open !== "0") {
    throw new Error(`ALIEH_STRICT_QA_ENV=1: exige ${PROTOTYPE_OPEN_ENV}=0 (sem modo protótipo aberto).`);
  }
}

/**
 * Staging (preview / homologação): mesmos segredos mínimos que produção para não aceitar tráfego com config vazia.
 * `ALIEH_PROTOTYPE_OPEN` pode ser `0` ou `1` (homologação pode testar UI fechada ou fluxo aberto).
 */
export function assertStagingServerEnv(): void {
  if (!isStagingTier()) return;

  requireNonEmpty("AUTH_SESSION_SECRET", process.env.AUTH_SESSION_SECRET, "staging (preview / homologação)");
  const secret = process.env.AUTH_SESSION_SECRET!.trim();
  if (secret.length < 32) {
    throw new Error("AUTH_SESSION_SECRET em staging deve ter pelo menos 32 caracteres.");
  }
  requireNonEmpty("API_PROTOTYPE_URL", process.env.API_PROTOTYPE_URL, "staging");
  requireNonEmpty("DATABASE_URL", process.env.DATABASE_URL || process.env.SUPABASE_DB_URL, "staging");

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  if (supabaseUrl) {
    requireNonEmpty("NEXT_PUBLIC_SUPABASE_ANON_KEY", process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY, "staging");
  }
}
