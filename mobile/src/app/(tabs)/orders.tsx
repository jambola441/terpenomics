import { useCallback, useRef, useState } from 'react'
import { FlatList, RefreshControl } from 'react-native'
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
  const [cancelling, setCancelling] = useState<Set<string>>(new Set())
  // A failed cancel shows on that order's card, not as an alert.
  const [cancelErrors, setCancelErrors] = useState<Record<string, string>>({})

  // Coming back to the tab refreshes, beside the foreground and 30s polls.
  const focused = useRef(false)
  useFocusEffect(
    useCallback(() => {
      if (focused.current) refresh()
      focused.current = true
    }, [refresh]),
  )

  // The card asks "Cancel this order?" itself; by here the shopper said yes.
  async function cancel(orderId: string) {
    setCancelling(prev => new Set(prev).add(orderId))
    setCancelErrors(({ [orderId]: _, ...rest }) => rest)
    try {
      upsert(await api.orders.cancel(orderId))
    } catch (e: unknown) {
      setCancelErrors(prev => ({ ...prev, [orderId]: (e instanceof Error && e.message) || 'Could not cancel that order.' }))
    } finally {
      setCancelling(prev => {
        const next = new Set(prev)
        next.delete(orderId)
        return next
      })
    }
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
        <OrderCard
          order={item}
          cancelling={cancelling.has(item.id)}
          cancelError={cancelErrors[item.id] ?? null}
          onCancel={() => cancel(item.id)}
        />
      )}
    />
  )
}
