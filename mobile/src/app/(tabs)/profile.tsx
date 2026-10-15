import { useCallback, useRef, useState } from 'react'
import { Alert, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native'
import { useFocusEffect } from 'expo-router'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import type { CustomerProfile } from '@web/types'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { formatE164ForDisplay } from '@/lib/phone'
import { useFetch } from '@/lib/useFetch'
import { Button, FeedState, Label, Segmented, styles } from '@/components/ui'
import { Icon } from '@/components/Icon'
import EmailEditor from '@/components/EmailEditor'
import PointsPane from '@/components/PointsPane'
import FeedbackPane from '@/components/FeedbackPane'
import { t, font, fonts, radius, space, type } from '@/lib/theme'

type Pane = 'points' | 'feedback' | 'profile'

const PANES: { key: Pane; label: string }[] = [
  { key: 'points', label: 'Points' },
  { key: 'feedback', label: 'Feedback' },
  { key: 'profile', label: 'Profile' },
]

/** You, as on the web portal (components/ProfileView.tsx): who you are and
 *  your points balance up top, then Points, Feedback and Profile panes. */
export default function You() {
  const insets = useSafeAreaInsets()
  const { profile: me, setProfile } = useAuth()
  const [pane, setPane] = useState<Pane>('points')
  const points = useFetch('points', () => api.me.getPoints())
  const receipts = useFetch('receipts', () => api.me.getReceipts())

  // Back from the receipt upload, or after a reviewer approves, the balance
  // should be current without a pull. The first focus is the load.
  const focused = useRef(false)
  const refreshPoints = points.refresh
  const refreshReceipts = receipts.refresh
  useFocusEffect(
    useCallback(() => {
      if (focused.current) {
        refreshPoints()
        refreshReceipts()
      }
      focused.current = true
    }, [refreshPoints, refreshReceipts]),
  )

  if (!me) return <FeedState loading />

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={{ paddingTop: insets.top + 28, paddingBottom: space[7] }}
      keyboardShouldPersistTaps="handled"
      refreshControl={
        <RefreshControl
          refreshing={points.refreshing}
          onRefresh={() => {
            points.refresh()
            receipts.refresh()
          }}
          tintColor={t.text3}
        />
      }
    >
      <View style={s.identity}>
        <View style={s.avatar}>
          <Text style={s.avatarLetter}>{(me.name ?? me.phone ?? '?').charAt(0).toUpperCase()}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text numberOfLines={1} style={s.name} accessibilityRole="header">{me.name || 'Your account'}</Text>
          <Text style={s.phone}>{me.phone ? formatE164ForDisplay(me.phone) : me.email}</Text>
        </View>
        {points.data ? (
          <Pressable
            onPress={() => setPane('points')}
            accessibilityRole="button"
            accessibilityLabel={`${points.data.available} Terpee points`}
            style={s.chip}
          >
            <Icon name="drop" size={15} color={t.accent} strokeWidth={2} />
            <Text style={s.chipPoints}>{points.data.available.toLocaleString()}</Text>
            <Text style={s.chipUnit}>pts</Text>
          </Pressable>
        ) : null}
      </View>

      <Segmented options={PANES} value={pane} onChange={setPane} style={{ marginTop: 22, marginHorizontal: space[4] }} />

      {pane === 'points' ? (
        points.data ? (
          <PointsPane data={points.data} receipts={receipts.data} />
        ) : (
          <FeedState loading={points.loading} error={points.error} onRetry={points.refresh} style={{ paddingVertical: space[8] }} />
        )
      ) : pane === 'feedback' ? (
        <FeedbackPane customerId={me.id} />
      ) : (
        <ProfilePane profile={me} onSaved={setProfile} />
      )}
    </ScrollView>
  )
}

/* ── Profile ───────────────────────────────────────────────────────────────── */

function ProfilePane({ profile, onSaved }: { profile: CustomerProfile; onSaved: (p: CustomerProfile) => void }) {
  const { signOut } = useAuth()
  const [first, setFirst] = useState(profile.first_name ?? '')
  const [last, setLast] = useState(profile.last_name ?? '')
  const [optIn, setOptIn] = useState(profile.marketing_opt_in)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null)
  const stores = useFetch('stores', () => api.me.listPreferredDispensaries())

  const namesChanged = first.trim() !== (profile.first_name ?? '') || last.trim() !== (profile.last_name ?? '')
  const dirty = namesChanged || optIn !== profile.marketing_opt_in

  async function save() {
    setSaving(true)
    setStatus(null)
    try {
      const updated = await api.me.updateProfile({
        ...(namesChanged ? { first_name: first.trim(), last_name: last.trim() } : {}),
        marketing_opt_in: optIn,
        // Opting in records consent to the disclosure shown beside the switch.
        marketing_sms_version: profile.onboarding.disclosures.marketing_sms.version,
        platform: Platform.OS === 'ios' || Platform.OS === 'android' ? Platform.OS : 'web',
      })
      onSaved(updated)
      setStatus({ ok: true, text: 'Saved' })
    } catch (err) {
      setStatus({ ok: false, text: err instanceof Error && err.message ? err.message : 'Could not save. Try again.' })
    } finally {
      setSaving(false)
    }
  }

  // Signing back in costs a text and a code, so ask first.
  function confirmSignOut() {
    Alert.alert('Sign out?', 'Signing back in takes a code sent to your phone.', [
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
        { text: 'Keep my account', style: 'cancel' },
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
    <View style={{ paddingHorizontal: space[4], paddingTop: 18, gap: 22 }}>
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <View style={{ flex: 1 }}>
          <Label>First name</Label>
          <TextInput
            value={first}
            onChangeText={setFirst}
            autoComplete="given-name"
            textContentType="givenName"
            maxLength={100}
            style={s.input}
          />
        </View>
        <View style={{ flex: 1 }}>
          <Label>Last name</Label>
          <TextInput
            value={last}
            onChangeText={setLast}
            autoComplete="family-name"
            textContentType="familyName"
            maxLength={100}
            placeholder="Optional"
            placeholderTextColor={t.text4}
            style={s.input}
          />
        </View>
      </View>

      {/* Phone is shown but not editable: it is how sign-in and in-store
          purchase matching find this account. Email is contact only. */}
      <View style={{ gap: 10 }}>
        <View style={s.readOnly}>
          <Label>Phone</Label>
          <Text style={[type.mono, { color: t.text1 }]}>{profile.phone ? formatE164ForDisplay(profile.phone) : '—'}</Text>
        </View>
        <Text style={s.note}>
          Your phone number is how you sign in and how stores match your purchases. Ask a staff member to change it.
        </Text>
        <EmailEditor profile={profile} onSaved={onSaved} />
      </View>

      <View style={[styles.card, { padding: 14, flexDirection: 'row', gap: 12, alignItems: 'flex-start' }]}>
        <View style={{ flex: 1 }}>
          <Text style={styles.name}>Deal alerts by text</Text>
          <Text style={[s.note, { marginTop: 3 }]}>{profile.onboarding.disclosures.marketing_sms.text}</Text>
        </View>
        <Switch
          value={optIn}
          onValueChange={setOptIn}
          trackColor={{ true: t.accent, false: t.surface3 }}
          ios_backgroundColor={t.surface3}
        />
      </View>

      <View>
        <Label>Stores you follow</Label>
        <Text style={[s.note, { marginTop: 8 }]}>
          {stores.data == null
            ? 'Loading…'
            : stores.data.length === 0
              ? 'None yet. Pick some on Home to build your feed.'
              : stores.data.map(d => d.name).join(' · ')}
        </Text>
      </View>

      <View>
        <Button
          title="Save changes"
          onPress={save}
          loading={saving}
          disabled={!dirty || (namesChanged && !first.trim())}
        />
        {status ? (
          <View style={s.status} accessibilityLiveRegion="polite">
            {status.ok ? <Icon name="check" size={15} color={t.success} /> : null}
            <Text style={{ fontFamily: fonts.sans, fontSize: font.size.small, color: status.ok ? t.success : t.danger }}>
              {status.text}
            </Text>
          </View>
        ) : null}
      </View>

      <Button title="Sign out" icon="log-out" variant="secondary" onPress={confirmSignOut} style={{ alignSelf: 'center', paddingHorizontal: 24 }} />
      <Pressable onPress={confirmDelete} accessibilityRole="button" style={{ alignSelf: 'center', padding: 8 }}>
        <Text style={s.delete}>Delete account</Text>
      </Pressable>
    </View>
  )
}

const s = StyleSheet.create({
  identity: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingHorizontal: 20 },
  avatar: {
    width: 56, height: 56, borderRadius: 28, alignItems: 'center', justifyContent: 'center',
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border,
  },
  avatarLetter: { fontFamily: fonts.display, fontSize: 24, color: t.text1 },
  name: { fontFamily: fonts.display, fontSize: font.size.display, lineHeight: 28, letterSpacing: -0.48, color: t.text1 },
  phone: { fontFamily: fonts.sans, fontSize: font.size.small, color: t.text3, marginTop: 2 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingVertical: 7, paddingLeft: 10, paddingRight: 12, borderRadius: radius.pill,
    backgroundColor: t.accentTint, borderWidth: 1, borderColor: t.accentDim,
  },
  chipPoints: { fontFamily: fonts.sansBold, fontSize: font.size.callout, color: t.accent, fontVariant: ['tabular-nums'] },
  chipUnit: { fontFamily: fonts.monoMedium, fontSize: font.size.caption, color: t.accent },
  input: {
    ...type.body, fontSize: font.size.callout, marginTop: 6, minHeight: 44, paddingHorizontal: 12,
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border, borderRadius: radius.md,
  },
  readOnly: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    padding: 12, backgroundColor: t.surface1, borderWidth: 1, borderColor: t.border, borderRadius: radius.md,
  },
  note: { fontFamily: fonts.sans, fontSize: font.size.small, lineHeight: 18, color: t.text3 },
  status: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, marginTop: 10 },
  delete: { fontFamily: fonts.sans, fontSize: font.size.small, color: t.danger, textDecorationLine: 'underline' },
})
