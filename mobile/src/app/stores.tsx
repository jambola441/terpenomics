import { useMemo, useState } from 'react'
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from 'react-native'
import { router } from 'expo-router'
import { SafeAreaView } from 'react-native-safe-area-context'
import type { PortalDispensary } from '@web/types'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { Button, FeedState, StoreBullet, styles } from '@/components/ui'
import { Icon } from '@/components/Icon'
import { t, space, radius, type } from '@/lib/theme'

/** Pick the stores Home is built from. Before this the app could only say
 *  "follow a few stores on the Terpee website", so an app-only shopper's Home
 *  stayed empty for good. */
export default function Stores() {
  const { data, error, loading, refresh, setData } = useFetch('stores', async () => {
    const [all, followed] = await Promise.all([api.portal.getDispensaries(), api.me.listPreferredDispensaries()])
    return { all, followed }
  })
  const [query, setQuery] = useState('')
  const [pending, setPending] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  const followedIds = useMemo(() => new Set((data?.followed ?? []).map(d => d.id)), [data])
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    const all = data?.all ?? []
    return q ? all.filter(d => `${d.name} ${d.address ?? ''}`.toLowerCase().includes(q)) : all
  }, [data, query])

  async function toggle(store: PortalDispensary) {
    setPending(store.id)
    setSaveError(null)
    try {
      const followed = followedIds.has(store.id)
        ? await api.me.removePreferredDispensary(store.id)
        : await api.me.addPreferredDispensary(store.id)
      setData(prev => (prev ? { ...prev, followed } : prev))
    } catch {
      setSaveError("That didn't save. Try again.")
    } finally {
      setPending(null)
    }
  }

  if (loading || error) return <FeedState loading={loading} error={error} onRetry={refresh} />

  return (
    <SafeAreaView style={styles.screen} edges={['bottom']}>
      <FlatList
        data={shown}
        keyExtractor={d => d.id}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingBottom: space[6] }}
        ListHeaderComponent={
          <View style={s.header}>
            <Text style={type.copy}>
              Home is built from the stores you follow. Pick the ones you actually shop at; you can change this any time.
            </Text>
            <View style={s.search}>
              <Icon name="search" size={18} color={t.text3} />
              <TextInput
                value={query}
                onChangeText={setQuery}
                placeholder="Find a store"
                placeholderTextColor={t.text4}
                style={[type.body, { flex: 1, paddingVertical: space[3] }]}
                autoCorrect={false}
              />
            </View>
            {saveError ? <Text style={[type.meta, { color: t.danger }]}>{saveError}</Text> : null}
          </View>
        }
        ListEmptyComponent={<FeedState empty="No stores match" icon="store" />}
        renderItem={({ item }) => {
          const following = followedIds.has(item.id)
          return (
            <View style={s.row}>
              <StoreBullet name={item.name} address={item.address} />
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={type.heading} numberOfLines={1}>{item.name}</Text>
                {item.address ? <Text style={type.meta} numberOfLines={1}>{item.address}</Text> : null}
              </View>
              <Pressable
                onPress={() => toggle(item)}
                disabled={pending === item.id}
                accessibilityRole="button"
                accessibilityState={{ selected: following, busy: pending === item.id }}
                accessibilityLabel={following ? `Unfollow ${item.name}` : `Follow ${item.name}`}
                style={[s.toggle, following ? s.following : s.follow]}
              >
                {following ? <Icon name="check" size={15} color={t.accent} /> : null}
                <Text style={[type.button, { color: following ? t.accent : t.accentInk }]}>
                  {following ? 'Following' : 'Follow'}
                </Text>
              </Pressable>
            </View>
          )
        }}
        ListFooterComponent={
          <View style={{ paddingHorizontal: space[4], paddingTop: space[4] }}>
            <Button
              title={followedIds.size ? `Done · ${followedIds.size} followed` : 'Done'}
              onPress={() => router.back()}
              disabled={followedIds.size === 0}
            />
          </View>
        }
      />
    </SafeAreaView>
  )
}

const s = StyleSheet.create({
  header: { padding: space[4], gap: space[3] },
  search: {
    flexDirection: 'row', alignItems: 'center', gap: space[2], paddingHorizontal: space[3],
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border, borderRadius: radius.md,
  },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: space[3],
    paddingHorizontal: space[4], paddingVertical: space[3],
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: t.border,
  },
  toggle: {
    flexDirection: 'row', alignItems: 'center', gap: 4, minHeight: 40,
    paddingHorizontal: space[3], borderRadius: radius.pill,
  },
  follow: { backgroundColor: t.accent },
  following: { backgroundColor: 'transparent', borderWidth: 1, borderColor: t.accent },
})
