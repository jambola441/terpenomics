import { Pressable, StyleSheet, Text, View } from 'react-native'
import { router } from 'expo-router'
import { useCart } from '@/lib/cart'
import { Icon } from './Icon'
import { t, font, fonts, radius } from '@/lib/theme'

/** The web's cart bar: "N items in cart · View", in resin. Only drawn once
 *  there is something in the cart. Sits above the tab bar, and at the foot of
 *  screens that cover the tabs (a store's menu and aisles). */
export default function CartBar() {
  const { count } = useCart()
  if (count === 0) return null
  return (
    <Pressable
      onPress={() => router.push('/cart')}
      accessibilityRole="button"
      accessibilityLabel={`${count} ${count === 1 ? 'item' : 'items'} in cart, view cart`}
      style={({ pressed }) => [s.bar, pressed && { backgroundColor: t.accentStrong }]}
    >
      <View style={s.row}>
        <Icon name="bag" size={18} color={t.accentInk} strokeWidth={2} />
        <Text style={s.text}>{count} {count === 1 ? 'item' : 'items'} in cart</Text>
      </View>
      <View style={[s.row, { gap: 2 }]}>
        <Text style={s.text}>View</Text>
        <Icon name="chevron-right" size={17} color={t.accentInk} strokeWidth={2} />
      </View>
    </Pressable>
  )
}

const s = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  bar: {
    height: 46, borderRadius: radius.lg, backgroundColor: t.accent,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingLeft: 16, paddingRight: 14,
    shadowColor: '#000', shadowOpacity: 0.56, shadowRadius: 24, shadowOffset: { width: 0, height: 16 },
  },
  text: { fontFamily: fonts.sansBold, fontSize: font.size.callout, color: t.accentInk, fontVariant: ['tabular-nums'] },
})
