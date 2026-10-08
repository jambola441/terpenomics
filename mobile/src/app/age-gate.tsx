import { useState } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useAuth } from '@/lib/auth'
import { Button, Label } from '@/components/ui'
import { Logo } from '@/components/Icon'
import { t, space, type } from '@/lib/theme'

/** Asked once per device, before anything else. */
export default function AgeGate() {
  const { confirmAge } = useAuth()
  const [refused, setRefused] = useState(false)

  return (
    <SafeAreaView style={s.screen}>
      <View style={s.body}>
        <Logo size={32} style={s.logo} />
        <Label>New York · 21+</Label>
        {refused ? (
          <>
            <Text style={type.display} accessibilityRole="header">Sorry, you have to be 21 or older</Text>
            <Text style={s.copy}>Terpenomics is only for adults of legal age to buy cannabis in New York.</Text>
            <Button title="I made a mistake" variant="secondary" onPress={() => setRefused(false)} />
          </>
        ) : (
          <>
            <Text style={type.display} accessibilityRole="header">Are you 21 or older?</Text>
            <Text style={s.copy}>You must be of legal age to view cannabis products and reserve them for pickup.</Text>
            <Button title="Yes, I'm 21 or older" onPress={confirmAge} />
            <Button title="No" variant="secondary" onPress={() => setRefused(true)} />
          </>
        )}
      </View>
    </SafeAreaView>
  )
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: t.bg },
  body: { flex: 1, justifyContent: 'center', padding: space[6], gap: space[4] },
  logo: { marginBottom: space[7] },
  copy: { ...type.copy, marginBottom: space[4] },
})
