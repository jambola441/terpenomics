import { useState } from 'react'
import { Linking, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native'
import { router, Stack, useLocalSearchParams } from 'expo-router'
import type { PortalPartnerLocation } from '@web/types'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { FeedState, Label, styles } from '@/components/ui'
import { Icon, type IconName } from '@/components/Icon'
import { PartnerMark } from '@/components/partners'
import { openStatus, weekHours } from '@web/utils/hours'
import { directionsUrl, telHref } from '@web/utils/partnerPlaces'
import { earnLine } from '@web/utils/pointsProgram'
import { t, space, font, radius, type } from '@/lib/theme'

/** One partner store: what it is, where its stores are and when they're open,
 *  and how shopping there earns points. Same content as the web's partner page. */
export default function Partner() {
  const { slug } = useLocalSearchParams<{ slug: string }>()
  const { data, error, loading, refreshing, refresh } = useFetch(`partner:${slug}`, () => api.portal.getPartner(slug))

  if (loading) return <FeedState loading />
  if (!data) {
    const gone = /not found/i.test(error ?? '')
    return gone
      ? <FeedState empty="This store isn't a partner any more" icon="pin" />
      : <FeedState error={error} onRetry={refresh} />
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={{ padding: space[4], paddingBottom: space[8] }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={t.text3} />}
    >
      <Stack.Screen options={{ title: data.name }} />
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space[3] }}>
        <PartnerMark name={data.name} uri={data.logo_url} size={64} />
        <View style={{ flex: 1 }}>
          <Text style={type.title}>{data.name}</Text>
          <Text style={[styles.meta, { marginTop: 2 }]}>{data.category ?? 'Partner store'}</Text>
        </View>
      </View>

      {data.description ? <Text style={[type.copy, { marginTop: space[4] }]}>{data.description}</Text> : null}
      {data.website_url ? (
        <Pressable onPress={() => Linking.openURL(data.website_url!)} hitSlop={8} style={s.inline} accessibilityRole="link">
          <Text style={[type.link, { color: t.accent }]}>{data.website_url.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')}</Text>
          <Icon name="arrow-up-right" size={14} color={t.accent} />
        </Pressable>
      ) : null}

      <View style={s.earnBox}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space[2] }}>
          <Icon name="drop" size={17} color={t.accent} strokeWidth={2} />
          <Text style={[type.bodyStrong, { color: t.accent, fontSize: font.size.callout, flexShrink: 1 }]}>{earnLine(data.program)}</Text>
        </View>
        <Text style={[type.copy, { marginTop: space[2] }]}>
          Give the phone number you sign in with at checkout. Points are yours {data.program.pending_days} days later.
          Forgot? Send the receipt within {data.program.claim_window_days} days.
        </Text>
        <View style={{ flexDirection: 'row', gap: space[5], marginTop: space[3] }}>
          <Pressable onPress={() => router.push('/receipt')} hitSlop={8} accessibilityRole="button">
            <Text style={[type.link, { color: t.accent }]}>Send a receipt</Text>
          </Pressable>
          <Pressable onPress={() => router.push('/how-points-work')} hitSlop={8} accessibilityRole="link">
            <Text style={[type.link, { color: t.accent }]}>How points work</Text>
          </Pressable>
        </View>
      </View>

      <Label style={{ marginTop: space[6] }}>{data.locations.length > 1 ? `${data.locations.length} locations` : 'Location'}</Label>
      {data.locations.length === 0 ? (
        <Text style={[styles.meta, { marginTop: space[3] }]}>No store address yet.</Text>
      ) : (
        data.locations.map(loc => <LocationRow key={loc.id} location={loc} />)
      )}
    </ScrollView>
  )
}

function LocationRow({ location: loc }: { location: PortalPartnerLocation }) {
  const [showHours, setShowHours] = useState(false)
  const status = openStatus(loc.hours, loc.timezone)
  const directions = directionsUrl(loc, Platform.OS === 'ios')
  return (
    <View style={s.location}>
      <Text style={[styles.name, { fontSize: font.size.callout }]}>{loc.name}</Text>
      {loc.address ? <Text style={[type.copy, { fontSize: font.size.small + 1, marginTop: 2 }]}>{loc.address}</Text> : null}
      {status ? (
        <Text style={[styles.meta, { marginTop: 4, fontSize: font.size.small + 1, color: status.open ? t.success : t.text3 }]}>{status.text}</Text>
      ) : null}
      <View style={{ flexDirection: 'row', gap: space[2], marginTop: space[3], flexWrap: 'wrap' }}>
        {directions ? <Action icon="navigate" label="Directions" onPress={() => Linking.openURL(directions)} /> : null}
        {loc.lat != null && loc.lng != null ? (
          <Action
            icon="map"
            label="Show on map"
            onPress={() => router.navigate({ pathname: '/map', params: { show: 'partners', spot: loc.id } })}
          />
        ) : null}
        {loc.phone ? <Action icon="phone" label={loc.phone} onPress={() => Linking.openURL(telHref(loc.phone!))} /> : null}
        {loc.hours?.length ? <Action icon="clock" label={showHours ? 'Hide hours' : 'Hours'} onPress={() => setShowHours(v => !v)} /> : null}
      </View>
      {showHours && loc.hours ? (
        <View style={{ marginTop: space[3], gap: 4 }}>
          {weekHours(loc.hours).map(d => (
            <View key={d.day} style={{ flexDirection: 'row', gap: space[4] }}>
              <Text style={[styles.meta, { width: 36, fontSize: font.size.small + 1 }]}>{d.label}</Text>
              <Text style={[type.body, { color: d.text === 'Closed' ? t.text3 : t.text1 }]}>{d.text}</Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  )
}

function Action({ icon, label, onPress }: { icon: IconName; label: string; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [s.action, pressed && { backgroundColor: t.surface3 }]}
      accessibilityRole="button"
    >
      <Icon name={icon} size={15} color={t.text1} />
      <Text style={[type.button, { color: t.text1, fontSize: font.size.small + 1 }]}>{label}</Text>
    </Pressable>
  )
}

const s = StyleSheet.create({
  inline: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: space[2], alignSelf: 'flex-start' },
  earnBox: {
    marginTop: space[5], padding: space[4], borderRadius: radius.lg,
    backgroundColor: t.accentTint, borderWidth: 1, borderColor: t.accentDim,
  },
  location: { paddingVertical: space[4], borderBottomWidth: 1, borderBottomColor: t.border },
  action: {
    flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 40, paddingHorizontal: space[4],
    borderRadius: radius.pill, backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border,
  },
})
