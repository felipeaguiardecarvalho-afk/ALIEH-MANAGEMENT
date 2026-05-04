"use server";

import { revalidatePath } from "next/cache";
import { db, getTenantId, hasDatabaseUrl } from "@/lib/db";

export type CustomerFormState = { ok: boolean; message: string };

function requireDatabase(): CustomerFormState | null {
  if (!hasDatabaseUrl) {
    return {
      ok: false,
      message:
        "Banco não configurado. Defina DATABASE_URL em .env para gravar clientes.",
    };
  }
  return null;
}

function str(value: FormDataEntryValue | null) {
  return typeof value === "string" ? value.trim() : "";
}

export async function createCustomer(
  _prev: CustomerFormState,
  formData: FormData
): Promise<CustomerFormState> {
  const dbCheck = requireDatabase();
  if (dbCheck) return dbCheck;

  const name = str(formData.get("name"));
  if (!name) return { ok: false, message: "Nome é obrigatório." };

  const tenantId = getTenantId();
  const now = new Date().toISOString().slice(0, 19);

  const cpf = str(formData.get("cpf")) || null;
  const phone = str(formData.get("phone")) || null;

  try {
    const sql = db();
    await sql.begin(async (tx) => {
      if (cpf) {
        const [dupCpf] = await tx`
          SELECT id FROM customers
          WHERE tenant_id = ${tenantId} AND cpf = ${cpf}
          LIMIT 1;
        `;
        if (dupCpf) throw new Error("Já existe cliente com esse CPF.");
      }
      if (phone) {
        const [dupPhone] = await tx`
          SELECT id FROM customers
          WHERE tenant_id = ${tenantId} AND phone = ${phone}
          LIMIT 1;
        `;
        if (dupPhone) throw new Error("Já existe cliente com esse telefone.");
      }

      const [seq] = await tx`
        INSERT INTO customer_sequence_counter (tenant_id, id, last_value)
        VALUES (${tenantId}, 1, 1)
        ON CONFLICT (tenant_id, id)
        DO UPDATE SET last_value = customer_sequence_counter.last_value + 1
        RETURNING last_value;
      `;
      const next = Number(seq?.last_value ?? 1);
      const code = `C${String(next).padStart(4, "0")}`;

      await tx`
        INSERT INTO customers (
          tenant_id, customer_code, name, cpf, rg, phone, email, instagram,
          zip_code, street, number, neighborhood, city, state, country, created_at
        ) VALUES (
          ${tenantId}, ${code}, ${name},
          ${cpf}, ${str(formData.get("rg")) || null},
          ${phone}, ${str(formData.get("email")) || null},
          ${str(formData.get("instagram")) || null},
          ${str(formData.get("zip_code")) || null},
          ${str(formData.get("street")) || null},
          ${str(formData.get("number")) || null},
          ${str(formData.get("neighborhood")) || null},
          ${str(formData.get("city")) || null},
          ${str(formData.get("state")) || null},
          ${str(formData.get("country")) || "Brasil"},
          ${now}
        );
      `;
    });

    revalidatePath("/customers");
    return { ok: true, message: "Cliente cadastrado." };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao cadastrar cliente.",
    };
  }
}

export async function deleteCustomer(id: number): Promise<CustomerFormState> {
  const dbCheck = requireDatabase();
  if (dbCheck) return dbCheck;
  try {
    await db()`
      DELETE FROM customers
      WHERE tenant_id = ${getTenantId()} AND id = ${id};
    `;
    revalidatePath("/customers");
    return { ok: true, message: "Cliente excluído." };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao excluir cliente.",
    };
  }
}
