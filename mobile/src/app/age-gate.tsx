import { useState } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui'
import { t, space, font } from '@/lib/theme'

/** Asked once per device, before anything else. */
export default function AgeGate() {
  const { confirmAge } = useAuth()
  const [refused, setRefused] = useState(false)

  return (
    <SafeAreaView style={s.screen}>
      <View style={s.body}>
        <Text style={s.brand}>terpenomics</Text>
        {refused ? (
          <>
            <Text style={s.title}>Sorry, you have to be 21 or older</Text>
            <Text style={s.copy}>Terpenomics is only for adults of legal age to buy cannabis in New York.</Text>
            <Button title="I made a mistake" variant="ghost" onPress={() => setRefused(false)} />
          </>
        ) : (
          <>
            <Text style={s.title}>Are you 21 or older?</Text>
            <Text style={s.copy}>You must be of legal age to view cannabis products and reserve them for pickup.</Text>
            <Button title="Yes, I'm 21 or older" onPress={confirmAge} />
            <Button title="No" variant="ghost" onPress={() => setRefused(true)} />
          </>
        )}
      </View>
    </SafeAreaView>
  )
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: t.bg },
  body: { flex: 1, justifyContent: 'center', padding: space[6], gap: space[4] },
  brand: { color: t.accent, fontSize: font.size.hero, fontWeight: font.weight.heavy, marginBottom: space[6] },
  title: { color: t.text1, fontSize: font.size.display, fontWeight: font.weight.heavy },
  copy: { color: t.text2, fontSize: font.size.callout, lineHeight: 22, marginBottom: space[4] },
})
