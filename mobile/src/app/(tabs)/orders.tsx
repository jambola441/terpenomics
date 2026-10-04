import { useState } from 'react'
import { Alert, FlatList, RefreshControl } from 'react-native'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import OrderCard from '@/components/OrderCard'
import { FeedState, styles } from '@/components/ui'
import { t, space } from '@/lib/theme'

export default function Orders() {
  const { data, setData, error, loading, refreshing, refresh } = useFetch('orders', () => api.orders.list())
  const [cancelling, setCancelling] = useState<string | null>(null)

  function confirmCancel(orderId: string) {
    Alert.alert('Cancel this order?', 'The store will be told not to hold it for you.', [
      { text: 'Keep it', style: 'cancel' },
      {
        text: 'Cancel order',
        style: 'destructive',
        onPress: async () => {
          setCancelling(orderId)
          try {
            const updated = await api.orders.cancel(orderId)
            setData(prev => prev?.map(o => (o.id === orderId ? updated : o)) ?? prev)
          } catch (e: any) {
            Alert.alert('Could not cancel that order', e?.message ?? String(e))
          } finally {
            setCancelling(null)
          }
        },
      },
    ])
  }

  if (loading || error) return <FeedState loading={loading} error={error} onRetry={refresh} />

  return (
    <FlatList
      style={styles.screen}
      data={data ?? []}
      keyExtractor={o => o.id}
      contentContainerStyle={{ padding: space[4], gap: space[3], flexGrow: 1 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={t.accent} />}
      ListEmptyComponent={<FeedState empty="No orders yet. Reserve something for pickup and it shows up here." />}
      renderItem={({ item }) => (
        <OrderCard order={item} cancelling={cancelling === item.id} onCancel={() => confirmCancel(item.id)} />
      )}
    />
  )
}
