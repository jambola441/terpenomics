import { Pressable, Text, View } from 'react-native'
import type { FeedListing } from '@web/types'
import { Price, ProductImage, StoreBullet, styles } from './ui'
import { t, space, type } from '@/lib/theme'

const WIDTH = 148

/** A feed card: photo, name, brand, price. Sized for a horizontal rail. */
export default function ListingCard({ listing, store, onPress }: {
  listing: FeedListing
  /** The store it is at, when the rail mixes stores. */
  store?: { name: string; address: string | null } | null
  onPress?: () => void
}) {
  const saving = listing.saving_cents != null && listing.saving_cents > 0 ? listing.saving_cents : null
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [{ width: WIDTH }, pressed && { opacity: 0.7 }]}
      accessibilityRole="button"
    >
      <ProductImage uri={listing.image_url} size={WIDTH} category={listing.scraped_category} />
      <Text numberOfLines={2} style={[styles.name, { marginTop: space[2] }]}>{listing.display_name}</Text>
      {listing.scraped_brand ? <Text numberOfLines={1} style={styles.meta}>{listing.scraped_brand}</Text> : null}
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: space[2], marginTop: space[1] }}>
        <Price cents={listing.price_cents} />
        {saving != null ? (
          <Text style={[type.meta, { color: t.success, fontVariant: ['tabular-nums'] }]}>
            ${Math.round(saving / 100)} under avg
          </Text>
        ) : null}
      </View>
      {store ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: space[1] }}>
          <StoreBullet name={store.name} address={store.address} size={16} />
          <Text numberOfLines={1} style={[styles.meta, { flex: 1 }]}>{store.name}</Text>
        </View>
      ) : null}
    </Pressable>
  )
}
