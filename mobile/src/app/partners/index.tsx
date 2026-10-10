import { useMemo } from 'react'
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native'
import { router } from 'expo-router'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { FeedState, styles } from '@/components/ui'
import { Icon } from '@/components/Icon'
import { PartnerMark, PointsSteps, useKnownPosition } from '@/components/partners'
import { formatDist } from '@web/utils/format'
import { nearestStore, sortPartners } from '@web/utils/partnerPlaces'
import { PARTNER_DEFINITION, earnLine } from '@web/utils/pointsProgram'
import { t, space, font, radius, type } from '@/lib/theme'

/** Where to earn Terpee points: what a partner store is, how earning works, and
 *  every partner, nearest first when the phone already shares where it is. Same
 *  content as the web's /portal/partners. */
export default function Partners() {
  const { data, error, loading, refreshing, refresh } = useFetch('partners', () => api.portal.getPartners())
  const pos = useKnownPosition()
  const partners = useMemo(() => sortPartners(data?.partners ?? [], pos), [data, pos])

  if (loading || (error && !data)) return <FeedState loading={loading} error={error} onRetry={refresh} />
  const program = data!.program

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={{ padding: space[4], paddingBottom: space[8], gap: space[4] }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={t.text3} />}
    >
      <Text style={[type.copy, { color: t.text3 }]}>{PARTNER_DEFINITION}</Text>

      <View style={[styles.card, { padding: space[4] }]}>
        <PointsSteps program={program} compact />
        <Pressable onPress={() => router.push('/how-points-work')} hitSlop={8} style={s.link} accessibilityRole="link">
          <Text style={[type.link, { color: t.accent }]}>How points work</Text>
          <Icon name="chevron-right" size={15} color={t.accent} />
        </Pressable>
      </View>

      {partners.length === 0 ? (
        <FeedState empty="No partner stores yet" hint="Local businesses are joining. Check back soon." icon="pin" style={{ flex: 0, paddingVertical: space[8] }} />
      ) : (
        partners.map(p => {
          const near = nearestStore(p, pos)
          const stores = p.locations.length
          const where = near
            ? `${formatDist(near.miles)}${stores > 1 ? ` · ${stores} stores` : ''}`
            : stores === 1 ? p.locations[0].address ?? '1 store' : stores > 1 ? `${stores} stores` : null
          return (
            <Pressable
              key={p.id}
              onPress={() => router.push({ pathname: '/partners/[slug]', params: { slug: p.slug } })}
              style={({ pressed }) => [styles.card, s.row, pressed && { backgroundColor: t.surface2 }]}
              accessibilityRole="button"
              accessibilityLabel={`${p.name}${p.category ? `, ${p.category}` : ''}`}
            >
              <PartnerMark name={p.name} uri={p.logo_url} />
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={[styles.name, { fontSize: font.size.callout }]}>{p.name}</Text>
                {(p.category || where) ? <Text style={styles.meta}>{[p.category, where].filter(Boolean).join(' · ')}</Text> : null}
                {p.description ? <Text style={[type.copy, { fontSize: font.size.small + 1, lineHeight: 19, marginTop: 4 }]} numberOfLines={2}>{p.description}</Text> : null}
                <View style={s.earn}>
                  <Icon name="drop" size={13} color={t.accent} strokeWidth={2} />
                  <Text style={[styles.meta, { color: t.accent }]}>{earnLine(program)}</Text>
                </View>
              </View>
              <Icon name="chevron-right" size={18} color={t.text3} />
            </Pressable>
          )
        })
      )}
    </ScrollView>
  )
}

const s = StyleSheet.create({
  link: { flexDirection: 'row', alignItems: 'center', gap: 2, marginTop: space[3], alignSelf: 'flex-start' },
  row: { flexDirection: 'row', alignItems: 'center', gap: space[3], padding: space[4], borderRadius: radius.lg },
  earn: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: space[2] },
})
