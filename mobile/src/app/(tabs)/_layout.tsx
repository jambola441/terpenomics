import { Tabs } from 'expo-router'
import { SymbolView, type SymbolViewProps } from 'expo-symbols'
import type { ColorValue } from 'react-native'
import CartButton from '@/components/CartButton'
import { t } from '@/lib/theme'

function TabIcon({ name, color }: { name: SymbolViewProps['name']; color: ColorValue }) {
  return <SymbolView name={name} tintColor={color} size={24} />
}

function icon(name: SymbolViewProps['name']) {
  return function TabBarIcon({ color }: { color: ColorValue }) {
    return <TabIcon name={name} color={color} />
  }
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: t.bg },
        headerTintColor: t.text1,
        headerShadowVisible: false,
        headerRight: () => <CartButton />,
        tabBarStyle: { backgroundColor: t.bg, borderTopColor: t.border },
        tabBarActiveTintColor: t.accent,
        tabBarInactiveTintColor: t.text3,
        sceneStyle: { backgroundColor: t.bg },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Home', tabBarIcon: icon({ ios: 'house.fill', android: 'home' }) }} />
      <Tabs.Screen
        name="shop"
        options={{ title: 'Shop', headerShown: false, tabBarIcon: icon({ ios: 'square.grid.2x2.fill', android: 'grid_view' }) }}
      />
      <Tabs.Screen name="orders" options={{ title: 'Orders', tabBarIcon: icon({ ios: 'bag.fill', android: 'shopping_bag' }) }} />
      <Tabs.Screen name="profile" options={{ title: 'You', tabBarIcon: icon({ ios: 'person.fill', android: 'person' }) }} />
    </Tabs>
  )
}
