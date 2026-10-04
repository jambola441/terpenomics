import { Stack } from 'expo-router'
import { StatusBar } from 'expo-status-bar'
import { AuthProvider, useAuth } from '@/lib/auth'
import { FeedState } from '@/components/ui'
import { t } from '@/lib/theme'

function RootNavigator() {
  const { session } = useAuth()
  if (session === undefined) return <FeedState loading />

  const signedIn = session !== null
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: t.bg },
        headerTintColor: t.text1,
        contentStyle: { backgroundColor: t.bg },
      }}
    >
      <Stack.Protected guard={signedIn}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="listing/[dispensaryId]/[listingId]" options={{ title: '', headerBackButtonDisplayMode: 'minimal' }} />
      </Stack.Protected>
      <Stack.Protected guard={!signedIn}>
        <Stack.Screen name="sign-in" options={{ headerShown: false }} />
      </Stack.Protected>
    </Stack>
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
