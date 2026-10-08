import { Alert, Platform, ScrollView, Switch, Text, View } from 'react-native'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { formatE164ForDisplay } from '@/lib/phone'
import { useFetch } from '@/lib/useFetch'
import { Button, FeedState, SectionTitle, StoreBullet, styles } from '@/components/ui'
import EmailEditor from '@/components/EmailEditor'
import { t, space, type } from '@/lib/theme'

export default function Profile() {
  const { signOut, setProfile } = useAuth()
  const profile = useFetch('profile', () => api.me.getProfile())
  const stores = useFetch('stores', () => api.me.listPreferredDispensaries())

  if (profile.loading || profile.error) {
    return <FeedState loading={profile.loading} error={profile.error} onRetry={profile.refresh} />
  }
  const me = profile.data!

  async function setOptIn(value: boolean) {
    profile.setData(() => ({ ...me, marketing_opt_in: value }))
    try {
      // Turning texts on records consent to the disclosure shown below the
      // switch, so its version goes with the request.
      const updated = await api.me.updateProfile({
        marketing_opt_in: value,
        marketing_sms_version: me.onboarding.disclosures.marketing_sms.version,
        platform: Platform.OS === 'ios' || Platform.OS === 'android' ? Platform.OS : 'web',
      })
      profile.setData(() => updated)
      setProfile(updated)
    } catch {
      profile.setData(() => me)
    }
  }

  // Signing back in costs a text and a code, so ask first.
  function confirmSignOut() {
    Alert.alert('Sign out?', "Signing back in takes a code sent to your phone.", [
      { text: 'Stay signed in', style: 'cancel' },
      { text: 'Sign out', onPress: () => { signOut() } },
    ])
  }

  function confirmDelete() {
    Alert.alert(
      'Delete your account?',
      'This signs you out everywhere, cancels open pickup orders, and forfeits your points. '
        + 'Your name, phone number and receipt photos are erased. This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete account',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.me.deleteAccount()
              await signOut()
            } catch (err) {
              Alert.alert('Could not delete your account', err instanceof Error ? err.message : String(err))
            }
          },
        },
      ],
    )
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={{ paddingBottom: space[8] }}>
      <View style={{ padding: space[4], gap: space[1] }}>
        <Text style={type.display} accessibilityRole="header">{me.name || 'Welcome'}</Text>
        {me.phone ? <Text style={[type.mono, { color: t.text3 }]}>{formatE164ForDisplay(me.phone)}</Text> : null}
      </View>

      <EmailEditor
        profile={me}
        onSaved={updated => {
          profile.setData(() => updated)
          setProfile(updated)
        }}
      />

      <View style={[styles.card, { marginHorizontal: space[4], marginTop: space[3], padding: space[4], gap: space[2] }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <Text style={[styles.name, { flex: 1 }]}>Deals and drops by text</Text>
          <Switch
            value={me.marketing_opt_in}
            onValueChange={setOptIn}
            trackColor={{ true: t.accent, false: t.surface3 }}
            ios_backgroundColor={t.surface3}
          />
        </View>
        <Text style={styles.meta}>{me.onboarding.disclosures.marketing_sms.text}</Text>
      </View>

      <SectionTitle>Stores you follow</SectionTitle>
      <View style={{ paddingHorizontal: space[4], gap: space[2] }}>
        {stores.loading ? null : stores.data?.length ? (
          stores.data.map(d => (
            <View key={d.id} style={[styles.card, { padding: space[3], flexDirection: 'row', alignItems: 'center', gap: space[3] }]}>
              <StoreBullet name={d.name} address={d.address} />
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{d.name}</Text>
                {d.address ? <Text style={styles.meta} numberOfLines={2}>{d.address}</Text> : null}
              </View>
            </View>
          ))
        ) : (
          <Text style={styles.meta}>None yet.</Text>
        )}
      </View>

      <Button title="Sign out" icon="log-out" variant="secondary" onPress={confirmSignOut} style={{ margin: space[4], marginTop: space[7] }} />
      <Button title="Delete account" icon="trash" variant="danger" onPress={confirmDelete} style={{ marginHorizontal: space[4] }} />
    </ScrollView>
  )
}
