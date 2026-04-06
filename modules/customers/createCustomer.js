import { supabase } from '../supabase/client.js'

const CUSTOMERS_TABLE = 'customers'

/**
 * Insere um registro na tabela `customers` e devolve `{ data, error }` como o cliente Supabase.
 */
export async function createCustomer(customerRecord) {
  const previewKeys =
    customerRecord && typeof customerRecord === 'object'
      ? Object.keys(customerRecord)
      : []

  console.debug('[customers.createCustomer] insert', {
    table: CUSTOMERS_TABLE,
    payloadKeys: previewKeys,
  })

  const { data, error } = await supabase
    .from(CUSTOMERS_TABLE)
    .insert([customerRecord])
    .select()

  if (error) {
    console.debug('[customers.createCustomer] supabase error', {
    code: error.code,
    message: error.message,
    details: error.details,
    hint: error.hint,
    })
  } else {
    console.debug('[customers.createCustomer] ok', {
      returnedRows: Array.isArray(data) ? data.length : data ? 1 : 0,
    })
  }

  return { data, error }
}
