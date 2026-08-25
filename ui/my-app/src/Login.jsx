import { useEffect, useState } from 'react'
import supabase from './utils/supabase'
import { useNavigate } from 'react-router-dom'
import { toE164, formatPhoneInput, formatE164ForDisplay } from './utils/phone'
import api from './api/client'

// Fallback cooldown. The SMS path uses whatever the backend reports instead.
const RESEND_SECONDS = 60

export default function Login() {
  const [channel, setChannel] = useState('sms') // 'sms' | 'email'
  const [step, setStep]       = useState('send')
  const [phone, setPhone]     = useState('')
  const [email, setEmail]     = useState('')
  const [sentTo, setSentTo]   = useState('')   // E.164 or email actually used for the send
  const [challengeId, setChallengeId] = useState('')  // backend handle for the SMS code
  const [code, setCode]       = useState('')
  const [msg, setMsg]         = useState('')
  const [loading, setLoading] = useState(false)
  const [isError, setIsError] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const [providers, setProviders] = useState([])  // OAuth providers actually enabled
  const navigate = useNavigate()

  // Ask Supabase which social providers are live rather than hardcoding them.
  // signInWithOAuth redirects the browser instead of making a request, so a
  // disabled provider would dump the user on a raw JSON error page. Rendering
  // only what is enabled means turning one on in the Supabase dashboard makes
  // the button appear with no code change, and nothing is clickable before then.
  useEffect(() => {
    let cancelled = false
    const url = import.meta.env.VITE_SUPABASE_URL
    const key = import.meta.env.VITE_SUPABASE_ANON_KEY || import.meta.env.VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY
    if (!url || !key) return

    fetch(`${url.replace(/\/$/, '')}/auth/v1/settings`, { headers: { apikey: key } })
      .then(r => (r.ok ? r.json() : null))
      .then(settings => {
        if (cancelled || !settings) return
        const external = settings.external || {}
        setProviders(SOCIAL_PROVIDERS.filter(p => external[p.id]))
      })
      .catch(() => { /* social sign-in simply stays hidden */ })

    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (cooldown <= 0) return
    const t = setTimeout(() => setCooldown(c => c - 1), 1000)
    return () => clearTimeout(t)
  }, [cooldown])

  function switchChannel(next) {
    setChannel(next)
    setStep('send')
    setCode('')
    setChallengeId('')
    setMsg('')
    setIsError(false)
  }

  function fail(message) {
    setIsError(true)
    setMsg(message)
  }

  function handleFailure(err) {
    // A 429 carries Retry-After; mirror it in the UI so the button reflects the
    // server's actual cooldown rather than our guess at it.
    if (err?.status === 429 && err.retryAfter) setCooldown(err.retryAfter)
    fail(err?.message || 'Something went wrong. Try again.')
  }

  /**
   * Request a code and return how many seconds until a resend is allowed.
   *
   * The two channels take different routes: email OTP is Supabase's own, while
   * SMS goes through our backend, which drives the SMS provider and hands back
   * a Supabase session only once the provider has validated the code.
   */
  async function requestCode(destination) {
    if (channel === 'sms') {
      const { challenge_id, resend_in } = await api.auth.smsStart(destination)
      setChallengeId(challenge_id)
      return resend_in || RESEND_SECONDS
    }

    const { error } = await supabase.auth.signInWithOtp({
      email: destination,
      options: { shouldCreateUser: true },
    })
    if (error) throw new Error(error.message)
    return RESEND_SECONDS
  }

  async function sendCode(e) {
    e.preventDefault()
    setMsg('')
    setIsError(false)

    let destination
    if (channel === 'sms') {
      destination = toE164(phone)
      if (!destination) return fail('Enter a valid mobile number, e.g. (555) 123-4567.')
    } else {
      destination = email.trim()
      if (!destination) return fail('Enter your email address.')
    }

    setLoading(true)
    try {
      const wait = await requestCode(destination)
      setSentTo(destination)
      setStep('verify')
      setCooldown(wait)
      setMsg(channel === 'sms' ? 'Code sent by text.' : 'Check your email for a 6-digit code.')
    } catch (err) {
      handleFailure(err)
    } finally {
      setLoading(false)
    }
  }

  async function resendCode() {
    if (cooldown > 0 || loading || !sentTo) return
    setMsg('')
    setIsError(false)
    setLoading(true)
    try {
      setCooldown(await requestCode(sentTo))
      setMsg('New code sent.')
    } catch (err) {
      handleFailure(err)
    } finally {
      setLoading(false)
    }
  }

  async function verifyCode(e) {
    e.preventDefault()
    setLoading(true)
    setMsg('')
    setIsError(false)

    try {
      let user

      if (channel === 'sms') {
        const session = await api.auth.smsVerify(challengeId, code)
        const { data, error } = await supabase.auth.setSession({
          access_token: session.access_token,
          refresh_token: session.refresh_token,
        })
        if (error) throw new Error(error.message)
        user = data?.user
      } else {
        const { data, error } = await supabase.auth.verifyOtp({
          email: sentTo,
          token: code,
          type: 'email',
        })
        if (error) throw new Error(error.message)
        user = data?.user
      }

      // Admins carry role="admin" on the Supabase JWT (see routes/admin/auth.py).
      // Everyone else who signs in by text lands in the customer portal.
      navigate(user?.role === 'admin' || channel === 'email' ? '/admin' : '/portal')
    } catch (err) {
      handleFailure(err)
      setLoading(false)
    }
  }

  /**
   * Hand off to an OAuth provider. Supabase owns this flow end to end: the
   * browser leaves for the provider and comes back to /auth/callback with a
   * session already in the URL, which the client picks up on its own. Nothing
   * routes through our backend, unlike the SMS path.
   */
  async function signInWithProvider(provider) {
    setIsError(false)
    setMsg('')
    setLoading(true)
    const { error } = await supabase.auth.signInWithOAuth({
      provider,
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    })
    // On success the browser is already navigating away, so only a failure
    // ever reaches here.
    if (error) {
      setLoading(false)
      fail(
        error.message?.includes('not enabled')
          ? `${provider === 'apple' ? 'Apple' : 'Google'} sign-in is not enabled yet.`
          : error.message || 'Could not start sign-in. Try again.'
      )
    }
  }

  const sendDisabled = loading || (channel === 'sms' ? !phone.trim() : !email.trim())

  return (
    <div style={{
      minHeight: '100vh',
      background: '#080d18',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      fontFamily: "'Inter', system-ui, sans-serif",
      padding: '40px 24px',
    }}>
      {/* Wordmark */}
      <div style={{
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.3em',
        textTransform: 'uppercase',
        color: '#334155',
        marginBottom: 48,
      }}>
        terpenomics
      </div>

      {/* Card */}
      <div style={{
        width: '100%',
        maxWidth: 400,
        background: '#0f172a',
        border: '1px solid #1e293b',
        borderRadius: 16,
        padding: '40px 36px',
        boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
      }}>
        {step === 'send' ? (
          <>
            <h2 style={headingStyle}>Sign in</h2>
            <p style={subheadStyle}>
              {channel === 'sms'
                ? "Enter your mobile number and we'll text you a one-time code."
                : "Enter your email and we'll send a one-time code."}
            </p>

            {providers.length > 0 && (
              <>
                <div style={providerRowStyle}>
                  {providers.map(p => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => signInWithProvider(p.id)}
                      disabled={loading}
                      style={providerBtnStyle(loading)}
                    >
                      <p.Mark />
                      Continue with {p.label}
                    </button>
                  ))}
                </div>

                <div style={dividerRowStyle}>
                  <span style={dividerLineStyle} />
                  <span style={dividerTextStyle}>or</span>
                  <span style={dividerLineStyle} />
                </div>
              </>
            )}

            <div style={tabRowStyle}>
              <button type="button" onClick={() => switchChannel('sms')} style={tabStyle(channel === 'sms')}>
                Text message
              </button>
              <button type="button" onClick={() => switchChannel('email')} style={tabStyle(channel === 'email')}>
                Email
              </button>
            </div>

            <form onSubmit={sendCode}>
              {channel === 'sms' ? (
                <>
                  <label style={labelStyle}>Mobile number</label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={e => setPhone(formatPhoneInput(e.target.value))}
                    placeholder="(555) 123-4567"
                    autoComplete="tel"
                    autoFocus
                    required
                    style={inputStyle}
                  />
                </>
              ) : (
                <>
                  <label style={labelStyle}>Email</label>
                  <input
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    autoComplete="email"
                    autoFocus
                    required
                    style={inputStyle}
                  />
                </>
              )}
              <button type="submit" disabled={sendDisabled} style={btnStyle(sendDisabled)}>
                {loading ? 'Sending…' : 'Send code'}
              </button>
            </form>

            {channel === 'sms' && (
              <p style={fineprintStyle}>
                Message and data rates may apply. Codes are single-use and expire shortly.
              </p>
            )}
          </>
        ) : (
          <>
            <h2 style={headingStyle}>
              {channel === 'sms' ? 'Check your texts' : 'Check your email'}
            </h2>
            <p style={subheadStyle}>
              We sent a 6-digit code to{' '}
              <span style={{ color: '#94a3b8', fontWeight: 500 }}>
                {channel === 'sms' ? formatE164ForDisplay(sentTo) : sentTo}
              </span>
            </p>
            <form onSubmit={verifyCode}>
              <label style={labelStyle}>Code</label>
              <input
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, ''))}
                placeholder="000000"
                inputMode="numeric"
                pattern="[0-9]*"
                autoComplete="one-time-code"
                maxLength={8}
                autoFocus
                required
                style={{ ...inputStyle, letterSpacing: '0.3em', fontSize: 22, textAlign: 'center' }}
              />
              <button type="submit" disabled={loading} style={btnStyle(loading)}>
                {loading ? 'Verifying…' : 'Continue'}
              </button>
            </form>

            <button
              type="button"
              onClick={resendCode}
              disabled={cooldown > 0 || loading}
              style={{
                ...linkBtnStyle,
                marginTop: 16,
                cursor: cooldown > 0 || loading ? 'default' : 'pointer',
              }}
            >
              {cooldown > 0 ? `Resend code in ${cooldown}s` : 'Resend code'}
            </button>

            <button
              type="button"
              onClick={() => { setStep('send'); setCode(''); setMsg(''); setIsError(false) }}
              style={linkBtnStyle}
            >
              ← Use a different {channel === 'sms' ? 'number' : 'email'}
            </button>
          </>
        )}

        {msg && (
          <p style={{
            marginTop: 20,
            marginBottom: 0,
            fontSize: 13,
            color: isError ? '#f87171' : '#4ade80',
            textAlign: 'center',
            lineHeight: 1.5,
          }}>
            {msg}
          </p>
        )}
      </div>
    </div>
  )
}

// Provider marks. Inlined rather than pulled from a CDN so the login page has
// no external dependency, and so they render before any network round trip.
function GoogleMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 18 18" aria-hidden="true">
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"/>
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z"/>
      <path fill="#FBBC05" d="M3.97 10.72a5.41 5.41 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z"/>
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.9 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"/>
    </svg>
  )
}

function AppleMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 384 512" aria-hidden="true" fill="#f1f5f9">
      <path d="M318.7 268.7c-.2-36.7 16.4-64.4 50-84.8-18.8-26.9-47.2-41.7-84.7-44.6-35.5-2.8-74.3 20.7-88.5 20.7-15 0-49.4-19.7-76.4-19.7C63.3 141.2 4 184.8 4 273.5q0 39.3 14.4 81.2c12.8 36.7 59 126.7 107.2 125.2 25.2-.6 43-17.9 75.8-17.9 31.8 0 48.3 17.9 76.4 17.9 48.6-.7 90.4-82.5 102.6-119.3-65.2-30.7-61.7-90-61.7-91.9zm-56.6-164.2c27.3-32.4 24.8-61.9 24-72.5-24.1 1.4-52 16.4-67.9 34.9-17.5 19.8-27.8 44.3-25.6 71.9 26.1 2 49.9-11.4 69.5-34.3z"/>
    </svg>
  )
}

// Order here is the order they render. A provider only appears once it is
// actually enabled in the Supabase project.
const SOCIAL_PROVIDERS = [
  { id: 'google', label: 'Google', Mark: GoogleMark },
  { id: 'apple',  label: 'Apple',  Mark: AppleMark },
]

const providerRowStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
  marginBottom: 20,
}

const providerBtnStyle = (disabled) => ({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 10,
  width: '100%',
  background: '#0b1220',
  color: disabled ? '#475569' : '#f1f5f9',
  border: '1px solid #1e293b',
  borderRadius: 8,
  padding: '11px 0',
  fontSize: 14,
  fontWeight: 500,
  cursor: disabled ? 'default' : 'pointer',
  transition: 'border-color 0.15s, background 0.15s',
})

const dividerRowStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  marginBottom: 20,
}

const dividerLineStyle = {
  flex: 1,
  height: 1,
  background: '#1e293b',
}

const dividerTextStyle = {
  fontSize: 11,
  color: '#475569',
  textTransform: 'uppercase',
  letterSpacing: '0.1em',
}

const headingStyle = {
  margin: '0 0 8px',
  fontSize: 20,
  fontWeight: 600,
  color: '#f1f5f9',
  letterSpacing: '-0.01em',
}

const subheadStyle = {
  margin: '0 0 24px',
  fontSize: 14,
  color: '#475569',
  lineHeight: 1.5,
}

const tabRowStyle = {
  display: 'flex',
  gap: 4,
  background: '#080d18',
  border: '1px solid #1e293b',
  borderRadius: 8,
  padding: 4,
  marginBottom: 24,
}

const tabStyle = (active) => ({
  flex: 1,
  background: active ? '#1e293b' : 'transparent',
  color: active ? '#f1f5f9' : '#475569',
  border: 'none',
  borderRadius: 6,
  padding: '8px 0',
  fontSize: 13,
  fontWeight: 500,
  cursor: 'pointer',
  transition: 'background 0.15s, color 0.15s',
})

const labelStyle = {
  display: 'block',
  fontSize: 12,
  fontWeight: 500,
  color: '#475569',
  letterSpacing: '0.05em',
  textTransform: 'uppercase',
  marginBottom: 8,
}

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  background: '#080d18',
  border: '1px solid #1e293b',
  borderRadius: 8,
  padding: '12px 14px',
  fontSize: 15,
  color: '#f1f5f9',
  marginBottom: 16,
  outline: 'none',
  transition: 'border-color 0.15s',
}

const btnStyle = (disabled) => ({
  width: '100%',
  background: disabled ? '#1e293b' : '#2563eb',
  color: disabled ? '#475569' : '#fff',
  border: 'none',
  borderRadius: 8,
  padding: '13px 0',
  fontSize: 14,
  fontWeight: 600,
  cursor: disabled ? 'not-allowed' : 'pointer',
  letterSpacing: '0.01em',
  transition: 'background 0.15s',
})

const linkBtnStyle = {
  marginTop: 8,
  width: '100%',
  background: 'none',
  border: 'none',
  color: '#334155',
  fontSize: 13,
  padding: '6px 0',
  cursor: 'pointer',
}

const fineprintStyle = {
  margin: '20px 0 0',
  fontSize: 11,
  color: '#334155',
  textAlign: 'center',
  lineHeight: 1.5,
}
