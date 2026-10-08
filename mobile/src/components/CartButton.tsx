import { Pressable, Text, View } from 'react-native'
import { router } from 'expo-router'
import { useCart } from '@/lib/cart'
import { Icon } from '@/components/Icon'
import { t, font, fonts, radius } from '@/lib/theme'

/** Header button that opens the cart, with a count badge. */
export default function CartButton() {
  const { count } = useCart()
  return (
    <Pressable
      onPress={() => router.push('/cart')}
      hitSlop={12}
      style={{ paddingHorizontal: 8 }}
      accessibilityRole="button"
      accessibilityLabel={`Cart, ${count} item${count === 1 ? '' : 's'}`}
    >
      <Icon name="bag" color={t.text1} size={24} />
      {count > 0 ? (
        <View
          style={{
            position: 'absolute', top: -4, right: 0, minWidth: 18, height: 18, paddingHorizontal: 4,
            borderRadius: radius.pill, backgroundColor: t.accent, alignItems: 'center', justifyContent: 'center',
          }}
        >
          <Text style={{ color: t.accentInk, fontSize: font.size.caption, fontFamily: fonts.sansBold, fontVariant: ['tabular-nums'] }}>
            {count}
          </Text>
        </View>
      ) : null}
    </Pressable>
  )
}
