import { useLocalSearchParams } from 'expo-router'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { FeedState } from '@/components/ui'
import StoreMenu from '@/components/store/StoreMenu'
import AisleView from '@/components/store/AisleView'

/** A store's page, or one of its aisles: the web's StoreScreen. Home's See
 *  all, a listing's Menu, and the map open it over whatever tab they are in. */
export default function StoreScreen() {
  const { dispensaryId, aisle } = useLocalSearchParams<{ dispensaryId: string; aisle?: string }>()
  // The store list is small and is what the map draws too.
  const { data, error, loading, refresh } = useFetch('dispensaries', () => api.portal.getDispensaries())
  const store = data?.find(d => d.id === dispensaryId) ?? null

  if (loading || error) return <FeedState loading={loading} error={error ? "Couldn't load this store." : null} onRetry={refresh} />
  if (!store) return <FeedState empty="This store isn't on Terpee any more." icon="store" />
  return aisle
    ? <AisleView key={`${store.id}/${aisle}`} store={store} category={aisle} />
    : <StoreMenu key={store.id} store={store} />
}
