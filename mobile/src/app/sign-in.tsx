import { useEffect, useState } from 'react'
import { KeyboardAvoidingView, Platform, Text, TextInput, View, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { api, ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { formatE164ForDisplay, formatPhoneInput, toE164 } from '@/lib/phone'
import { Button } from '@/components/ui'
import { t, radius, space, font } from '@/lib/theme'

/** Phone number, then the code. Mirrors the SMS half of the web Login page. */
export default function SignIn() {
  const { signInWithSms } = useAuth()
  const [phone, setPhone] = useState('')
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [challengeId, setChallengeId] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [resendIn, setResendIn] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (resendIn <= 0) return
    const id = setTimeout(() => setResendIn(s => s - 1), 1000)
    return () => clearTimeout(id)
  }, [resendIn])

  function fail(err: unknown) {
    if (err instanceof ApiError && err.retryAfter) {
      setResendIn(err.retryAfter)
    }
    setError(err instanceof Error ? err.message : String(err))
  }

  async function sendCode() {
    const e164 = toE164(phone)
    if (!e164) {
      setError('Enter a 10-digit US phone number.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await api.auth.smsStart(e164)
      setChallengeId(res.challenge_id)
      setSentTo(e164)
      setResendIn(res.resend_in)
      setCode('')
    } catch (err) {
      fail(err)
    } finally {
      setLoading(false)
    }
  }

  async function verify() {
    if (!challengeId) return
    setLoading(true)
    setError(null)
    try {
      // On success the auth listener flips the session and the router moves
      // us into the tabs, so there is nothing to navigate to here.
      await signInWithSms(challengeId, code.trim())
    } catch (err) {
      fail(err)
      setLoading(false)
    }
  }

  return (
    <SafeAreaView style={s.screen}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={s.body}>
        <Text style={s.brand}>terpenomics</Text>

        {sentTo === null ? (
          <>
            <Text style={s.label}>Sign in with your phone number</Text>
            <TextInput
              style={s.input}
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
            <Text style={s.label}>Enter the code we sent to {formatE164ForDisplay(sentTo)}</Text>
            <TextInput
              style={[s.input, s.code]}
              value={code}
              onChangeText={v => setCode(v.replace(/\D/g, '').slice(0, 8))}
              placeholder="123456"
              placeholderTextColor={t.text4}
              keyboardType="number-pad"
              textContentType="oneTimeCode"
              autoComplete="sms-otp"
              autoFocus
            />
            <Button title="Sign in" onPress={verify} loading={loading} disabled={code.length < 4} />
            <View style={s.row}>
              <Button
                title="Change number"
                variant="ghost"
                onPress={() => { setSentTo(null); setChallengeId(null); setError(null) }}
                style={{ flex: 1 }}
              />
              <Button
                title={resendIn > 0 ? `Resend in ${resendIn}s` : 'Resend code'}
                variant="ghost"
                onPress={sendCode}
                disabled={resendIn > 0 || loading}
                style={{ flex: 1 }}
              />
            </View>
          </>
        )}

        {error ? <Text style={s.error}>{error}</Text> : null}
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: t.bg },
  body: { flex: 1, justifyContent: 'center', padding: space[6], gap: space[4] },
  brand: { color: t.accent, fontSize: font.size.hero, fontWeight: font.weight.heavy, marginBottom: space[6] },
  label: { color: t.text2, fontSize: font.size.callout },
  input: {
    backgroundColor: t.surface2,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: t.border,
    color: t.text1,
    fontSize: font.size.title,
    paddingHorizontal: space[4],
    minHeight: 52,
  },
  code: { letterSpacing: 6, fontSize: font.size.display },
  row: { flexDirection: 'row', gap: space[3] },
  error: { color: t.danger, fontSize: font.size.body },
})
