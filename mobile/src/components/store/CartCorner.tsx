import { Pressable, StyleSheet, Text } from 'react-native'
import type { DispensaryListing, PortalDispensary } from '@web/types'
import { addToCart, useCart } from '@/lib/cart'
import { Icon } from '@/components/Icon'
import { t, fonts } from '@/lib/theme'

/** The round add-to-cart button on a store's cards (the web's PhotoCorner):
 *  a resin plus, or the count once some are in the cart. */
export default function CartCorner({ listing, store }: { listing: DispensaryListing; store: PortalDispensary }) {
  const cart = useCart()
  const qty = cart.items.find(i => i.listingId === listing.id)?.quantity ?? 0
  return (
    <Pressable
      onPress={() => addToCart(cart, {
        ...listing,
        dispensary_id: store.id,
        dispensary_slug: store.slug,
        dispensary_name: store.name,
      })}
      hitSlop={6}
      accessibilityRole="button"
      accessibilityLabel={qty > 0 ? `Add another ${listing.display_name}, ${qty} in cart` : `Add ${listing.display_name} to cart`}
      style={({ pressed }) => [
        s.button,
        qty > 0 ? { backgroundColor: t.bg, borderWidth: 1.5, borderColor: t.accent } : { backgroundColor: t.accent },
        pressed && { transform: [{ scale: 0.94 }] },
      ]}
    >
      {qty > 0 ? <Text style={s.count}>{qty}</Text> : <Icon name="plus" size={16} color={t.accentInk} strokeWidth={2.25} />}
    </Pressable>
  )
}

const s = StyleSheet.create({
  button: {
    width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center',
    shadowColor: '#000', shadowOpacity: 0.35, shadowRadius: 6, shadowOffset: { width: 0, height: 2 },
  },
  count: { fontFamily: fonts.monoMedium, fontSize: 13, color: t.accent },
})
