import { useState } from 'react'
import { PixelRatio, Text, View, type StyleProp, type ViewStyle } from 'react-native'
import { Image } from 'expo-image'
import { photoAt } from '@web/utils/photoUrl'
import { t, fonts } from '@/lib/theme'

/** A brand's avatar, as on the web (components/ui BrandMark): its logo on the
 *  light plate products sit on, or its initial in the display face when there
 *  is no logo or it fails to load. */
export default function BrandMark({ name, imageUrl, size = 62, style }: {
  name: string
  imageUrl?: string | null
  size?: number
  style?: StyleProp<ViewStyle>
}) {
  const [failed, setFailed] = useState<string | null>(null)
  const pad = Math.round(size * 0.08)
  const src = imageUrl && failed !== imageUrl ? photoAt(imageUrl, (size - pad * 2) * PixelRatio.get()) ?? imageUrl : null
  return (
    <View
      style={[
        {
          width: size, height: size, borderRadius: Math.round(size * 0.24), overflow: 'hidden',
          alignItems: 'center', justifyContent: 'center',
          backgroundColor: src ? t.tile : t.surface2, borderWidth: 1, borderColor: src ? 'transparent' : t.border,
        },
        style,
      ]}
    >
      {src ? (
        <Image
          source={{ uri: src }}
          style={{ width: size - pad * 2, height: size - pad * 2 }}
          contentFit="contain"
          onError={() => setFailed(imageUrl!)}
        />
      ) : (
        <Text style={{ fontFamily: fonts.display, fontSize: Math.round(size * 0.42), color: t.text2 }}>
          {name.charAt(0).toUpperCase()}
        </Text>
      )}
    </View>
  )
}
