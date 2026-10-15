import type { ReactNode } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import { router } from 'expo-router'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { PageTitle, Segmented } from './ui'
import { Icon } from './Icon'
import { t, font, fonts, radius, space } from '@/lib/theme'

type View_ = 'categories' | 'brands'

const VIEWS: { key: View_; label: string }[] = [
  { key: 'categories', label: 'Categories' },
  { key: 'brands', label: 'Brands' },
]

/** The top of the Shop tab, as on the web (components/ShopHeader.tsx): one way
 *  into search, and a switch between browsing by category and by brand. */
export default function ShopHeader({ active, sub }: { active: View_; sub?: ReactNode }) {
  const insets = useSafeAreaInsets()
  return (
    <View style={{ paddingTop: insets.top + 26, paddingHorizontal: space[4] }}>
      <PageTitle sub={sub}>Shop</PageTitle>

      {/* Looks like a field; opens Search with the real one focused. */}
      <Pressable
        onPress={() => router.push('/shop/search')}
        accessibilityRole="search"
        accessibilityLabel="Search products, brands, strains"
        style={s.field}
      >
        <Icon name="search" size={18} color={t.text3} />
        <Text style={s.placeholder}>Search products, brands, strains</Text>
      </Pressable>

      <Segmented
        options={VIEWS}
        value={active}
        // A switch between two views of one tab, not a step to go Back through.
        onChange={key => { if (key !== active) router.replace(key === 'brands' ? '/shop/brands' : '/shop') }}
        style={{ marginTop: 12 }}
      />
    </View>
  )
}

const s = StyleSheet.create({
  field: {
    minHeight: 46, marginTop: 14, flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14,
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border, borderRadius: radius.md,
  },
  placeholder: { fontFamily: fonts.sans, fontSize: font.size.callout, color: t.text4 },
})
