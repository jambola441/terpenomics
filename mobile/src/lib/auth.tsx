import { createContext, use, useCallback, useEffect, useState, type PropsWithChildren } from 'react'
import type { Session } from '@supabase/supabase-js'
import type { CustomerProfile } from '@web/types'
import supabase from './supabase'
import { api, ApiError } from './api'
import { confirmAge as storeAgeConfirmation, isAgeConfirmed } from './ageGate'

type AuthState = {
  /** undefined while the stored session is still being read from the Keychain. */
  session: Session | null | undefined
  /** undefined while being read from the Keychain. Asked once, before sign-in. */
  ageConfirmed: boolean | undefined
  confirmAge: () => Promise<void>
  /** The signed-in customer: undefined while loading, null when signed out or
   *  it could not be loaded (see profileError). Drives the sign-up gate. */
  profile: CustomerProfile | null | undefined
  profileError: string | null
  /** Re-read /me, e.g. after a retry. */
  reloadProfile: () => Promise<void>
  /** Adopt a /me response the caller already has (sign-up, profile edits). */
  setProfile: (p: CustomerProfile) => void
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
  const [ageConfirmed, setAgeConfirmed] = useState<boolean | undefined>(undefined)
  // The profile is remembered with the user it belongs to, so a sign-out or a
  // different sign-in reads as "not loaded" without resetting state in an effect.
  const [loaded, setLoaded] = useState<{ userId: string; profile: CustomerProfile | null; error: string | null } | null>(null)
  const userId = session?.user.id ?? null

  const fetchProfile = useCallback(
    (uid: string) =>
      loadProfile().then(
        p => setLoaded({ userId: uid, profile: p, error: null }),
        err => setLoaded({ userId: uid, profile: null, error: err instanceof Error ? err.message : String(err) }),
      ),
    [],
  )

  useEffect(() => {
    isAgeConfirmed().then(setAgeConfirmed)
    supabase.auth.getSession().then(({ data }) => setSession(data.session ?? null))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => subscription.unsubscribe()
  }, [])

  // Every signed-in user needs a customer row and its sign-up state before the
  // app proper opens. Keyed on the user, not the session: token refreshes
  // replace the session object without changing who is signed in.
  useEffect(() => {
    if (userId) fetchProfile(userId)
  }, [userId, fetchProfile])

  const current = userId && loaded?.userId === userId ? loaded : null
  const profile = session === undefined ? undefined : !userId ? null : current ? current.profile : undefined
  const profileError = current?.error ?? null

  const reloadProfile = useCallback(async () => {
    if (!userId) return
    setLoaded(null)
    await fetchProfile(userId)
  }, [userId, fetchProfile])

  const setProfile = useCallback((p: CustomerProfile) => {
    if (userId) setLoaded({ userId, profile: p, error: null })
  }, [userId])

  async function signInWithSms(challengeId: string, code: string) {
    // Phone login runs outside Supabase's own OTP path (see SMS_LOGIN.md): the
    // backend verifies the code and mints the session, and we adopt it here.
    const tokens = await api.auth.smsVerify(challengeId, code)
    const { error } = await supabase.auth.setSession({
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token,
    })
    if (error) throw new Error(error.message)
    // The profile effect above takes it from here.
  }

  async function confirmAge() {
    await storeAgeConfirmation()
    setAgeConfirmed(true)
  }

  async function signOut() {
    await supabase.auth.signOut()
  }

  return (
    <AuthContext.Provider
      value={{ session, ageConfirmed, confirmAge, profile, profileError, reloadProfile, setProfile, signInWithSms, signOut }}
    >
      {children}
    </AuthContext.Provider>
  )
}

/** /me, linking the login to a customer first if this is its first visit.
 *  Same first-login step as the web portal. */
async function loadProfile(): Promise<CustomerProfile> {
  try {
    return await api.me.getProfile()
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 404) throw err
  }
  await api.me.linkCustomer()
  return api.me.getProfile()
}
