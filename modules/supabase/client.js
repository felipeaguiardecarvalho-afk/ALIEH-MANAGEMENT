import { createClient } from '@supabase/supabase-js'

function requireEnv(name) {
  const v = (process.env[name] ?? '').trim()
  if (!v) {
    throw new Error(
      `Missing ${name}. Set it in the environment or load a .env file (e.g. node --env-file=.env …).`
    )
  }
  return v
}

const supabaseUrl = requireEnv('SUPABASE_URL')
const supabaseKey = requireEnv('SUPABASE_ANON_KEY')

export const supabase = createClient(supabaseUrl, supabaseKey)
