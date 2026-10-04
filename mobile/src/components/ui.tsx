import type { ReactNode } from 'react'
import { ActivityIndicator, Pressable, StyleSheet, Text, View, type ViewStyle } from 'react-native'
import { Image } from 'expo-image'
import { formatDollars } from '@web/utils/format'
import { t, radius, space, font } from '@/lib/theme'

/** Loading / error / empty, in one place so every screen fails the same way. */
export function FeedState({ loading, error, empty, onRetry }: {
  loading?: boolean
  error?: string | null
  empty?: string | null
  onRetry?: () => void
}) {
  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={t.accent} />
      </View>
    )
  }
  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.muted}>{error}</Text>
        {onRetry && <Button title="Try again" onPress={onRetry} variant="ghost" style={{ marginTop: space[4] }} />}
      </View>
    )
  }
  if (empty) {
    return (
      <View style={styles.center}>
        <Text style={styles.muted}>{empty}</Text>
      </View>
    )
  }
  return null
}

export function Button({ title, onPress, disabled, loading, variant = 'primary', style }: {
  title: string
  onPress: () => void
  disabled?: boolean
  loading?: boolean
  variant?: 'primary' | 'ghost' | 'danger'
  style?: ViewStyle
}) {
  const primary = variant === 'primary'
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.button,
        primary ? { backgroundColor: t.accent } : { borderWidth: 1, borderColor: t.borderStrong },
        (disabled || loading) && { opacity: 0.5 },
        pressed && { opacity: 0.8 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={primary ? t.accentInk : t.text1} />
      ) : (
        <Text style={[styles.buttonText, { color: primary ? t.accentInk : variant === 'danger' ? t.danger : t.text1 }]}>
          {title}
        </Text>
      )}
    </Pressable>
  )
}

export function Price({ cents }: { cents: number | null | undefined }) {
  return <Text style={styles.price}>{cents == null ? '—' : formatDollars(cents)}</Text>
}

/** Product photos sit on a light square plate, as on the web. */
export function ProductImage({ uri, size }: { uri: string | null | undefined; size: number }) {
  return (
    <View style={[styles.tile, { width: size, height: size }]}>
      {uri ? <Image source={{ uri }} style={{ width: size - 8, height: size - 8 }} contentFit="contain" /> : null}
    </View>
  )
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <Text style={styles.sectionTitle}>{children}</Text>
}

export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: t.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space[7], backgroundColor: t.bg },
  muted: { color: t.text3, fontSize: font.size.body, textAlign: 'center', lineHeight: 20 },
  button: {
    minHeight: 48,
    borderRadius: radius.lg,
    paddingHorizontal: space[5],
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonText: { fontSize: font.size.callout, fontWeight: font.weight.bold },
  price: { color: t.text1, fontSize: font.size.body, fontWeight: font.weight.bold },
  tile: { backgroundColor: t.tile, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  sectionTitle: {
    color: t.text1,
    fontSize: font.size.title,
    fontWeight: font.weight.heavy,
    paddingHorizontal: space[4],
    marginTop: space[6],
    marginBottom: space[3],
  },
  card: { backgroundColor: t.surface1, borderRadius: radius.lg, borderWidth: 1, borderColor: t.border },
  name: { color: t.text1, fontSize: font.size.body, fontWeight: font.weight.semibold },
  meta: { color: t.text3, fontSize: font.size.small },
})
