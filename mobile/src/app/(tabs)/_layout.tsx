import { Tabs } from 'expo-router'
import type { ColorValue } from 'react-native'
import CartButton from '@/components/CartButton'
import { Icon, type IconName } from '@/components/Icon'
import { font, fonts, t } from '@/lib/theme'

function icon(name: IconName) {
  return function TabBarIcon({ color }: { color: ColorValue }) {
    return <Icon name={name} color={color} size={24} />
  }
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: t.bg },
        headerTintColor: t.text1,
        headerTitleStyle: { fontFamily: fonts.display, fontSize: font.size.heading, color: t.text1 },
        headerShadowVisible: false,
        headerRight: () => <CartButton />,
        tabBarStyle: { backgroundColor: t.bg, borderTopColor: t.border, borderTopWidth: 1 },
        tabBarActiveTintColor: t.accent,
        tabBarInactiveTintColor: t.text3,
        tabBarLabelStyle: { fontFamily: fonts.sansMedium, fontSize: font.size.caption },
        sceneStyle: { backgroundColor: t.bg },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Home', tabBarIcon: icon('home') }} />
      <Tabs.Screen name="shop" options={{ title: 'Shop', headerShown: false, tabBarIcon: icon('grid') }} />
      <Tabs.Screen name="orders" options={{ title: 'Orders', tabBarIcon: icon('bag') }} />
      <Tabs.Screen name="points" options={{ title: 'Points', tabBarIcon: icon('drop') }} />
      <Tabs.Screen name="profile" options={{ title: 'You', tabBarIcon: icon('user') }} />
    </Tabs>
  )
}
