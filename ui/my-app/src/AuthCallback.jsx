import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import supabase from './utils/supabase'
import { peekNext, rememberNext } from './utils/redirect'
import { t } from './theme'
import { Logo } from './components/Icon'

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
  // Read once, not claimed until landing: a remount (StrictMode does one) must
  // still find it.
  const [next] = useState(peekNext)
  const navigate = useNavigate()

  // Only staff (/staff) and partners (/partner) sign in through a provider;
  // customers sign in by text and never come through here. A failure goes
  // back to the page it started from.
  const signInPage = next?.startsWith('/partner') ? '/partner' : '/staff'

  useEffect(() => {
    if (error) return
    let cancelled = false

    function land() {
      if (cancelled) return
      rememberNext(null)
      navigate(next || '/admin', { replace: true })
    }

    // The session may already be in place by the time this mounts, so check
    // once before waiting on the event.
    supabase.auth.getSession().then(({ data }) => {
      if (data?.session) land()
    })

    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) land()
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
  }, [navigate, error, next])

  return (
    <div style={wrapStyle}>
      <Logo size={30} style={{ marginBottom: 8 }} />
      {error ? (
        <>
          <p style={errStyle}>{error}</p>
          <button type="button" onClick={() => navigate(signInPage, { replace: true })} style={linkStyle}>
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
  background: t.bg,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 16,
  padding: '40px 16px',
}

const msgStyle = { margin: 0, fontSize: 14, color: t.text3 }
const errStyle = { margin: 0, fontSize: 14, color: t.danger, textAlign: 'center', maxWidth: 360 }
const linkStyle = {
  background: 'none',
  border: 'none',
  color: t.accent,
  fontSize: 13,
  fontWeight: 500,
  cursor: 'pointer',
  padding: 0,
}
