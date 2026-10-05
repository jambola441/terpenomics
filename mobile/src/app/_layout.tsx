import { Stack } from 'expo-router'
import { StatusBar } from 'expo-status-bar'
import { AuthProvider, useAuth } from '@/lib/auth'
import { CartProvider } from '@/lib/cart'
import CartButton from '@/components/CartButton'
import { View } from 'react-native'
import { Button, FeedState } from '@/components/ui'
import { space, t } from '@/lib/theme'

function RootNavigator() {
  const { session, ageConfirmed, profile, profileError, reloadProfile, signOut } = useAuth()
  if (session === undefined || ageConfirmed === undefined) return <FeedState loading />

  const signedIn = session !== null
  if (signedIn && profile === undefined) return <FeedState loading />
  if (signedIn && profile === null) {
    return (
      <View style={{ flex: 1, backgroundColor: t.bg }}>
        <FeedState error={profileError ?? 'Could not load your account'} onRetry={reloadProfile} />
        <Button title="Sign out" variant="ghost" onPress={signOut} style={{ margin: space[6] }} />
      </View>
    )
  }
  // Sign-up is a server-side state: the API refuses orders until it is done,
  // and a terms change can send a signed-up customer back through it.
  const signedUp = !!profile?.onboarding.complete
  // Keyed by user so signing out (or in as someone else) starts an empty cart.
  return (
    <CartProvider key={session?.user.id ?? 'signed-out'}>
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: t.bg },
        headerTintColor: t.text1,
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
  return (
    <AuthProvider>
      <StatusBar style="light" />
      <RootNavigator />
    </AuthProvider>
  )
}
