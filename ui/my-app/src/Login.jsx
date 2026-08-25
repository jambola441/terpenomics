import { useEffect, useState } from 'react'
import supabase from './utils/supabase'
import { useNavigate } from 'react-router-dom'
import { toE164, formatPhoneInput, formatE164ForDisplay } from './utils/phone'

// Supabase enforces a 60s window between OTP requests for the same recipient.
const RESEND_SECONDS = 60

export default function Login() {
  const [channel, setChannel] = useState('sms') // 'sms' | 'email'
  const [step, setStep]       = useState('send')
  const [phone, setPhone]     = useState('')
  const [email, setEmail]     = useState('')
  const [sentTo, setSentTo]   = useState('')   // E.164 or email actually used for the send
  const [code, setCode]       = useState('')
  const [msg, setMsg]         = useState('')
  const [loading, setLoading] = useState(false)
  const [isError, setIsError] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const navigate = useNavigate()

  useEffect(() => {
    if (cooldown <= 0) return
    const t = setTimeout(() => setCooldown(c => c - 1), 1000)
    return () => clearTimeout(t)
  }, [cooldown])

  function switchChannel(next) {
    setChannel(next)
    setStep('send')
    setCode('')
    setMsg('')
    setIsError(false)
  }

  function fail(message) {
    setIsError(true)
    setMsg(message)
  }

  async function requestCode(destination) {
    if (channel === 'sms') {
      return supabase.auth.signInWithOtp({
        phone: destination,
        options: { shouldCreateUser: true, channel: 'sms' },
      })
    }
    return supabase.auth.signInWithOtp({
      email: destination,
      options: { shouldCreateUser: true },
    })
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
    const { error } = await requestCode(destination)
    setLoading(false)

    if (error) return fail(explainError(error, channel))

    setSentTo(destination)
    setStep('verify')
    setCooldown(RESEND_SECONDS)
    setMsg(channel === 'sms' ? 'Code sent by text.' : 'Check your email for a 6-digit code.')
  }

  async function resendCode() {
    if (cooldown > 0 || loading || !sentTo) return
    setMsg('')
    setIsError(false)
    setLoading(true)
    const { error } = await requestCode(sentTo)
    setLoading(false)
    if (error) return fail(explainError(error, channel))
    setCooldown(RESEND_SECONDS)
    setMsg('New code sent.')
  }

  async function verifyCode(e) {
    e.preventDefault()
    setLoading(true)
    setMsg('')
    setIsError(false)

    const { data, error } =
      channel === 'sms'
        ? await supabase.auth.verifyOtp({ phone: sentTo, token: code, type: 'sms' })
        : await supabase.auth.verifyOtp({ email: sentTo, token: code, type: 'email' })

    setLoading(false)
    if (error) return fail(error.message)

    // Admins carry role="admin" on the Supabase JWT (see routes/admin/auth.py).
    // Everyone else who signs in by text lands in the customer portal.
    const isAdmin = data?.user?.role === 'admin'
    navigate(isAdmin || channel === 'email' ? '/admin' : '/portal')
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

function explainError(error, channel) {
  const raw = error?.message || 'Something went wrong.'
  if (channel === 'sms' && /provider|not enabled|unsupported phone/i.test(raw)) {
    return `${raw} — check that Phone auth is enabled in the Supabase dashboard.`
  }
  return raw
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
