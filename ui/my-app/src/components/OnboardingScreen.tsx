/* ============================================================================
   OnboardingScreen — sign-up, between first login and the portal.

   Shown whenever /me reports onboarding incomplete: a new customer, a row from
   before sign-up existed, or anyone after a terms change. Every disclosure on
   it comes from the server, and its version is sent back with the answers, so
   what gets recorded is what was on screen (services/consent.py). The mobile
   twin is mobile/src/app/sign-up.tsx.
   ========================================================================== */

import { useState, type ReactNode } from 'react'
import api from '../api/client'
import type { CustomerProfile } from '../types'
import { t, radius, font } from '../theme'
import { Logo } from './Icon'

export default function OnboardingScreen({ profile, onDone, onSignOut }: {
  profile: CustomerProfile
  onDone: (profile: CustomerProfile) => void
  onSignOut: () => void
}) {
  const { onboarding } = profile
  const { disclosures } = onboarding

  const [first, setFirst] = useState(profile.first_name ?? onboarding.prefill.first_name ?? '')
  const [last, setLast] = useState(profile.last_name ?? onboarding.prefill.last_name ?? '')
  const [age, setAge] = useState(false)
  const [terms, setTerms] = useState(false)
  // Off unless they turn it on; anyone already opted in sees their choice.
  const [marketing, setMarketing] = useState(profile.marketing_opt_in)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const returning = !onboarding.missing.includes('first_name') && !onboarding.missing.includes('age_21')
  const ready = first.trim().length > 0 && age && terms

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!ready) return
    setSaving(true)
    setError(null)
    try {
      onDone(await api.me.completeOnboarding({
        first_name: first.trim(),
        last_name: last.trim() || null,
        age_21: age,
        terms_version: disclosures.terms.version,
        marketing_sms_opt_in: marketing,
        marketing_sms_version: marketing ? disclosures.marketing_sms.version : null,
        platform: 'web',
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  return (
    <div style={{
      minHeight: '100dvh', background: t.bg, display: 'flex', justifyContent: 'center',
      padding: '48px 16px', boxSizing: 'border-box',
    }}>
      <form onSubmit={submit} style={{ width: '100%', maxWidth: 420, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <Logo size={26} style={{ marginBottom: 12 }} />
        <div>
          <h1 style={{ color: t.text1, fontFamily: font.family.display, fontSize: font.size.hero, fontWeight: font.weight.semibold, margin: 0, letterSpacing: '-0.02em', lineHeight: 1.1 }}>
            {returning ? 'We updated our terms' : 'Finish signing up'}
          </h1>
          <p style={{ color: t.text2, fontSize: font.size.body, lineHeight: 1.55, margin: '8px 0 0' }}>
            {returning
              ? 'Please review and accept them to keep ordering.'
              : 'A few details before you can reserve products for pickup.'}
          </p>
        </div>

        <div style={{ display: 'flex', gap: 12 }}>
          <Field label="First name">
            <input
              value={first}
              onChange={e => setFirst(e.target.value)}
              autoComplete="given-name"
              maxLength={100}
              required
              style={inputStyle}
            />
          </Field>
          <Field label="Last name">
            <input
              value={last}
              onChange={e => setLast(e.target.value)}
              autoComplete="family-name"
              maxLength={100}
              placeholder="Optional"
              style={inputStyle}
            />
          </Field>
        </div>

        <Check checked={age} onChange={setAge}>{disclosures.age_21.text}</Check>
        <Check checked={terms} onChange={setTerms}>
          I agree to the <DocLink url={disclosures.terms.terms_url}>Terms of Service</DocLink>
          {' '}and <DocLink url={disclosures.terms.privacy_url}>Privacy Policy</DocLink>.
        </Check>
        <Check checked={marketing} onChange={setMarketing}>
          <strong style={{ fontWeight: font.weight.semibold }}>Optional: </strong>
          {disclosures.marketing_sms.text}
        </Check>

        {error && <div role="alert" style={{ color: t.danger, fontSize: font.size.body }}>{error}</div>}

        <button
          type="submit"
          disabled={!ready || saving}
          style={{
            marginTop: 8, padding: '14px 18px', borderRadius: radius.md, border: 'none',
            background: ready ? t.accent : t.surface2, color: ready ? t.accentInk : t.text4,
            fontSize: font.size.callout, fontWeight: font.weight.bold,
            cursor: ready && !saving ? 'pointer' : 'default', opacity: saving ? 0.7 : 1,
          }}
        >
          {saving ? 'Saving…' : 'Continue'}
        </button>
        <button
          type="button"
          onClick={onSignOut}
          style={{
            background: 'none', border: 'none', color: t.text3, fontSize: font.size.small,
            cursor: 'pointer', padding: 8,
          }}
        >
          Sign out
        </button>
      </form>
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ color: t.text2, fontSize: font.size.small }}>{label}</span>
      {children}
    </label>
  )
}

function Check({ checked, onChange, children }: {
  checked: boolean
  onChange: (v: boolean) => void
  children: ReactNode
}) {
  return (
    <label style={{
      display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer',
      background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg, padding: 14,
    }}>
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
        style={{ width: 18, height: 18, marginTop: 1, accentColor: 'var(--accent)', flexShrink: 0 }}
      />
      <span style={{ color: t.text1, fontSize: font.size.body, lineHeight: 1.5 }}>{children}</span>
    </label>
  )
}

function DocLink({ url, children }: { url: string | null; children: ReactNode }) {
  if (!url) return <>{children}</>
  return (
    <a href={url} target="_blank" rel="noreferrer" style={{ color: t.accent }} onClick={e => e.stopPropagation()}>
      {children}
    </a>
  )
}

const inputStyle = {
  width: '100%', boxSizing: 'border-box', background: t.surface2, border: `1px solid ${t.border}`,
  borderRadius: radius.md, color: t.text1, fontSize: font.size.body, padding: '12px 14px', outline: 'none',
} as const
