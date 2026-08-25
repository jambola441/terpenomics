import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import supabase from './utils/supabase'
import { takeNext } from './utils/redirect'

/**
 * Landing point for OAuth redirects.
 *
 * The Supabase client parses the session out of the URL on its own
 * (detectSessionInUrl is on by default), so this waits for that to land rather
 * than doing any exchange itself. Unlike the SMS path, our backend is not
 * involved at all — the session arrives already minted by Supabase.
 */
/**
 * A provider that refuses sends the reason back on the URL rather than giving
 * us a session. Read it during render so it becomes the initial state instead
 * of a set-state-in-effect.
 */
function providerError() {
  const params = new URLSearchParams(
    window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.search
  )
  const raw = params.get('error_description') || params.get('error')
  return raw ? decodeURIComponent(raw.replace(/\+/g, ' ')) : ''
}

export default function AuthCallback() {
  const [error, setError] = useState(providerError)
  const navigate = useNavigate()

  useEffect(() => {
    if (error) return
    let cancelled = false

    // Claimed once: a second read would find it already cleared.
    const next = takeNext()

    async function land(user) {
      if (cancelled) return
      // Mirrors the rule in Login.jsx: admins carry role="admin" on the JWT,
      // everyone else belongs in the customer portal — unless they were headed
      // somewhere specific before signing in.
      const fallback = user?.role === 'admin' ? '/admin' : '/portal'
      navigate(next || fallback, { replace: true })
    }

    // The session may already be in place by the time this mounts, so check
    // once before waiting on the event.
    supabase.auth.getSession().then(({ data }) => {
      if (data?.session) land(data.session.user)
    })

    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) land(session.user)
    })

    // Don't hang forever if the session never materializes.
    const timer = setTimeout(() => {
      if (!cancelled) setError('Sign-in did not complete. Try again.')
    }, 10000)

    return () => {
      cancelled = true
      clearTimeout(timer)
      sub?.subscription?.unsubscribe()
    }
  }, [navigate, error])

  return (
    <div style={wrapStyle}>
      {error ? (
        <>
          <p style={errStyle}>{error}</p>
          <button type="button" onClick={() => navigate('/', { replace: true })} style={linkStyle}>
            Back to sign in
          </button>
        </>
      ) : (
        <p style={msgStyle}>Signing you in…</p>
      )}
    </div>
  )
}

const wrapStyle = {
  minHeight: '100vh',
  background: '#080d18',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 16,
  fontFamily: "'Inter', system-ui, sans-serif",
  padding: '40px 24px',
}

const msgStyle = { margin: 0, fontSize: 14, color: '#475569' }
const errStyle = { margin: 0, fontSize: 14, color: '#f87171', textAlign: 'center', maxWidth: 360 }
const linkStyle = {
  background: 'none',
  border: 'none',
  color: '#2563eb',
  fontSize: 13,
  cursor: 'pointer',
  padding: 0,
}
