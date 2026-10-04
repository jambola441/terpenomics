import { useCallback, useEffect, useState } from 'react'

type Loaded<T> = { key: string; data: T | null; error: string | null }

/**
 * Load on mount and whenever `key` changes, with pull-to-refresh. `key` names
 * what `load` fetches (e.g. its URL params); `load` itself is not a dependency.
 * Screens own their data — there is no cache layer yet because nothing is
 * shared between screens.
 */
export function useFetch<T>(key: string, load: () => Promise<T>) {
  const [state, setState] = useState<Loaded<T> | null>(null)
  const [nonce, setNonce] = useState(0)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    let live = true
    load()
      .then(data => live && setState({ key, data, error: null }))
      .catch(e => live && setState(prev => ({ key, data: prev?.key === key ? prev.data : null, error: e?.message ?? String(e) })))
      .finally(() => live && setRefreshing(false))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce])

  const refresh = useCallback(() => {
    setRefreshing(true)
    setNonce(n => n + 1)
  }, [])

  const setData = useCallback((update: (prev: T | null) => T | null) => {
    setState(prev => (prev ? { ...prev, data: update(prev.data) } : prev))
  }, [])

  const current = state?.key === key ? state : null
  return {
    data: current?.data ?? null,
    error: current?.error ?? null,
    loading: current === null || (refreshing && current.error !== null),
    refreshing,
    refresh,
    setData,
  }
}
