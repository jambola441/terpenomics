/* ============================================================================
   StaffGate — the door to /admin.

   Staff sign in on their own page, /staff. A signed-out visit to any admin
   screen is sent there and comes back afterwards, rather than loading the
   screen and failing every request. Whether a signed-in account may see the
   admin is still the API's call (routes/admin/auth.py); this only checks that
   there is someone to ask about.
   ========================================================================== */

import { useEffect, useState } from 'react'
import type { Session } from '@supabase/auth-js'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import supabase from './utils/supabase'
import { t } from './theme'

export default function StaffGate() {
  const location = useLocation()
  const [session, setSession] = useState<Session | null | undefined>(undefined)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session ?? null))
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => sub.subscription.unsubscribe()
  }, [])

  if (session === undefined) return <div style={{ minHeight: '100vh', background: t.bg }} />
  if (!session) {
    return <Navigate to="/staff" replace state={{ from: location.pathname + location.search }} />
  }
  return <main><Outlet /></main>
}
