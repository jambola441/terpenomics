import { useEffect } from 'react'
import { Stack } from 'expo-router'
import { StatusBar } from 'expo-status-bar'
import { useFonts } from 'expo-font'
// One face per family, imported by path so only these seven TTFs are bundled
// (each package's root index pulls in every weight and italic).
import { Fraunces_600SemiBold } from '@expo-google-fonts/fraunces/600SemiBold'
import { PublicSans_400Regular } from '@expo-google-fonts/public-sans/400Regular'
import { PublicSans_500Medium } from '@expo-google-fonts/public-sans/500Medium'
import { PublicSans_600SemiBold } from '@expo-google-fonts/public-sans/600SemiBold'
import { PublicSans_700Bold } from '@expo-google-fonts/public-sans/700Bold'
import { IBMPlexMono_400Regular } from '@expo-google-fonts/ibm-plex-mono/400Regular'
import { IBMPlexMono_500Medium } from '@expo-google-fonts/ibm-plex-mono/500Medium'
import { AuthProvider, useAuth } from '@/lib/auth'
import { CartProvider } from '@/lib/cart'
import CartButton from '@/components/CartButton'
import { View } from 'react-native'
import { Button, FeedState } from '@/components/ui'
import { font, fonts, space, t } from '@/lib/theme'

/** Registered under the names lib/theme's `fonts` map hands out. */
const FONT_ASSETS = {
  [fonts.display]: Fraunces_600SemiBold,
  [fonts.sans]: PublicSans_400Regular,
  [fonts.sansMedium]: PublicSans_500Medium,
  [fonts.sansSemibold]: PublicSans_600SemiBold,
  [fonts.sansBold]: PublicSans_700Bold,
  [fonts.mono]: IBMPlexMono_400Regular,
  [fonts.monoMedium]: IBMPlexMono_500Medium,
}

function RootNavigator() {
  const { session, ageConfirmed, profile, profileError, reloadProfile, signOut } = useAuth()
  if (session === undefined || ageConfirmed === undefined) return <FeedState loading />

  const signedIn = session !== null
  if (signedIn && profile === undefined) return <FeedState loading />
  if (signedIn && profile === null) {
    return (
      <View style={{ flex: 1, backgroundColor: t.bg }}>
        <FeedState error={profileError ?? 'Could not load your account'} onRetry={reloadProfile} />
        <Button title="Sign out" variant="secondary" onPress={signOut} style={{ margin: space[6] }} />
      </View>
    )
  }
  // Sign-up is a server-side state: the API refuses orders until it is done,
  // and a terms change can send a signed-up customer back through it.
  const signedUp = !!profile?.onboarding.complete
  // Keyed by user so signing out (or in as someone else) starts an empty cart.
  return (
    <CartProvider key={session?.user.id ?? 'signed-out'} userId={session?.user.id}>
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: t.bg },
        headerTintColor: t.text1,
        headerTitleStyle: { fontFamily: fonts.display, fontSize: font.size.heading, color: t.text1 },
        headerShadowVisible: false,
        contentStyle: { backgroundColor: t.bg },
      }}
    >
      <Stack.Protected guard={!ageConfirmed}>
        <Stack.Screen name="age-gate" options={{ headerShown: false }} />
      </Stack.Protected>
      <Stack.Protected guard={ageConfirmed && !signedIn}>
        <Stack.Screen name="sign-in" options={{ headerShown: false }} />
      </Stack.Protected>
      <Stack.Protected guard={ageConfirmed && signedIn && !signedUp}>
        <Stack.Screen name="sign-up" options={{ headerShown: false }} />
      </Stack.Protected>
      <Stack.Protected guard={ageConfirmed && signedIn && signedUp}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen
          name="listing/[dispensaryId]/[listingId]"
          options={{ title: '', headerBackButtonDisplayMode: 'minimal', headerRight: () => <CartButton /> }}
        />
        <Stack.Screen name="cart" options={{ presentation: 'modal', title: 'Your cart' }} />
        <Stack.Screen name="receipt" options={{ presentation: 'modal', title: 'Upload a receipt' }} />
      </Stack.Protected>
    </Stack>
    </CartProvider>
  )
}

export default function RootLayout() {
  // Until the faces are registered, text would flash in the system font, so
  // hold the loading state. If they fail, carry on: an unknown family falls
  // back to the system font on both platforms, which beats a blank app.
  const [fontsLoaded, fontError] = useFonts(FONT_ASSETS)
  useEffect(() => {
    if (fontError) console.warn('Fonts failed to load; using system fonts.', fontError)
  }, [fontError])

  return (
    <AuthProvider>
      <StatusBar style="light" />
      {fontsLoaded || fontError ? <RootNavigator /> : <FeedState loading />}
    </AuthProvider>
  )
}
