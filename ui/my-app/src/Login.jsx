// src/Login.jsx
import { useState } from 'react'
import supabase from './utils/supabase'
import { useNavigate } from 'react-router-dom'

export default function Login() {
  const [step, setStep] = useState('send') // 'send' | 'verify'
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [msg, setMsg] = useState('')
  const navigate = useNavigate()

  async function sendCode(e) {
    e.preventDefault()
    setMsg('')

    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        // Do NOT set emailRedirectTo; we want code entry, not magic link.
        shouldCreateUser: true,
      },
    })

    if (error) return setMsg(error.message)

    setStep('verify')
    setMsg('Check your email for a 6-digit code.')
  }

  async function verifyCode(e) {
    e.preventDefault()
    setMsg('')

    const { data, error } = await supabase.auth.verifyOtp({
      email,
      token: code,
      type: 'email',
    })

    if (error) return setMsg(error.message)

    // data.session.access_token is now available for backend calls
    navigate('/app')
  }

  return (
    <div style={{ padding: 40, maxWidth: 420 }}>
      <h1>Login</h1>

      {step === 'send' ? (
        <form onSubmit={sendCode}>
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            required
          />
          <button type="submit">Send code</button>
        </form>
      ) : (
        <form onSubmit={verifyCode}>
          <div style={{ marginBottom: 10 }}>Sent to {email}</div>
          <input
            value={code}
            onChange={e => setCode(e.target.value)}
            placeholder="12345678"
            inputMode="numeric"
            pattern="[0-9]{8}"
            maxLength={8}
            required
          />
          <button type="submit">Verify</button>
          <button type="button" onClick={() => setStep('send')} style={{ marginLeft: 8 }}>
            Change email
          </button>
        </form>
      )}

      {msg && <p>{msg}</p>}
    </div>
  )
}
