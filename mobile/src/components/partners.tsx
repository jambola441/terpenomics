import { useEffect, useState } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import { Image } from 'expo-image'
import * as Location from 'expo-location'
import type { PointsProgram } from '@web/types'
import type { Position } from '@web/utils/partnerPlaces'
import { steps } from '@web/utils/pointsProgram'
import { t, space, font, fonts, type } from '@/lib/theme'

/** A partner's logo on the light plate, or its initial when it has none. */
export function PartnerMark({ name, uri, size = 52 }: { name: string; uri?: string | null; size?: number }) {
  const [failed, setFailed] = useState(false)
  const photo = uri && !failed
  return (
    <View style={[s.mark, { width: size, height: size, borderRadius: Math.round(size * 0.24) },
      photo ? { backgroundColor: t.tile, borderColor: 'transparent' } : null]}>
      {photo ? (
        <Image
          source={{ uri }}
          style={{ width: size * 0.84, height: size * 0.84 }}
          contentFit="contain"
          onError={() => setFailed(true)}
        />
      ) : (
        <Text style={{ fontFamily: fonts.display, fontSize: Math.round(size * 0.42), color: t.text2 }}>
          {name.charAt(0).toUpperCase()}
        </Text>
      )}
    </View>
  )
}

/** The three numbered steps of earning points (words shared with the web). */
export function PointsSteps({ program, compact = false }: { program: PointsProgram; compact?: boolean }) {
  return (
    <View style={{ gap: compact ? space[3] : space[5] }}>
      {steps(program).map((step, i) => (
        <View key={step.title} style={{ flexDirection: 'row', gap: space[3], alignItems: 'flex-start' }}>
          <View style={s.stepDisc}>
            <Text style={{ fontFamily: fonts.mono, fontSize: font.size.small, color: t.accent }}>{i + 1}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={[type.bodyStrong, { fontSize: font.size.callout }]}>{step.title}</Text>
            {!compact && <Text style={[type.copy, { marginTop: 2 }]}>{step.body}</Text>}
          </View>
        </View>
      ))}
    </View>
  )
}

/**
 * Where the shopper is, for "nearest first": only if they already let Terpee use
 * their location (it asks when an order is placed). Never asks from here; null
 * otherwise, and the list stays A–Z.
 */
export function useKnownPosition(): Position | null {
  const [pos, setPos] = useState<Position | null>(null)
  useEffect(() => {
    let live = true
    ;(async () => {
      try {
        const { status } = await Location.getForegroundPermissionsAsync()
        if (status !== 'granted') return
        const last = await Location.getLastKnownPositionAsync({ maxAge: 30 * 60 * 1000 })
        if (live && last) setPos({ lat: last.coords.latitude, lng: last.coords.longitude })
      } catch {
        // No position: A–Z it is.
      }
    })()
    return () => {
      live = false
    }
  }, [])
  return pos
}

const s = StyleSheet.create({
  mark: {
    alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
    backgroundColor: t.surface2, borderWidth: 1, borderColor: t.border,
  },
  stepDisc: {
    width: 26, height: 26, borderRadius: 13, marginTop: 1,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: t.accentTint, borderWidth: 1, borderColor: t.accentDim,
  },
})

