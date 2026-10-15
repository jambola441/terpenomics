import type { ComponentProps } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import type { Tabs } from 'expo-router'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { alpha } from '@web/design/tokens'
import { useOrders } from '@/lib/orders'
import { Icon, type IconName } from './Icon'
import CartBar from './CartBar'
import { t, font, fonts, radius, space } from '@/lib/theme'

type TabBarProps = Parameters<NonNullable<ComponentProps<typeof Tabs>['tabBar']>>[0]

/** Route name → glyph, in the web nav's order (CustomerPortal's TABS). */
const ICONS: Record<string, IconName> = {
  index: 'home',
  shop: 'grid',
  map: 'pin',
  orders: 'bag',
  profile: 'user',
}

/** The web portal's floating bottom nav, with its cart bar above it: a
 *  rounded bar inset from the edges, the active tab's glyph in a resin-tinted
 *  pill, and the open-orders count on Orders. The cart bar only appears once
 *  there is something in the cart. */
export default function TabBar({ state, descriptors, navigation }: TabBarProps) {
  const insets = useSafeAreaInsets()
  const { openCount } = useOrders()

  return (
    <View style={[s.wrap, { paddingBottom: Math.max(insets.bottom, space[3]) }]}>
      <CartBar />

      <View style={s.bar} accessibilityRole="tablist">
        {state.routes.map((route, index) => {
          const { options } = descriptors[route.key]
          const label = typeof options.title === 'string' ? options.title : route.name
          const active = state.index === index
          const badge = route.name === 'orders' && openCount > 0 ? openCount : 0

          function onPress() {
            const event = navigation.emit({ type: 'tabPress', target: route.key, canPreventDefault: true })
            if (!active && !event.defaultPrevented) navigation.navigate(route.name, route.params)
          }

          return (
            <Pressable
              key={route.key}
              onPress={onPress}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              accessibilityLabel={badge ? `${label}, ${badge} open` : label}
              style={s.tab}
            >
              <View style={[s.glyph, active && { backgroundColor: t.accentTint }]}>
                <Icon
                  name={ICONS[route.name] ?? 'grid'}
                  size={19}
                  color={active ? t.accent : t.text3}
                  strokeWidth={active ? 2 : 1.75}
                />
                {badge ? (
                  <View style={s.badge}>
                    <Text style={s.badgeText}>{badge}</Text>
                  </View>
                ) : null}
              </View>
              <Text
                style={{
                  fontFamily: active ? fonts.sansSemibold : fonts.sansMedium,
                  fontSize: font.size.caption,
                  color: active ? t.accent : t.text3,
                }}
              >
                {label}
              </Text>
            </Pressable>
          )
        })}
      </View>
    </View>
  )
}

const s = StyleSheet.create({
  wrap: { backgroundColor: t.bg, paddingHorizontal: 12, paddingTop: space[2], gap: space[2] },
  row: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  bar: {
    height: 60, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 4,
    backgroundColor: alpha(t.surface1, 0.88), borderRadius: radius.xl, borderWidth: 1, borderColor: t.border,
    shadowColor: '#000', shadowOpacity: 0.56, shadowRadius: 24, shadowOffset: { width: 0, height: 16 },
  },
  tab: { flex: 1, height: '100%', alignItems: 'center', justifyContent: 'center', gap: 4 },
  glyph: { width: 40, height: 26, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center' },
  badge: {
    position: 'absolute', top: -4, right: 2, minWidth: 16, height: 16, paddingHorizontal: 4,
    borderRadius: radius.pill, backgroundColor: t.accent, alignItems: 'center', justifyContent: 'center',
  },
  badgeText: { fontFamily: fonts.sansBold, fontSize: 10, lineHeight: 16, color: t.accentInk, fontVariant: ['tabular-nums'] },
})
