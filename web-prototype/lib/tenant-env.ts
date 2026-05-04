import "server-only";

/**
 * Inquilino por defeito quando não há JWT/cookie de sessão (paridade com env da app).
 * Sem literais de tenant na camada de dados — só variáveis de ambiente.
 */
export function defaultTenantIdFromEnv(): string {
  return (
    process.env.ALIEH_TENANT_ID?.trim() ||
    process.env.ALIEH_DEFAULT_TENANT_ID?.trim() ||
    ""
  );
}
