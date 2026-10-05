import { Alert, Platform, ScrollView, Switch, Text, View } from 'react-native'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { formatE164ForDisplay } from '@/lib/phone'
import { useFetch } from '@/lib/useFetch'
import { Button, FeedState, SectionTitle, styles } from '@/components/ui'
import EmailEditor from '@/components/EmailEditor'
import { t, space } from '@/lib/theme'

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
        <Text style={[styles.name, { fontSize: 24 }]}>{me.name || 'Welcome'}</Text>
        {me.phone ? <Text style={styles.meta}>{formatE164ForDisplay(me.phone)}</Text> : null}
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
          <Switch value={me.marketing_opt_in} onValueChange={setOptIn} trackColor={{ true: t.accent }} />
        </View>
        <Text style={styles.meta}>{me.onboarding.disclosures.marketing_sms.text}</Text>
      </View>

      <SectionTitle>Stores you follow</SectionTitle>
      <View style={{ paddingHorizontal: space[4], gap: space[2] }}>
        {stores.loading ? null : stores.data?.length ? (
          stores.data.map(d => (
            <View key={d.id} style={[styles.card, { padding: space[3] }]}>
              <Text style={styles.name}>{d.name}</Text>
              {d.address ? <Text style={styles.meta}>{d.address}</Text> : null}
            </View>
          ))
        ) : (
          <Text style={styles.meta}>None yet.</Text>
        )}
      </View>

      <Button title="Sign out" variant="ghost" onPress={signOut} style={{ margin: space[4], marginTop: space[7] }} />
      <Button title="Delete account" variant="ghost" onPress={confirmDelete} style={{ marginHorizontal: space[4] }} />
    </ScrollView>
  )
}
