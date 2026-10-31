import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabasePublishableKey =
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabasePublishableKey) {
  console.error(
    '[ClarityX Auth] Missing Supabase configuration! Please ensure VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY are defined in frontend/.env'
  )
}

/**
 * Centralized Supabase browser client for authentication and session management.
 * Uses public anon/publishable credentials only.
 */
export const supabase = createClient(
  supabaseUrl || 'https://placeholder.supabase.co',
  supabasePublishableKey || 'placeholder-key',
  {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
      storage: window.localStorage,
    },
  }
)