/**
 * Sincroniza variáveis do monorepo (.env na raiz + web-prototype/.env.local)
 * para o projecto Vercel ligado em web-prototype/ (production + preview).
 *
 * Uso (na raiz do repo): node scripts/deploy/vercel-env-sync.mjs
 *
 * Preview: a CLI Vercel pede branch mesmo com `--value` (bug conhecido). Este script
 * usa a REST API para `target: preview` com `gitBranch: null` (todas as branches),
 * desde que exista `VERCEL_TOKEN` e `VERCEL_PROJECT_ID` (ou `web-prototype/.vercel/project.json`).
 *
 * API_PROTOTYPE_URL: usa a env `ALIEH_RENDER_API_URL` no shell se quiseres outro host;
 * senão https://alieh-api-prototype.onrender.com (nome do serviço em render.yaml).
 */
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
const WEB = path.join(ROOT, "web-prototype");

const RENDER_API_DEFAULT = "https://alieh-api-prototype.onrender.com";

function parseEnvFile(filePath) {
  if (!existsSync(filePath)) return {};
  const out = {};
  for (const line of readFileSync(filePath, "utf8").split(/\r?\n/)) {
    if (/^\s*#/.test(line) || !line.trim()) continue;
    const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!m) continue;
    let v = m[2].trim();
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
      v = v.slice(1, -1);
    }
    out[m[1]] = v;
  }
  return out;
}

function readLinkedVercelProject() {
  const p = path.join(WEB, ".vercel", "project.json");
  if (!existsSync(p)) return { projectId: "", teamId: "" };
  try {
    const j = JSON.parse(readFileSync(p, "utf8"));
    return {
      projectId: typeof j.projectId === "string" ? j.projectId : "",
      teamId: typeof j.orgId === "string" ? j.orgId : "",
    };
  } catch {
    return { projectId: "", teamId: "" };
  }
}

function vercelEnvAddCli(key, envName, value) {
  const r = spawnSync(
    "npx",
    ["vercel@latest", "env", "add", key, envName, "--value", value, "--yes", "--sensitive", "--force"],
    { cwd: WEB, encoding: "utf8", shell: true },
  );
  if (r.status !== 0) {
    process.stderr.write(
      `vercel env add ${key} ${envName} failed status=${r.status}\n${r.stderr || ""}\n${r.stdout || ""}\n${r.error || ""}\n`,
    );
    process.exit(r.status ?? 1);
  }
}

/**
 * Preview para todas as branches (gitBranch null). Requer token com permissão no projecto.
 * @see https://github.com/vercel/vercel/issues/15763
 */
async function vercelEnvUpsertPreviewApi(key, value, projectId, teamId, token) {
  const params = new URLSearchParams({ upsert: "true" });
  if (teamId) params.set("teamId", teamId);
  const url = `https://api.vercel.com/v10/projects/${encodeURIComponent(projectId)}/env?${params}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      key,
      value,
      type: "encrypted",
      target: ["preview"],
      gitBranch: null,
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Vercel API preview ${key}: HTTP ${res.status} ${text}`);
  }
}

const rootEnv = parseEnvFile(path.join(ROOT, ".env"));
const localEnv = parseEnvFile(path.join(WEB, ".env.local"));
const merged = { ...rootEnv, ...localEnv };

merged.ALIEH_ENV = "production";
merged.ALIEH_PROTOTYPE_OPEN = "0";
merged.ALIEH_TENANT_ID = (merged.ALIEH_TENANT_ID || "default").trim();

const apiUrl = (process.env.ALIEH_RENDER_API_URL || "").trim() || RENDER_API_DEFAULT;
merged.API_PROTOTYPE_URL = apiUrl;

if (!merged.AUTH_SESSION_SECRET?.trim() || merged.AUTH_SESSION_SECRET.trim().length < 32) {
  merged.AUTH_SESSION_SECRET = randomBytes(32).toString("hex");
}

if (!merged.PROTOTYPE_AUDIT_INGEST_SECRET?.trim()) {
  merged.PROTOTYPE_AUDIT_INGEST_SECRET = randomBytes(24).toString("hex");
}

/** Chaves que o Next precisa em produção/preview (instrumentation + runtime). */
const KEYS = [
  "ALIEH_ENV",
  "ALIEH_PROTOTYPE_OPEN",
  "ALIEH_TENANT_ID",
  "DATABASE_URL",
  "SUPABASE_DB_URL",
  "SUPABASE_URL",
  "SUPABASE_ANON_KEY",
  "NEXT_PUBLIC_SUPABASE_URL",
  "NEXT_PUBLIC_SUPABASE_ANON_KEY",
  "API_PROTOTYPE_URL",
  "AUTH_SESSION_SECRET",
  "ALIEH_AUTH_USERNAME",
  "ALIEH_AUTH_PASSWORD",
  "PROTOTYPE_AUDIT_INGEST_SECRET",
];

const linked = readLinkedVercelProject();
const projectId = (process.env.VERCEL_PROJECT_ID || linked.projectId || "").trim();
const teamId = (process.env.VERCEL_TEAM_ID || linked.teamId || "").trim();
const vercelToken = (process.env.VERCEL_TOKEN || "").trim();

for (const key of KEYS) {
  const v = merged[key];
  if (v == null || String(v).trim() === "") continue;
  const val = String(v).trim();
  vercelEnvAddCli(key, "production", val);
}

if (vercelToken && projectId) {
  for (const key of KEYS) {
    const v = merged[key];
    if (v == null || String(v).trim() === "") continue;
    await vercelEnvUpsertPreviewApi(key, String(v).trim(), projectId, teamId, vercelToken);
  }
  console.log("Vercel: production (CLI) + preview (API, todas as branches).");
} else {
  console.log(
    "Vercel: variáveis sincronizadas (production apenas).\n" +
      "Preview: omitido — a CLI Vercel não define preview para «todas as branches» sem bug. " +
      "Defina VERCEL_TOKEN e VERCEL_PROJECT_ID (ou `vercel link` em web-prototype) para o script aplicar preview via API.",
  );
}
