/**
 * Falha antes de abrir o browser se o gate / CI prometer E2E completo sem credenciais.
 */
export default async function globalSetup(): Promise<void> {
  const password = (process.env.ALIEH_E2E_PASSWORD || process.env.ALIEH_CI_E2E_PASSWORD || "").trim();
  const strict = (process.env.ALIEH_STRICT_E2E || "").trim() === "1";
  const ci = (process.env.CI || "").toLowerCase() === "true";

  if ((ci || strict) && !password) {
    throw new Error(
      "E2E: defina ALIEH_E2E_PASSWORD ou ALIEH_CI_E2E_PASSWORD (obrigatório com CI=true ou ALIEH_STRICT_E2E=1)."
    );
  }
}
