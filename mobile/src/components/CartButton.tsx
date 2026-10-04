import { Pressable, Text, View } from 'react-native'
import { router } from 'expo-router'
import { SymbolView } from 'expo-symbols'
import { useCart } from '@/lib/cart'
import { t, font, radius } from '@/lib/theme'

/** Header button that opens the cart, with a count badge. */
export default function CartButton() {
  const { count } = useCart()
  return (
    <Pressable onPress={() => router.push('/cart')} hitSlop={12} style={{ paddingHorizontal: 8 }} accessibilityLabel={`Cart, ${count} items`}>
      <SymbolView name={{ ios: 'cart', android: 'shopping_cart' }} tintColor={t.text1} size={24} />
      {count > 0 ? (
        <View
          style={{
            position: 'absolute', top: -4, right: 0, minWidth: 18, height: 18, paddingHorizontal: 4,
            borderRadius: radius.pill, backgroundColor: t.accent, alignItems: 'center', justifyContent: 'center',
          }}
        >
          <Text style={{ color: t.accentInk, fontSize: font.size.caption, fontWeight: font.weight.heavy }}>{count}</Text>
        </View>
      ) : null}
    </Pressable>
  )
}
