import { useEffect, useState } from 'react'
import supabase from './utils/supabase'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { toE164, formatPhoneInput, formatE164ForDisplay } from './utils/phone'
import api from './api/client'
import { safeNext, rememberNext } from './utils/redirect'
import { t, font, radius } from './theme'
import { Icon, Logo } from './components/Icon'

// Fallback cooldown. The SMS path uses whatever the backend reports instead.
const RESEND_SECONDS = 60
/** A texted code's length when the API doesn't say (routes/auth_sms.py,
 *  SMS_OTP_LENGTH). An emailed code's length is a Supabase project setting
 *  (6-10) the page can't read, so that field takes up to the most and
 *  doesn't submit by itself. */
const DEFAULT_CODE_LENGTH = 6
const MAX_CODE_LENGTH = 10
// How long an email code is offered back after a reload; Supabase's own
// expiry decides whether it still works.
const EMAIL_CODE_SECONDS = 600

/*
 * A sent code, kept in sessionStorage until it expires. Every text costs
 * money, and a reload, or iOS discarding the tab while the shopper reads the
 * message, used to drop the code step and the resend cooldown with it, so the
 * only way on was to send another. Session storage is per tab and gone when
 * the tab closes, which is about how long a code is worth keeping.
 *
 *   { channel, sentTo, challengeId, expiresAt, cooldownUntil }  (times in ms)
 */
const pendingKey = audience => `terpee:signin:${audience}`

function readPending(audience) {
  try {
    const saved = JSON.parse(sessionStorage.getItem(pendingKey(audience)) ?? 'null')
    return saved && saved.expiresAt > Date.now() ? saved : null
  } catch {
    return null
  }
}

function writePending(audience, pending) {
  try {
    if (pending) sessionStorage.setItem(pendingKey(audience), JSON.stringify(pending))
    else sessionStorage.removeItem(pendingKey(audience))
  } catch {
    // Storage blocked: the flow still works, it just won't survive a reload.
  }
}

/**
 * Two sign-in pages share this flow.
 *
 *   /        Customers. A mobile number and nothing else: the phone is what
 *            points and order matching key on, so it is the only way in, even
 *            while Google, Apple or email are switched on in Supabase for staff.
 *   /staff   Staff. Whatever social providers Supabase has enabled, a work
 *            email code, and a text code (ADMIN_PHONES admins sign in by text).
 */
export default function Login() {
  return <SignIn audience="customer" />
}

export function StaffLogin() {
  return <SignIn audience="staff" />
}

function SignIn({ audience }) {
  const staff = audience === 'staff'
  // A code sent before a reload picks up where it left off.
  const [restored] = useState(() => readPending(audience))
  const [channel, setChannel] = useState(restored?.channel ?? 'sms') // 'sms' | 'email' — email is staff-only
  const [step, setStep]       = useState(restored ? 'verify' : 'send')
  const [phone, setPhone]     = useState(restored?.channel === 'sms' ? formatE164ForDisplay(restored.sentTo) : '')
  const [email, setEmail]     = useState(restored?.channel === 'email' ? restored.sentTo : '')
  const [sentTo, setSentTo]   = useState(restored?.sentTo ?? '')   // E.164 or email actually used for the send
  const [challengeId, setChallengeId] = useState(restored?.challengeId ?? '')  // backend handle for the SMS code
  const [code, setCode]       = useState('')
  // How long the code is, when known (texted codes); the field stops there
  // and submits by itself.
  const [codeLength, setCodeLength] = useState(restored?.codeLength ?? (restored?.channel === 'email' ? null : DEFAULT_CODE_LENGTH))
  const [msg, setMsg]         = useState(restored ? (restored.channel === 'sms' ? 'Code sent by text.' : 'Check your email for the code.') : '')
  const [loading, setLoading] = useState(false)
  const [isError, setIsError] = useState(false)
  // When a resend is next allowed, as a time rather than a countdown, so it
  // survives a reload and stays tied to the number it was for.
  const [cooldownUntil, setCooldownUntil] = useState(restored?.cooldownUntil ?? 0)
  const [now, setNow] = useState(() => Date.now())
  const cooldown = Math.max(0, Math.ceil((cooldownUntil - now) / 1000))
  const [providers, setProviders] = useState([])  // OAuth providers actually enabled
  // Null until we know whether this browser already has a session.
  const [signedIn, setSignedIn] = useState(null)
  const navigate = useNavigate()
  const location = useLocation()
  // Where the visitor was headed before being bounced here, if anywhere.
  const next = safeNext(location.state?.from)
  const home = staff ? '/admin' : '/portal'

  // Already signed in: go on to where they were headed rather than offering a
  // form that would send another text. getSession() refreshes an expired
  // access token from the stored refresh token, so a long-idle visitor still
  // counts as signed in; it only comes back empty when that refresh fails.
  useEffect(() => {
    let cancelled = false
    supabase.auth.getSession()
      .then(({ data }) => {
        if (cancelled) return
        if (data?.session) navigate(next || home, { replace: true })
        else setSignedIn(false)
      })
      .catch(() => { if (!cancelled) setSignedIn(false) })
    return () => { cancelled = true }
  }, [navigate, next, home])

  // Ask Supabase which social providers are live rather than hardcoding them.
  // signInWithOAuth redirects the browser instead of making a request, so a
  // disabled provider would dump the user on a raw JSON error page. Rendering
  // only what is enabled means turning one on in the Supabase dashboard makes
  // the button appear with no code change, and nothing is clickable before then.
  useEffect(() => {
    // Customers never see a provider button, whatever Supabase has enabled.
    if (!staff) return
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
  }, [staff])

  useEffect(() => {
    if (cooldownUntil <= now) return
    const timer = setTimeout(() => setNow(Date.now()), 1000)
    return () => clearTimeout(timer)
  }, [cooldownUntil, now])

  /** Start the resend clock for this destination, and remember both. */
  function startCooldown(seconds, pending) {
    const until = Date.now() + seconds * 1000
    setNow(Date.now())
    setCooldownUntil(until)
    if (pending) writePending(audience, { ...pending, cooldownUntil: until })
  }

  function switchChannel(next) {
    setChannel(next)
    setStep('send')
    setCode('')
    setChallengeId('')
    setMsg('')
    setIsError(false)
    setCooldownUntil(0)
    writePending(audience, null)
  }

  function fail(message) {
    setIsError(true)
    setMsg(message)
  }

  function handleFailure(err) {
    // A 429 carries Retry-After; mirror it in the UI so the button reflects the
    // server's actual cooldown rather than our guess at it.
    if (err?.status === 429 && err.retryAfter) startCooldown(err.retryAfter, readPending(audience))
    fail(err?.message || 'Something went wrong. Try again.')
  }

  /**
   * Request a code. Returns the challenge (SMS only), how many seconds until a
   * resend is allowed, and how long the code stays valid.
   *
   * The two channels take different routes: email OTP is Supabase's own, while
   * SMS goes through our backend, which drives the SMS provider and hands back
   * a Supabase session only once the provider has validated the code.
   */
  async function requestCode(destination) {
    if (channel === 'sms') {
      const { challenge_id, resend_in, expires_in, code_length } = await api.auth.smsStart(destination)
      setChallengeId(challenge_id)
      return {
        challengeId: challenge_id, wait: resend_in || RESEND_SECONDS, valid: expires_in || RESEND_SECONDS * 5,
        length: code_length || DEFAULT_CODE_LENGTH,
      }
    }

    // Email is for staff accounts that already exist. Customers sign up by
    // phone, which is what points and order matching key on, so an unknown
    // address gets no account here.
    const { error } = await supabase.auth.signInWithOtp({
      email: destination,
      options: { shouldCreateUser: false },
    })
    if (error) {
      if (/signups? not allowed|not found|user not found/i.test(error.message)) {
        throw new Error('No staff account uses that email.')
      }
      throw new Error(error.message)
    }
    return { challengeId: '', wait: RESEND_SECONDS, valid: EMAIL_CODE_SECONDS, length: null }
  }

  /** Record a sent code so a reload lands back on the code step. */
  function rememberSent(destination, sent) {
    const pending = {
      channel,
      sentTo: destination,
      challengeId: sent.challengeId,
      codeLength: sent.length,
      expiresAt: Date.now() + sent.valid * 1000,
      cooldownUntil: 0,
    }
    setCodeLength(sent.length)
    startCooldown(sent.wait, pending)
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

    // Back on the send step with the same number while its code is still
    // good and the resend clock still running: go back to that code rather
    // than texting again. ("Use a different number" used to be a way round the
    // cooldown.)
    const pending = readPending(audience)
    if (pending && pending.channel === channel && pending.sentTo === destination && pending.cooldownUntil > Date.now()) {
      setSentTo(pending.sentTo)
      setChallengeId(pending.challengeId)
      setCodeLength(pending.codeLength ?? (pending.channel === 'email' ? null : DEFAULT_CODE_LENGTH))
      setCooldownUntil(pending.cooldownUntil)
      setNow(Date.now())
      setStep('verify')
      setMsg(channel === 'sms' ? 'We already texted a code to this number. Enter it below.' : 'We already emailed a code to this address. Enter it below.')
      return
    }

    setLoading(true)
    try {
      const sent = await requestCode(destination)
      setSentTo(destination)
      setStep('verify')
      rememberSent(destination, sent)
      setMsg(channel === 'sms' ? 'Code sent by text.' : 'Check your email for the code.')
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
      rememberSent(sentTo, await requestCode(sentTo))
      setMsg('New code sent.')
    } catch (err) {
      handleFailure(err)
    } finally {
      setLoading(false)
    }
  }

  const codeComplete = code.length >= (codeLength ?? DEFAULT_CODE_LENGTH)

  function verifyCode(e) {
    e.preventDefault()
    if (codeComplete && !loading) submitCode(code)
  }

  /** The field submits by itself once the code is complete, including when
   *  the phone fills it from the text. */
  function enterCode(value) {
    const digits = value.replace(/\D/g, '').slice(0, codeLength ?? MAX_CODE_LENGTH)
    setCode(digits)
    if (codeLength && digits.length === codeLength && !loading) submitCode(digits)
  }

  async function submitCode(entered) {
    setLoading(true)
    setMsg('')
    setIsError(false)

    try {
      if (channel === 'sms') {
        const session = await api.auth.smsVerify(challengeId, entered)
        const { error } = await supabase.auth.setSession({
          access_token: session.access_token,
          refresh_token: session.refresh_token,
        })
        if (error) throw new Error(error.message)
      } else {
        const { error } = await supabase.auth.verifyOtp({
          email: sentTo,
          token: entered,
          type: 'email',
        })
        if (error) throw new Error(error.message)
      }

      writePending(audience, null)
      // Each page lands where its audience works, unless the visitor was
      // bounced here from somewhere specific. Whether a staff sign-in may see
      // /admin is the API's call (routes/admin/auth.py), not this page's.
      navigate(next || home)
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
    // The provider round trip discards router state, so hand the destination
    // to sessionStorage for AuthCallback to pick up. Only staff get here.
    rememberNext(next || home)
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

  // Hold the page blank for the moment the session check takes, so a signed-in
  // visitor never sees the form flash before being sent on.
  if (signedIn === null) return <div style={{ minHeight: '100vh', background: t.bg }} />

  return (
    <main style={{
      minHeight: '100vh',
      background: t.bg,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '40px 16px',
    }}>
      {/* Card */}
      <div style={{
        width: '100%',
        maxWidth: 400,
        background: t.surface1,
        border: `1px solid ${t.border}`,
        borderRadius: radius.xl,
        padding: '36px 32px',
      }}>
        <div style={{ marginBottom: 28, display: 'flex', alignItems: 'center', gap: 12 }}>
          <Logo size={30} />
          {staff && <span style={staffTagStyle}>Staff</span>}
        </div>

        {step === 'send' ? (
          <>
            <h1 style={headingStyle}>{staff ? 'Staff sign-in' : 'Sign in'}</h1>
            <p style={subheadStyle}>
              {channel === 'sms'
                ? "Enter your mobile number and we'll text you a one-time code."
                : "Enter your work email and we'll send a one-time code."}
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

            {staff && (
              <div style={tabRowStyle}>
                <button type="button" onClick={() => switchChannel('sms')} style={tabStyle(channel === 'sms')}>
                  Text message
                </button>
                <button type="button" onClick={() => switchChannel('email')} style={tabStyle(channel === 'email')}>
                  Work email
                </button>
              </div>
            )}

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
            <h1 style={headingStyle}>
              {channel === 'sms' ? 'Check your texts' : 'Check your email'}
            </h1>
            <p style={subheadStyle}>
              We sent a {codeLength ? `${codeLength}-digit ` : ''}code to{' '}
              <span style={{ color: t.text1, fontWeight: 500 }}>
                {channel === 'sms' ? formatE164ForDisplay(sentTo) : sentTo}
              </span>
            </p>
            <form onSubmit={verifyCode}>
              <label style={labelStyle}>Code</label>
              <input
                value={code}
                onChange={e => enterCode(e.target.value)}
                placeholder={'0'.repeat(codeLength ?? DEFAULT_CODE_LENGTH)}
                inputMode="numeric"
                pattern="[0-9]*"
                autoComplete="one-time-code"
                maxLength={codeLength ?? MAX_CODE_LENGTH}
                aria-label={codeLength ? `${codeLength}-digit code` : 'Code'}
                autoFocus
                required
                data-large
                style={{ ...inputStyle, letterSpacing: '0.3em', fontSize: 22, textAlign: 'center' }}
              />
              <button type="submit" disabled={loading || !codeComplete} style={btnStyle(loading || !codeComplete)}>
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
              <Icon name="arrow-left" size={14} />
              Use a different {channel === 'sms' ? 'number' : 'email'}
            </button>
          </>
        )}

        {msg && (
          <p style={{
            marginTop: 20,
            marginBottom: 0,
            fontSize: 13,
            color: isError ? t.danger : t.success,
            textAlign: 'center',
            lineHeight: 1.5,
          }}>
            {msg}
          </p>
        )}

        <p style={{ marginTop: 24, marginBottom: 0, fontSize: 12, color: t.text3, textAlign: 'center' }}>
          <Link to="/terms" style={{ color: 'inherit' }}>Terms</Link>
          {' · '}
          <Link to="/privacy" style={{ color: 'inherit' }}>Privacy</Link>
        </p>
      </div>
    </main>
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
    <svg width="16" height="16" viewBox="0 0 384 512" aria-hidden="true" fill="currentColor">
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
  background: t.surface2,
  color: disabled ? t.text4 : t.text1,
  border: `1px solid ${t.borderStrong}`,
  borderRadius: 10,
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
  background: t.border,
}

const dividerTextStyle = {
  fontFamily: font.family.mono,
  fontSize: 11,
  fontWeight: 500,
  color: t.text3,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
}

const staffTagStyle = {
  fontFamily: font.family.mono,
  fontSize: 11,
  fontWeight: 500,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: t.text2,
  border: `1px solid ${t.borderStrong}`,
  borderRadius: radius.pill,
  padding: '3px 9px',
}

const headingStyle = {
  margin: '0 0 8px',
  fontFamily: font.family.display,
  fontSize: font.size.display,
  fontWeight: 600,
  color: t.text1,
  letterSpacing: '-0.015em',
}

const subheadStyle = {
  margin: '0 0 24px',
  fontSize: 14,
  color: t.text2,
  lineHeight: 1.5,
}

const tabRowStyle = {
  display: 'flex',
  gap: 4,
  background: t.bg,
  border: `1px solid ${t.border}`,
  borderRadius: 10,
  padding: 4,
  marginBottom: 24,
}

const tabStyle = (active) => ({
  flex: 1,
  background: active ? t.surface3 : 'transparent',
  color: active ? t.text1 : t.text3,
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
  fontFamily: font.family.mono,
  fontSize: 11,
  fontWeight: 500,
  color: t.text3,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  marginBottom: 8,
}

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  background: t.surface2,
  border: `1px solid ${t.border}`,
  borderRadius: 10,
  padding: '12px 14px',
  fontSize: 15,
  color: t.text1,
  marginBottom: 16,
  outline: 'none',
  transition: 'border-color 0.15s',
}

const btnStyle = (disabled) => ({
  width: '100%',
  background: disabled ? t.surface2 : t.accent,
  color: disabled ? t.text4 : t.accentInk,
  border: 'none',
  borderRadius: 10,
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
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 6,
  background: 'none',
  border: 'none',
  color: t.text3,
  fontSize: 13,
  // 44px to tap, though it reads as a line of text.
  minHeight: 44,
  padding: '6px 0',
  cursor: 'pointer',
}

const fineprintStyle = {
  margin: '20px 0 0',
  fontSize: 11,
  color: t.text3,
  textAlign: 'center',
  lineHeight: 1.5,
}
