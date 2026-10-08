import { useState, type ReactNode } from 'react'
import {
  KeyboardAvoidingView, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { Button, Label, styles } from '@/components/ui'
import { Icon, Logo } from '@/components/Icon'
import { t, radius, space, fonts, type } from '@/lib/theme'

/** After the first verified login, and again whenever the terms change.
 *
 *  Every disclosure shown here comes from the server (`/me` onboarding), and
 *  its version is sent back with the answers, so what is recorded is exactly
 *  what was on screen. The device age gate stays as the App Store's gate in
 *  front of the content; this is the confirmation the API records and checks.
 */
export default function SignUp() {
  const { profile, setProfile, signOut } = useAuth()
  const onboarding = profile!.onboarding
  const { disclosures } = onboarding

  const [first, setFirst] = useState(profile!.first_name ?? onboarding.prefill.first_name ?? '')
  const [last, setLast] = useState(profile!.last_name ?? onboarding.prefill.last_name ?? '')
  const [age, setAge] = useState(false)
  const [terms, setTerms] = useState(false)
  // Off unless they turn it on; already-consented customers see their choice.
  const [marketing, setMarketing] = useState(profile!.marketing_opt_in)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const returning = !onboarding.missing.includes('first_name') && !onboarding.missing.includes('age_21')
  const ready = first.trim().length > 0 && age && terms

  async function submit() {
    setLoading(true)
    setError(null)
    try {
      const updated = await api.me.completeOnboarding({
        first_name: first.trim(),
        last_name: last.trim() || null,
        age_21: age,
        terms_version: disclosures.terms.version,
        marketing_sms_opt_in: marketing,
        marketing_sms_version: marketing ? disclosures.marketing_sms.version : null,
        platform: Platform.OS === 'ios' || Platform.OS === 'android' ? Platform.OS : 'web',
      })
      // A complete profile flips the router guard into the app.
      setProfile(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setLoading(false)
    }
  }

  return (
    <SafeAreaView style={s.screen}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={s.body} keyboardShouldPersistTaps="handled">
          <Logo size={28} style={s.logo} />
          <Text style={type.display} accessibilityRole="header">{returning ? 'We updated our terms' : 'Finish signing up'}</Text>
          <Text style={s.copy}>
            {returning
              ? 'Please review and accept them to keep ordering.'
              : 'A few details before you can reserve products for pickup.'}
          </Text>

          <Label style={s.label}>First name</Label>
          <TextInput
            style={styles.input}
            value={first}
            onChangeText={setFirst}
            autoComplete="given-name"
            textContentType="givenName"
            autoCapitalize="words"
            maxLength={100}
            placeholder="Required"
            placeholderTextColor={t.text4}
          />
          <Label style={s.label}>Last name</Label>
          <TextInput
            style={styles.input}
            value={last}
            onChangeText={setLast}
            autoComplete="family-name"
            textContentType="familyName"
            autoCapitalize="words"
            maxLength={100}
            placeholder="Optional"
            placeholderTextColor={t.text4}
          />

          <Check checked={age} onChange={setAge}>
            <Text style={s.checkText}>{disclosures.age_21.text}</Text>
          </Check>

          <Check checked={terms} onChange={setTerms}>
            <Text style={s.checkText}>
              I agree to the{' '}
              <DocLink url={disclosures.terms.terms_url}>Terms of Service</DocLink>
              {' '}and{' '}
              <DocLink url={disclosures.terms.privacy_url}>Privacy Policy</DocLink>.
            </Text>
          </Check>

          <Check checked={marketing} onChange={setMarketing}>
            <Text style={s.checkText}>
              <Text style={{ fontFamily: fonts.sansSemibold }}>Optional: </Text>
              {disclosures.marketing_sms.text}
            </Text>
          </Check>

          {error ? (
            <View style={s.error}>
              <Icon name="alert" size={16} color={t.danger} style={{ marginTop: 3 }} />
              <Text style={[type.copy, { color: t.danger, flex: 1 }]}>{error}</Text>
            </View>
          ) : null}

          <Button title="Continue" onPress={submit} disabled={!ready} loading={loading} style={{ marginTop: space[4] }} />
          <Button title="Sign out" variant="secondary" onPress={signOut} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

function Check({ checked, onChange, children }: {
  checked: boolean
  onChange: (v: boolean) => void
  children: ReactNode
}) {
  return (
    <Pressable
      onPress={() => onChange(!checked)}
      style={s.check}
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
    >
      <View style={[s.box, checked && s.boxOn]}>{checked ? <Icon name="check" size={16} color={t.accentInk} strokeWidth={2.5} /> : null}</View>
      <View style={{ flex: 1 }}>{children}</View>
    </Pressable>
  )
}

function DocLink({ url, children }: { url: string | null; children: string }) {
  if (!url) return <Text>{children}</Text>
  return (
    <Text style={s.link} onPress={() => Linking.openURL(url)} accessibilityRole="link">
      {children}
    </Text>
  )
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: t.bg },
  body: { padding: space[6], gap: space[3] },
  logo: { marginBottom: space[5] },
  copy: { ...type.copy, marginBottom: space[2] },
  label: { marginTop: space[2] },
  check: { flexDirection: 'row', gap: space[3], alignItems: 'flex-start', paddingVertical: space[2] },
  box: {
    width: 22, height: 22, borderRadius: radius.xs, borderWidth: 1.5, borderColor: t.text3,
    alignItems: 'center', justifyContent: 'center', marginTop: 1,
  },
  boxOn: { backgroundColor: t.accent, borderColor: t.accent },
  checkText: { ...type.copy, color: t.text1, lineHeight: 21 },
  link: { color: t.text1, fontFamily: fonts.sansSemibold, textDecorationLine: 'underline' },
  error: { flexDirection: 'row', alignItems: 'flex-start', gap: space[2] },
})
