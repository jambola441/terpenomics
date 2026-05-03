import { useState } from 'react'
import supabase from './utils/supabase'
import { useNavigate } from 'react-router-dom'

export default function Login() {
  const [step, setStep]       = useState('send')
  const [email, setEmail]     = useState('')
  const [code, setCode]       = useState('')
  const [msg, setMsg]         = useState('')
  const [loading, setLoading] = useState(false)
  const [isError, setIsError] = useState(false)
  const navigate = useNavigate()

  async function sendCode(e) {
    e.preventDefault()
    setLoading(true)
    setMsg('')
    setIsError(false)

    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { shouldCreateUser: true },
    })

    setLoading(false)
    if (error) { setIsError(true); return setMsg(error.message) }
    setStep('verify')
    setMsg('Check your email for a 6-digit code.')
  }

  async function verifyCode(e) {
    e.preventDefault()
    setLoading(true)
    setMsg('')
    setIsError(false)

    const { error } = await supabase.auth.verifyOtp({ email, token: code, type: 'email' })

    setLoading(false)
    if (error) { setIsError(true); return setMsg(error.message) }
    navigate('/admin')
  }

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
            <h2 style={{ margin: '0 0 8px', fontSize: 20, fontWeight: 600, color: '#f1f5f9', letterSpacing: '-0.01em' }}>
              Sign in
            </h2>
            <p style={{ margin: '0 0 28px', fontSize: 14, color: '#475569', lineHeight: 1.5 }}>
              Enter your email and we'll send a one-time code.
            </p>
            <form onSubmit={sendCode}>
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
              <button type="submit" disabled={loading} style={btnStyle(loading)}>
                {loading ? 'Sending…' : 'Send code'}
              </button>
            </form>
          </>
        ) : (
          <>
            <h2 style={{ margin: '0 0 8px', fontSize: 20, fontWeight: 600, color: '#f1f5f9', letterSpacing: '-0.01em' }}>
              Check your email
            </h2>
            <p style={{ margin: '0 0 28px', fontSize: 14, color: '#475569', lineHeight: 1.5 }}>
              We sent a 6-digit code to{' '}
              <span style={{ color: '#94a3b8', fontWeight: 500 }}>{email}</span>
            </p>
            <form onSubmit={verifyCode}>
              <label style={labelStyle}>Code</label>
              <input
                value={code}
                onChange={e => setCode(e.target.value)}
                placeholder="000000"
                inputMode="numeric"
                pattern="[0-9]*"
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
              onClick={() => { setStep('send'); setMsg(''); setIsError(false) }}
              style={{
                marginTop: 16,
                width: '100%',
                background: 'none',
                border: 'none',
                color: '#334155',
                fontSize: 13,
                cursor: 'pointer',
                padding: '6px 0',
                transition: 'color 0.15s',
              }}
              onMouseEnter={e => e.target.style.color = '#64748b'}
              onMouseLeave={e => e.target.style.color = '#334155'}
            >
              ← Use a different email
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

const btnStyle = (loading) => ({
  width: '100%',
  background: loading ? '#1e293b' : '#2563eb',
  color: loading ? '#475569' : '#fff',
  border: 'none',
  borderRadius: 8,
  padding: '13px 0',
  fontSize: 14,
  fontWeight: 600,
  cursor: loading ? 'not-allowed' : 'pointer',
  letterSpacing: '0.01em',
  transition: 'background 0.15s',
})
