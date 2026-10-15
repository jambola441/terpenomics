import { useCallback, useRef, useState } from 'react'
import { Alert, FlatList, RefreshControl } from 'react-native'
import { useFocusEffect } from 'expo-router'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { api } from '@/lib/api'
import { useOrders } from '@/lib/orders'
import OrderCard from '@/components/OrderCard'
import { FeedState, PageTitle, styles } from '@/components/ui'
import { t, space } from '@/lib/theme'

/** The Orders tab, as on the web (components/OrdersScreen.tsx): the pickup
 *  code is what a shopper shows at the counter, so orders get a tab of their
 *  own. The list is shared with the tab bar's badge (lib/orders). */
export default function Orders() {
  const insets = useSafeAreaInsets()
  const { orders, error, refreshing, openCount, refresh, upsert } = useOrders()
  const [cancelling, setCancelling] = useState<string | null>(null)

  // Coming back to the tab refreshes, beside the foreground and 30s polls.
  const focused = useRef(false)
  useFocusEffect(
    useCallback(() => {
      if (focused.current) refresh()
      focused.current = true
    }, [refresh]),
  )

  function confirmCancel(orderId: string) {
    Alert.alert('Cancel this order?', 'The store will be told not to hold it for you.', [
      { text: 'Keep it', style: 'cancel' },
      {
        text: 'Cancel order',
        style: 'destructive',
        onPress: async () => {
          setCancelling(orderId)
          try {
            upsert(await api.orders.cancel(orderId))
          } catch (e: any) {
            Alert.alert('Could not cancel that order', e?.message ?? String(e))
          } finally {
            setCancelling(null)
          }
        },
      },
    ])
  }

  const header = (
    <PageTitle
      style={{ paddingBottom: space[3] }}
      sub={openCount > 0 ? `${openCount} open · show the code at the counter` : 'Pickup orders and their codes'}
    >
      Orders
    </PageTitle>
  )

  if (orders === null) {
    return (
      <FeedState
        loading={!error}
        error={error}
        onRetry={refresh}
        style={{ paddingTop: insets.top }}
      />
    )
  }

  return (
    <FlatList
      style={styles.screen}
      data={orders}
      keyExtractor={o => o.id}
      contentContainerStyle={{ padding: space[4], paddingTop: insets.top + 26, gap: space[3], flexGrow: 1 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={t.text3} />}
      ListHeaderComponent={header}
      ListEmptyComponent={
        <FeedState
          icon="bag"
          empty="No orders yet"
          hint="Orders you place for pickup show up here with their pickup code."
        />
      }
      renderItem={({ item }) => (
        <OrderCard order={item} cancelling={cancelling === item.id} onCancel={() => confirmCancel(item.id)} />
      )}
    />
  )
}
