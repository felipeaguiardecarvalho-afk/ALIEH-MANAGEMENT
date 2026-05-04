import "server-only";
import postgres from "postgres";

const databaseUrl = process.env.DATABASE_URL || process.env.SUPABASE_DB_URL;

export const hasDatabaseUrl = Boolean(databaseUrl);

let client: postgres.Sql | null = null;

export function db() {
  if (!databaseUrl) {
    throw new Error("DATABASE_URL or SUPABASE_DB_URL is not configured.");
  }

  if (!client) {
    client = postgres(databaseUrl, {
      connect_timeout: 5,
      idle_timeout: 20,
      max: 3,
      prepare: false,
      ssl: process.env.POSTGRES_SSL === "false" ? false : "require",
    });
  }

  return client;
}

export function getTenantId() {
  return process.env.ALIEH_TENANT_ID?.trim() || "default";
}
