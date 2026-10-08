import { useEffect, useState } from 'react'
import { KeyboardAvoidingView, Platform, Text, TextInput, View, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { api, ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { formatE164ForDisplay, formatPhoneInput, toE164 } from '@/lib/phone'
import { Button, Label, styles } from '@/components/ui'
import { Icon, Logo } from '@/components/Icon'
import { t, space, font, fonts, type } from '@/lib/theme'

/** A texted code's length when the API doesn't say (SMS_OTP_LENGTH). */
const DEFAULT_CODE_LENGTH = 6

/** Phone number, then the code. Mirrors the SMS half of the web Login page. */
export default function SignIn() {
  const { signInWithSms } = useAuth()
  const [phone, setPhone] = useState('')
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [challengeId, setChallengeId] = useState<string | null>(null)
  const [code, setCode] = useState('')
  // The field stops at the code's length and signs in by itself when it's full.
  const [codeLength, setCodeLength] = useState(DEFAULT_CODE_LENGTH)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The last code sent. It outlives "Change number", so going back to the same
  // number returns to that code instead of sending another text while the
  // resend clock is still running; that used to be a way round the cooldown.
  const [lastSent, setLastSent] = useState<{ to: string; challengeId: string; codeLength: number; resendAt: number } | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const resendIn = lastSent && lastSent.to === sentTo ? Math.max(0, Math.ceil((lastSent.resendAt - now) / 1000)) : 0

  useEffect(() => {
    if (!lastSent || lastSent.resendAt <= now) return
    const id = setTimeout(() => setNow(Date.now()), 1000)
    return () => clearTimeout(id)
  }, [lastSent, now])

  function fail(err: unknown) {
    if (err instanceof ApiError && err.retryAfter) {
      const resendAt = Date.now() + err.retryAfter * 1000
      setLastSent(prev => (prev ? { ...prev, resendAt } : prev))
      setNow(Date.now())
    }
    setError(err instanceof Error ? err.message : String(err))
  }

  async function sendCode() {
    const e164 = toE164(phone)
    if (!e164) {
      setError('Enter a 10-digit US phone number.')
      return
    }
    if (lastSent && lastSent.to === e164 && lastSent.resendAt > Date.now()) {
      setSentTo(e164)
      setChallengeId(lastSent.challengeId)
      setCodeLength(lastSent.codeLength)
      setCode('')
      setError(null)
      setNow(Date.now())
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await api.auth.smsStart(e164)
      const length = res.code_length || DEFAULT_CODE_LENGTH
      setChallengeId(res.challenge_id)
      setCodeLength(length)
      setSentTo(e164)
      setLastSent({ to: e164, challengeId: res.challenge_id, codeLength: length, resendAt: Date.now() + res.resend_in * 1000 })
      setNow(Date.now())
      setCode('')
    } catch (err) {
      fail(err)
    } finally {
      setLoading(false)
    }
  }

  function enterCode(value: string) {
    const digits = value.replace(/\D/g, '').slice(0, codeLength)
    setCode(digits)
    // Including when iOS fills it from the text.
    if (digits.length === codeLength && !loading) verify(digits)
  }

  async function verify(entered = code) {
    if (!challengeId) return
    setLoading(true)
    setError(null)
    try {
      // On success the auth listener flips the session and the router moves
      // us into the tabs, so there is nothing to navigate to here.
      await signInWithSms(challengeId, entered)
    } catch (err) {
      fail(err)
      setLoading(false)
    }
  }

  return (
    <SafeAreaView style={s.screen}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={s.body}>
        <Logo size={32} style={s.logo} />

        {sentTo === null ? (
          <>
            <Text style={type.display} accessibilityRole="header">Sign in</Text>
            <Label style={s.eyebrow}>Phone number</Label>
            <TextInput
              style={styles.input}
              value={phone}
              onChangeText={v => setPhone(formatPhoneInput(v))}
              placeholder="(555) 123-4567"
              placeholderTextColor={t.text4}
              keyboardType="phone-pad"
              textContentType="telephoneNumber"
              autoComplete="tel"
              autoFocus
            />
            <Button title="Text me a code" onPress={sendCode} loading={loading} disabled={!phone} />
          </>
        ) : (
          <>
            <Text style={type.display} accessibilityRole="header">Enter the code</Text>
            <Text style={type.copy}>We sent it to {formatE164ForDisplay(sentTo)}.</Text>
            <TextInput
              style={[styles.input, s.code]}
              value={code}
              onChangeText={enterCode}
              maxLength={codeLength}
              accessibilityLabel={`${codeLength}-digit code`}
              placeholder={'0'.repeat(codeLength)}
              placeholderTextColor={t.text4}
              keyboardType="number-pad"
              textContentType="oneTimeCode"
              autoComplete="sms-otp"
              autoFocus
            />
            <Button title="Sign in" onPress={() => verify()} loading={loading} disabled={code.length < codeLength} />
            <View style={s.row}>
              <Button
                title="Change number"
                variant="secondary"
                onPress={() => { setSentTo(null); setChallengeId(null); setError(null) }}
                style={{ flex: 1 }}
              />
              <Button
                title={resendIn > 0 ? `Resend in ${resendIn}s` : 'Resend code'}
                variant="secondary"
                onPress={sendCode}
                disabled={resendIn > 0 || loading}
                style={{ flex: 1 }}
              />
            </View>
          </>
        )}

        {error ? (
          <View style={s.error}>
            <Icon name="alert" size={16} color={t.danger} style={{ marginTop: 2 }} />
            <Text style={[type.body, { color: t.danger, flex: 1 }]}>{error}</Text>
          </View>
        ) : null}
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: t.bg },
  body: { flex: 1, justifyContent: 'center', padding: space[6], gap: space[4] },
  logo: { marginBottom: space[6] },
  eyebrow: { marginTop: space[2], marginBottom: -space[2] },
  code: { fontFamily: fonts.monoMedium, fontSize: font.size.display, letterSpacing: 6, fontVariant: ['tabular-nums'] },
  row: { flexDirection: 'row', gap: space[3] },
  error: { flexDirection: 'row', alignItems: 'flex-start', gap: space[2] },
})
