import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || ''
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || ''

let client = null

export function isSupabaseConfigured() {
  return Boolean(supabaseUrl && supabaseAnonKey)
}

export function getSupabaseClient() {
  if (!isSupabaseConfigured()) return null
  if (client) return client
  client = createClient(supabaseUrl, supabaseAnonKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  })
  return client
}
