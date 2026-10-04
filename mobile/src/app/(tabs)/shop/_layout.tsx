import { Stack } from 'expo-router'
import CartButton from '@/components/CartButton'
import { t } from '@/lib/theme'

export default function ShopLayout() {
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: t.bg },
        headerTintColor: t.text1,
        headerShadowVisible: false,
        headerRight: () => <CartButton />,
        contentStyle: { backgroundColor: t.bg },
      }}
    >
      <Stack.Screen name="index" options={{ title: 'Shop' }} />
      <Stack.Screen name="[category]" options={{ title: '' }} />
    </Stack>
  )
}
