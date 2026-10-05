/* ============================================================================
   EmailEditor — add, change or remove the contact email on the profile.

   The address is saved only after the customer enters the code sent to it
   (routes/me_email.py), so nobody can put someone else's email on their
   account. Email is contact only; sign-in stays by phone.
   ========================================================================== */

import { useEffect, useState } from 'react'
import api from '../api/client'
import type { CustomerProfile } from '../types'
import { t, radius, font } from '../theme'

type Step = 'view' | 'enter' | 'code'

export default function EmailEditor({ profile, onSaved }: {
  profile: CustomerProfile
  onSaved: (profile: CustomerProfile) => void
}) {
  const [step, setStep] = useState<Step>('view')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [challengeId, setChallengeId] = useState<string | null>(null)
  const [resendIn, setResendIn] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (resendIn <= 0) return
    const id = setTimeout(() => setResendIn(s => s - 1), 1000)
    return () => clearTimeout(id)
  }, [resendIn])

  async function run(fn: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Something went wrong. Try again.')
    } finally {
      setBusy(false)
    }
  }

  const sendCode = () => run(async () => {
    const res = await api.me.startEmailChange(email.trim())
    setChallengeId(res.challenge_id)
    setResendIn(res.resend_in)
    setCode('')
    setStep('code')
  })

  const verify = () => run(async () => {
    if (!challengeId) return
    onSaved(await api.me.verifyEmailChange(challengeId, code))
    setStep('view')
  })

  const remove = () => {
    if (!confirm('Remove your email from your account?')) return
    run(async () => onSaved(await api.me.removeEmail()))
  }

  const cancel = () => {
    setStep('view')
    setError(null)
  }

  return (
    <div style={{
      background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg, padding: '12px 14px',
      display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <span style={{ color: t.text3, fontSize: font.size.small }}>Email</span>
        {step === 'view' && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
            <span style={{
              color: profile.email ? t.text2 : t.text4, fontSize: font.size.small,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            }}>
              {profile.email ?? 'None'}
            </span>
            <LinkButton onClick={() => { setEmail(''); setStep('enter') }}>
              {profile.email ? 'Change' : 'Add'}
            </LinkButton>
            {profile.email && <LinkButton onClick={remove} disabled={busy}>Remove</LinkButton>}
          </span>
        )}
      </div>

      {step === 'enter' && (
        <form onSubmit={e => { e.preventDefault(); sendCode() }} style={rowStyle}>
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
          <button type="submit" disabled={busy || !email.trim()} style={buttonStyle(busy || !email.trim())}>
            {busy ? 'Sending…' : 'Send code'}
          </button>
          <LinkButton onClick={cancel}>Cancel</LinkButton>
        </form>
      )}

      {step === 'code' && (
        <>
          <div style={{ color: t.text3, fontSize: font.size.small }}>
            Enter the 6-digit code we sent to <b style={{ color: t.text2 }}>{email.trim()}</b>.
          </div>
          <form onSubmit={e => { e.preventDefault(); verify() }} style={rowStyle}>
            <input
              value={code}
              onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="123456"
              autoFocus
              style={{ ...inputStyle, letterSpacing: 4 }}
            />
            <button type="submit" disabled={busy || code.length !== 6} style={buttonStyle(busy || code.length !== 6)}>
              {busy ? 'Checking…' : 'Verify'}
            </button>
          </form>
          <div style={{ display: 'flex', gap: 16 }}>
            <LinkButton onClick={sendCode} disabled={busy || resendIn > 0}>
              {resendIn > 0 ? `Resend in ${resendIn}s` : 'Resend code'}
            </LinkButton>
            <LinkButton onClick={() => setStep('enter')}>Use a different email</LinkButton>
            <LinkButton onClick={cancel}>Cancel</LinkButton>
          </div>
        </>
      )}

      {error && <div role="alert" style={{ color: t.danger, fontSize: font.size.small }}>{error}</div>}
    </div>
  )
}

function LinkButton({ onClick, disabled, children }: {
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        background: 'none', border: 'none', padding: 0, flexShrink: 0,
        color: disabled ? t.text4 : t.accent, fontSize: font.size.small,
        cursor: disabled ? 'default' : 'pointer',
      }}
    >
      {children}
    </button>
  )
}

const rowStyle = { display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' } as const

const inputStyle = {
  flex: '1 1 180px', minWidth: 0, boxSizing: 'border-box', background: t.surface2,
  border: `1px solid ${t.border}`, borderRadius: radius.md, color: t.text1,
  fontSize: font.size.body, padding: '10px 12px', outline: 'none',
} as const

function buttonStyle(disabled: boolean) {
  return {
    padding: '10px 14px', borderRadius: radius.md, border: 'none', flexShrink: 0,
    background: disabled ? t.surface3 : t.accent, color: disabled ? t.text3 : t.accentInk,
    fontSize: font.size.small, fontWeight: font.weight.bold, cursor: disabled ? 'default' : 'pointer',
  } as const
}
