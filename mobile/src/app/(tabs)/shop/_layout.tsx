import { Stack } from 'expo-router'
import { font, fonts, t } from '@/lib/theme'

/** Shop: categories and brands share a header (components/ShopHeader) and
 *  switch in place; a category, a brand and search push on top, as on the web
 *  (CategoriesPage, BrandsPage, CategoryView, BrandView, SearchView). */
export default function ShopLayout() {
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: t.bg },
        headerTintColor: t.text1,
        headerTitleStyle: { fontFamily: fonts.display, fontSize: font.size.heading, color: t.text1 },
        headerShadowVisible: false,
        headerBackButtonDisplayMode: 'minimal',
        contentStyle: { backgroundColor: t.bg },
      }}
    >
      <Stack.Screen name="index" options={{ headerShown: false }} />
      <Stack.Screen name="brands" options={{ headerShown: false, animation: 'none' }} />
      <Stack.Screen name="search" options={{ title: 'Search' }} />
      <Stack.Screen name="[category]" options={{ title: '' }} />
      <Stack.Screen name="brand/[name]" options={{ title: '' }} />
    </Stack>
  )
}
