// The web app uses Supabase for sign-in only, so it builds the auth client on
// its own rather than the whole supabase-js client, whose database, storage,
// realtime and functions clients nothing here calls (~80 KB of the bundle).
//
// The settings match what supabase-js's createClient passes to the same class,
// so sessions stored by the old client (same storage key) carry straight over.
import { AuthClient } from '@supabase/auth-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY || import.meta.env.VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY

if (!supabaseUrl || !supabaseKey) {
  throw new Error('Missing Supabase environment variables. Please check your .env file.')
}

const base = new URL(supabaseUrl.endsWith('/') ? supabaseUrl : `${supabaseUrl}/`)

const auth = new AuthClient({
  url: new URL('auth/v1', base).href,
  headers: { Authorization: `Bearer ${supabaseKey}`, apikey: supabaseKey },
  storageKey: `sb-${base.hostname.split('.')[0]}-auth-token`,
  autoRefreshToken: true,
  persistSession: true,
  detectSessionInUrl: true,
  flowType: 'implicit',
})

const supabase = { auth }

export default supabase
