/**
 * Gate QA: Supabase (`DATABASE_URL`) + schema/seed no **host** + **Docker** só com `qa-api` + `qa-web`.
 * Pytest (host) + Playwright (host) contra API (:36101) e Next (:3000).
 *
 * Requisitos: `DATABASE_URL` (Supabase), Docker, Python+deps do repo, Node na máquina (só para Playwright/npm test).
 * Opcional: `ALIEH_ALLOW_NON_SUPABASE_DB=1` se o hostname não contiver `supabase`.
 *
 * Uso: `npm run test:qa:full:docker`
 */

import { execSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
const COMPOSE_FILE = path.join(ROOT, "docker-compose.qa.yml");
const composeBase = `docker compose -f "${COMPOSE_FILE}" --profile gate`;

const QA_API = "http://127.0.0.1:36101";
const QA_E2E_USER = "e2e_ci";
const QA_E2E_PASS = "E2E_ci_change_me_!";
const QA_SESSION = "qa-local-session-secret-min-32-chars-long!!";

/** Último env passado ao `docker compose` (para `down` / logs). */
let gateComposeEnv = null;

function composeEnvSafe() {
  const databaseUrl = (process.env.DATABASE_URL || "").trim();
  return {
    ...process.env,
    ...(databaseUrl ? { DATABASE_URL: databaseUrl } : {}),
    AUTH_SESSION_SECRET: QA_SESSION,
  };
}

function requireDatabaseUrl() {
  const url = (process.env.DATABASE_URL || "").trim();
  if (!url) {
    console.error(
      "Defina DATABASE_URL (mesma instância Supabase que o Streamlit — Settings → Database)."
    );
    process.exit(1);
  }
  let host = "";
  try {
    const normalized = url.replace(/^postgres(ql)?:/i, "http:");
    host = new URL(normalized).hostname.toLowerCase();
  } catch {
    console.error("DATABASE_URL não é um URL válido.");
    process.exit(1);
  }
  const allowNonSupabase = (process.env.ALIEH_ALLOW_NON_SUPABASE_DB || "").trim() === "1";
  if (!allowNonSupabase && !host.includes("supabase")) {
    console.error(
      "O gate espera Supabase (hostname com 'supabase'). Para outro Postgres: ALIEH_ALLOW_NON_SUPABASE_DB=1."
    );
    process.exit(1);
  }
  return url;
}

function compose(args, extraEnv = {}) {
  execSync(`${composeBase} ${args}`, {
    cwd: ROOT,
    stdio: "inherit",
    env: { ...process.env, ...extraEnv },
  });
}

function waitHttp(url, label, maxMs = 180_000) {
  const deadline = Date.now() + maxMs;
  return new Promise((resolve, reject) => {
    const tick = () => {
      if (Date.now() > deadline) {
        reject(new Error(`Timeout à espera de ${label} (${url})`));
        return;
      }
      const req = http.get(url, (res) => {
        res.resume();
        if (res.statusCode !== undefined && res.statusCode < 500) resolve();
        else setTimeout(tick, 800);
      });
      req.on("error", () => setTimeout(tick, 800));
    };
    tick();
  });
}

function hostPyEnv(databaseUrl) {
  return {
    ...process.env,
    DATABASE_URL: databaseUrl,
    PYTHONPATH: ROOT,
  };
}

/** Se `DATABASE_URL` não estiver no ambiente, lê da raiz `.env` (Passo 1). */
function loadDatabaseUrlFromRootDotEnv() {
  if ((process.env.DATABASE_URL || "").trim()) {
    return;
  }
  const p = path.join(ROOT, ".env");
  if (!existsSync(p)) {
    return;
  }
  const lines = readFileSync(p, "utf8").split(/\r?\n/);
  for (const line of lines) {
    if (/^\s*#/.test(line) || !line.trim()) {
      continue;
    }
    const m = line.match(/^\s*DATABASE_URL\s*=\s*(.*)$/);
    if (!m) {
      continue;
    }
    let v = m[1].trim();
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
      v = v.slice(1, -1);
    }
    if (v) {
      process.env.DATABASE_URL = v;
    }
    return;
  }
}

async function main() {
  console.log("=== ALIEH full QA gate (Supabase + Docker: qa-api + qa-web) ===\n");

  loadDatabaseUrlFromRootDotEnv();
  const databaseUrl = requireDatabaseUrl();
  const composeEnv = {
    ...process.env,
    DATABASE_URL: databaseUrl,
    AUTH_SESSION_SECRET: QA_SESSION,
  };
  gateComposeEnv = composeEnv;

  try {
    execSync("docker info", { stdio: "ignore" });
  } catch {
    console.error("Docker não está acessível. Inicie o Docker Desktop e volte a correr: npm run test:qa:full:docker");
    process.exit(1);
  }

  try {
    compose("down", composeEnv);
  } catch {
    /* ignore */
  }

  console.log("\n--- schema.sql (python -m database.schema_apply — idempotente, sem reset) ---\n");
  execSync("python -m database.schema_apply", {
    cwd: ROOT,
    stdio: "inherit",
    env: hostPyEnv(databaseUrl),
  });

  console.log("\n--- seed utilizador E2E ---\n");
  execSync("python scripts/ci/seed_e2e_user.py", {
    cwd: ROOT,
    stdio: "inherit",
    env: hostPyEnv(databaseUrl),
  });

  console.log("\n--- Docker: qa-api + qa-web (npm ci + build no contentor Next) ---\n");
  compose("up -d qa-api qa-web", composeEnv);

  await waitHttp(`${QA_API}/health`, "API /health", 900_000);
  await waitHttp("http://127.0.0.1:3000/login", "Next /login", 1_200_000);

  const pyEnv = {
    ...process.env,
    DATABASE_URL: databaseUrl,
    ALIEH_PG_INTEGRATION: "1",
    ALIEH_API_TEST_URL: QA_API,
    ALIEH_QA_GATE: "1",
    CI: "true",
  };

  console.log("\n--- pytest: regressão (inclui integração PG) ---\n");
  execSync("python -m pytest tests -v --tb=short --ignore=tests/api", {
    cwd: ROOT,
    env: pyEnv,
    stdio: "inherit",
  });

  console.log("\n--- pytest: API live ---\n");
  execSync("python -m pytest tests/api -v --tb=short -m live_api", {
    cwd: ROOT,
    env: pyEnv,
    stdio: "inherit",
  });

  console.log("\n--- Playwright E2E ---\n");
  execSync("npm run test:e2e", {
    cwd: ROOT,
    env: {
      ...process.env,
      DATABASE_URL: databaseUrl,
      PLAYWRIGHT_BASE_URL: "http://127.0.0.1:3000",
      ALIEH_E2E_USERNAME: QA_E2E_USER,
      ALIEH_E2E_PASSWORD: QA_E2E_PASS,
      ALIEH_STRICT_E2E: "1",
      CI: "true",
    },
    stdio: "inherit",
  });

  console.log("\n=== GATE OK — regressão + API + E2E sem skips ===\n");
}

main()
  .catch((e) => {
    console.error(e);
    try {
      console.error("\n--- logs qa-api ---\n");
      execSync(`${composeBase} logs qa-api --tail 120`, {
        cwd: ROOT,
        stdio: "inherit",
        env: composeEnvSafe(),
      });
    } catch {
      /* ignore */
    }
    try {
      console.error("\n--- logs qa-web ---\n");
      execSync(`${composeBase} logs qa-web --tail 200`, {
        cwd: ROOT,
        stdio: "inherit",
        env: gateComposeEnv || composeEnvSafe(),
      });
    } catch {
      /* ignore */
    }
    process.exitCode = 1;
  })
  .finally(() => {
    try {
      compose("down", gateComposeEnv || composeEnvSafe());
    } catch {
      /* ignore */
    }
  });
