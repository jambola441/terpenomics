import 'react-native-url-polyfill/auto'
import { AppState, Platform } from 'react-native'
import * as SecureStore from 'expo-secure-store'
import { createClient } from '@supabase/supabase-js'
import { SUPABASE_URL, SUPABASE_ANON_KEY } from './config'

/**
 * Session storage in the iOS Keychain. A Supabase session (two JWTs plus the
 * user record) can run past the ~2KB SecureStore advises per value, so it is
 * split into chunks with the chunk count stored under the key itself. The cart
 * is saved the same way (lib/cart.tsx).
 */
const CHUNK = 1800

export const keychainStorage = {
  async getItem(key: string): Promise<string | null> {
    const count = await SecureStore.getItemAsync(key)
    if (count === null) return null
    const parts: string[] = []
    for (let i = 0; i < Number(count); i++) {
      const part = await SecureStore.getItemAsync(`${key}.${i}`)
      if (part === null) return null
      parts.push(part)
    }
    return parts.join('')
  },
  async setItem(key: string, value: string): Promise<void> {
    await keychainStorage.removeItem(key)
    const n = Math.ceil(value.length / CHUNK)
    for (let i = 0; i < n; i++) {
      await SecureStore.setItemAsync(`${key}.${i}`, value.slice(i * CHUNK, (i + 1) * CHUNK))
    }
    await SecureStore.setItemAsync(key, String(n))
  },
  async removeItem(key: string): Promise<void> {
    const count = await SecureStore.getItemAsync(key)
    if (count === null) return
    for (let i = 0; i < Number(count); i++) await SecureStore.deleteItemAsync(`${key}.${i}`)
    await SecureStore.deleteItemAsync(key)
  },
}

const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    storage: Platform.OS === 'web' ? undefined : keychainStorage,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
})

// Supabase refreshes tokens on a timer, which a backgrounded app can't run.
// Pause it in the background and resume (refreshing if overdue) on return.
if (Platform.OS !== 'web') {
  AppState.addEventListener('change', state => {
    if (state === 'active') supabase.auth.startAutoRefresh()
    else supabase.auth.stopAutoRefresh()
  })
}

export default supabase
