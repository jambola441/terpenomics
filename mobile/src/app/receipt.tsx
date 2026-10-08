import { useMemo, useState } from 'react'
import { Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native'
import { router } from 'expo-router'
import { Image } from 'expo-image'
import { SafeAreaView } from 'react-native-safe-area-context'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { pickReceipt, type ReceiptPhoto } from '@/lib/receiptImage'
import { Button, FeedState, Label, styles } from '@/components/ui'
import { t, space, font, fonts, radius, type } from '@/lib/theme'

/** Matches CLAIM_WINDOW_DAYS in connectors/receipts.py: older receipts are
 *  flagged to the reviewer, so the picker doesn't offer them. */
const DAYS_BACK = 30

function isoDay(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function recentDays(): { value: string; label: string }[] {
  const out = []
  for (let i = 0; i <= DAYS_BACK; i++) {
    const d = new Date()
    d.setDate(d.getDate() - i)
    const label = i === 0 ? 'Today' : i === 1 ? 'Yesterday' : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
    out.push({ value: isoDay(d), label })
  }
  return out
}

function Chip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        s.chip,
        pressed && { backgroundColor: t.surface3 },
        selected && { backgroundColor: t.accentTint, borderColor: t.accent },
      ]}
      accessibilityRole="button"
      accessibilityState={{ selected }}
    >
      <Text style={[s.chipText, selected && { color: t.accent, fontFamily: fonts.sansSemibold }]}>{label}</Text>
    </Pressable>
  )
}

/** Claim points for a partner purchase the POS sync couldn't match. A person
 *  reads the subtotal off the photo and approves it (/admin/receipts). */
export default function ReceiptUpload() {
  const partners = useFetch('partners', () => api.me.getPartners())
  const days = useMemo(() => recentDays(), [])
  const [partnerId, setPartnerId] = useState<string | null>(null)
  const [day, setDay] = useState(days[0].value)
  const [photo, setPhoto] = useState<ReceiptPhoto | null>(null)
  const [note, setNote] = useState('')
  const [picking, setPicking] = useState(false)
  const [busy, setBusy] = useState(false)

  async function choose(source: 'camera' | 'library') {
    setPicking(true)
    try {
      const picked = await pickReceipt(source)
      if (picked) setPhoto(picked)
    } catch (e: any) {
      Alert.alert('Could not get the photo', e?.message ?? String(e))
    } finally {
      setPicking(false)
    }
  }

  async function submit() {
    if (!partnerId || !photo) return
    setBusy(true)
    try {
      await api.me.uploadReceipt({
        partnerId,
        purchasedOn: day,
        note: note.trim() || undefined,
        image: { uri: photo.uri, type: photo.type, name: photo.name },
      })
      Alert.alert('Receipt sent', "We'll check it and add the points, usually within a day.")
      router.back()
    } catch (e: any) {
      Alert.alert('Could not upload the receipt', e?.message ?? String(e))
    } finally {
      setBusy(false)
    }
  }

  if (partners.loading || partners.error) {
    return <FeedState loading={partners.loading} error={partners.error} onRetry={partners.refresh} />
  }
  if (!partners.data?.length) return <FeedState icon="store" empty="There are no partner stores yet." />

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={{ padding: space[4], gap: space[5] }} keyboardShouldPersistTaps="handled">
        <View style={{ gap: space[2] }}>
          <Label>Store</Label>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space[2] }}>
            {partners.data.map(p => (
              <Chip key={p.id} label={p.name} selected={partnerId === p.id} onPress={() => setPartnerId(p.id)} />
            ))}
          </View>
        </View>

        <View style={{ gap: space[2] }}>
          <Label>Date of purchase</Label>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space[2] }}>
            {days.map(d => <Chip key={d.value} label={d.label} selected={day === d.value} onPress={() => setDay(d.value)} />)}
          </ScrollView>
        </View>

        <View style={{ gap: space[2] }}>
          <Label>Photo of the receipt</Label>
          {photo ? (
            <Image
              source={{ uri: photo.uri }}
              style={{ width: '100%', aspectRatio: photo.width / photo.height, maxHeight: 360, borderRadius: radius.md, backgroundColor: t.tile }}
              contentFit="contain"
              accessibilityLabel="Receipt photo"
            />
          ) : null}
          <View style={{ flexDirection: 'row', gap: space[2] }}>
            <Button title={photo ? 'Retake' : 'Take photo'} icon="camera" variant="secondary" onPress={() => choose('camera')} disabled={picking} style={{ flex: 1 }} />
            <Button title="Choose photo" icon="image" variant="secondary" onPress={() => choose('library')} disabled={picking} style={{ flex: 1 }} />
          </View>
          <Text style={styles.meta}>Make sure the store name, date and total are readable.</Text>
        </View>

        <View style={{ gap: space[2] }}>
          <Label>Note (optional)</Label>
          <TextInput
            value={note}
            onChangeText={setNote}
            maxLength={500}
            placeholder="Anything we should know"
            placeholderTextColor={t.text4}
            style={[styles.input, s.input]}
          />
        </View>

        <SafeAreaView edges={['bottom']}>
          <Button title="Submit for review" onPress={submit} loading={busy} disabled={!partnerId || !photo} />
        </SafeAreaView>
      </ScrollView>
    </KeyboardAvoidingView>
  )
}

const s = StyleSheet.create({
  chip: {
    paddingVertical: space[2],
    paddingHorizontal: space[3],
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: t.border,
    backgroundColor: t.surface2,
  },
  chipText: { ...type.body, color: t.text2 },
  input: { fontSize: font.size.callout, paddingHorizontal: space[3], minHeight: 48 },
})
