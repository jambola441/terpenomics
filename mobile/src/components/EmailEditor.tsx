import { useEffect, useState } from 'react'
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native'
import type { CustomerProfile } from '@web/types'
import { api } from '@/lib/api'
import { Button, styles } from '@/components/ui'
import { t, radius, space, font } from '@/lib/theme'

type Step = 'view' | 'enter' | 'code'

/** Add, change or remove the contact email. The address is saved only after
 *  the code sent to it is entered (routes/me_email.py). Twin of the web
 *  portal's components/EmailEditor.tsx. */
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

  function remove() {
    Alert.alert('Remove your email?', undefined, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: () => run(async () => onSaved(await api.me.removeEmail())) },
    ])
  }

  function cancel() {
    setStep('view')
    setError(null)
  }

  return (
    <View style={[styles.card, s.card]}>
      <View style={s.row}>
        <Text style={[styles.name, { flex: 1 }]}>Email</Text>
        {step === 'view' ? (
          <>
            <Link onPress={() => { setEmail(''); setStep('enter') }}>{profile.email ? 'Change' : 'Add'}</Link>
            {profile.email ? <Link onPress={remove} disabled={busy}>Remove</Link> : null}
          </>
        ) : (
          <Link onPress={cancel}>Cancel</Link>
        )}
      </View>

      {step === 'view' ? (
        <Text style={styles.meta}>{profile.email ?? 'Add an email to get receipts and account notices.'}</Text>
      ) : null}

      {step === 'enter' ? (
        <>
          <TextInput
            style={s.input}
            value={email}
            onChangeText={setEmail}
            placeholder="you@example.com"
            placeholderTextColor={t.text4}
            keyboardType="email-address"
            autoCapitalize="none"
            autoComplete="email"
            textContentType="emailAddress"
            autoFocus
          />
          <Button title="Send code" onPress={sendCode} disabled={!email.trim()} loading={busy} />
        </>
      ) : null}

      {step === 'code' ? (
        <>
          <Text style={styles.meta}>Enter the 6-digit code we sent to {email.trim()}.</Text>
          <TextInput
            style={[s.input, { letterSpacing: 6 }]}
            value={code}
            onChangeText={v => setCode(v.replace(/\D/g, '').slice(0, 6))}
            placeholder="123456"
            placeholderTextColor={t.text4}
            keyboardType="number-pad"
            autoComplete="one-time-code"
            textContentType="oneTimeCode"
            autoFocus
          />
          <Button title="Verify" onPress={verify} disabled={code.length !== 6} loading={busy} />
          <View style={[s.row, { gap: space[4] }]}>
            <Link onPress={sendCode} disabled={busy || resendIn > 0}>
              {resendIn > 0 ? `Resend in ${resendIn}s` : 'Resend code'}
            </Link>
            <Link onPress={() => setStep('enter')}>Different email</Link>
          </View>
        </>
      ) : null}

      {error ? <Text style={s.error}>{error}</Text> : null}
    </View>
  )
}

function Link({ onPress, disabled, children }: { onPress: () => void; disabled?: boolean; children: string }) {
  return (
    <Pressable onPress={onPress} disabled={disabled} hitSlop={8} style={{ marginLeft: space[3] }}>
      <Text style={{ color: disabled ? t.text4 : t.accent, fontSize: font.size.body }}>{children}</Text>
    </Pressable>
  )
}

const s = StyleSheet.create({
  card: { marginHorizontal: space[4], marginTop: space[3], padding: space[4], gap: space[2] },
  row: { flexDirection: 'row', alignItems: 'center' },
  input: {
    backgroundColor: t.surface2, borderRadius: radius.md, borderWidth: 1, borderColor: t.border,
    color: t.text1, fontSize: font.size.title, paddingHorizontal: space[3], minHeight: 46,
  },
  error: { color: t.danger, fontSize: font.size.body },
})
