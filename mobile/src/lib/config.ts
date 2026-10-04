// Read once at startup. Expo inlines EXPO_PUBLIC_* at build time, so a missing
// value is a build problem, and failing loudly here beats a blank screen later.
function required(name: string, value: string | undefined): string {
  if (!value) throw new Error(`Missing ${name}. Copy mobile/.env.example to mobile/.env.local.`)
  return value
}

export const API_BASE = required('EXPO_PUBLIC_API_BASE_URL', process.env.EXPO_PUBLIC_API_BASE_URL).replace(/\/$/, '')
export const SUPABASE_URL = required('EXPO_PUBLIC_SUPABASE_URL', process.env.EXPO_PUBLIC_SUPABASE_URL)
export const SUPABASE_ANON_KEY = required('EXPO_PUBLIC_SUPABASE_ANON_KEY', process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY)
