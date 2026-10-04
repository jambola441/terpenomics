import { Pressable, Text, View } from 'react-native'
import type { FeedListing } from '@web/types'
import { Price, ProductImage, styles } from './ui'
import { t, space, font } from '@/lib/theme'

const WIDTH = 148

/** A feed card: photo, name, brand, price. Sized for a horizontal rail. */
export default function ListingCard({ listing, storeName, onPress }: {
  listing: FeedListing
  storeName?: string | null
  onPress?: () => void
}) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [{ width: WIDTH }, pressed && { opacity: 0.7 }]}>
      <ProductImage uri={listing.image_url} size={WIDTH} />
      <Text numberOfLines={2} style={[styles.name, { marginTop: space[2] }]}>{listing.display_name}</Text>
      {listing.scraped_brand ? <Text numberOfLines={1} style={styles.meta}>{listing.scraped_brand}</Text> : null}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space[2], marginTop: space[1] }}>
        <Price cents={listing.price_cents} />
        {listing.saving_cents != null && listing.saving_cents > 0 ? (
          <Text style={{ color: t.accent, fontSize: font.size.caption, fontWeight: font.weight.bold }}>
            ${Math.round(listing.saving_cents / 100)} under avg
          </Text>
        ) : null}
      </View>
      {storeName ? <Text numberOfLines={1} style={styles.meta}>{storeName}</Text> : null}
    </Pressable>
  )
}
