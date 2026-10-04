import { createContext, use, useEffect, useState, type PropsWithChildren } from 'react'
import type { Session } from '@supabase/supabase-js'
import supabase from './supabase'
import { api } from './api'

type AuthState = {
  /** undefined while the stored session is still being read from the Keychain. */
  session: Session | null | undefined
  signInWithSms: (challengeId: string, code: string) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const value = use(AuthContext)
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>')
  return value
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<Session | null | undefined>(undefined)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session ?? null))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => subscription.unsubscribe()
  }, [])

  async function signInWithSms(challengeId: string, code: string) {
    // Phone login runs outside Supabase's own OTP path (see SMS_LOGIN.md): the
    // backend verifies the code and mints the session, and we adopt it here.
    const tokens = await api.auth.smsVerify(challengeId, code)
    const { error } = await supabase.auth.setSession({
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token,
    })
    if (error) throw new Error(error.message)

    // Same first-login step as the web portal: a fresh phone user has no
    // customer row until /me/link-customer finds or creates one.
    try {
      await api.me.getProfile()
    } catch {
      await api.me.linkCustomer()
    }
  }

  async function signOut() {
    await supabase.auth.signOut()
  }

  return <AuthContext.Provider value={{ session, signInWithSms, signOut }}>{children}</AuthContext.Provider>
}
