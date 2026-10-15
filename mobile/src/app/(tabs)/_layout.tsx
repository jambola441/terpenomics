import { Tabs } from 'expo-router'
import TabBar from '@/components/TabBar'
import { t } from '@/lib/theme'

/** Home · Shop · Map · Orders · You, as on the web portal (CustomerPortal's TABS).
 *  Points lives under You there, and does here. Each tab draws its own title
 *  (components/ui PageTitle) instead of a native header, and the nav is the
 *  web's floating bar (components/TabBar). */
export default function TabsLayout() {
  return (
    <Tabs
      tabBar={props => <TabBar {...props} />}
      screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: t.bg } }}
    >
      <Tabs.Screen name="index" options={{ title: 'Home' }} />
      <Tabs.Screen name="shop" options={{ title: 'Shop' }} />
      <Tabs.Screen name="map" options={{ title: 'Map' }} />
      <Tabs.Screen name="orders" options={{ title: 'Orders' }} />
      <Tabs.Screen name="profile" options={{ title: 'You' }} />
    </Tabs>
  )
}
