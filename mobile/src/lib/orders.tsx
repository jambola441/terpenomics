import { createContext, use, useCallback, useEffect, useRef, useState, type PropsWithChildren } from 'react'
import { AppState } from 'react-native'
import type { Order } from '@web/types'
import { api } from './api'

/** The shopper's pickup orders, held once so the Orders tab and its badge
 *  agree. Like the web portal it refetches when the app comes back to the
 *  foreground, and every 30 seconds while an order is still open, so "Ready"
 *  shows up without a pull. */
type OrdersState = {
  orders: Order[] | null
  error: string | null
  refreshing: boolean
  /** Orders the store still holds: submitted or ready. */
  openCount: number
  refresh: () => Promise<void>
  /** Put a returned order (placed or cancelled) in the list without a refetch. */
  upsert: (order: Order) => void
}

const OrdersContext = createContext<OrdersState | null>(null)

export function useOrders(): OrdersState {
  const value = use(OrdersContext)
  if (!value) throw new Error('useOrders must be used inside <OrdersProvider>')
  return value
}

const POLL_MS = 30_000
const isOpen = (o: Order) => o.status === 'submitted' || o.status === 'ready'

export function OrdersProvider({ enabled, children }: PropsWithChildren<{ enabled: boolean }>) {
  const [orders, setOrders] = useState<Order[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const live = useRef(true)

  const refresh = useCallback(async () => {
    if (!enabled) return
    setRefreshing(true)
    try {
      const next = await api.orders.list()
      if (live.current) {
        setOrders(next)
        setError(null)
      }
    } catch (e: any) {
      if (live.current) setError(e?.message ?? 'Could not load your orders.')
    } finally {
      if (live.current) setRefreshing(false)
    }
  }, [enabled])

  useEffect(() => {
    live.current = true
    // Fetched on a timer tick rather than in the effect body, so the state
    // updates land in a callback.
    const first = setTimeout(refresh, 0)
    const sub = AppState.addEventListener('change', s => { if (s === 'active') refresh() })
    return () => {
      live.current = false
      clearTimeout(first)
      sub.remove()
    }
  }, [refresh])

  const openCount = orders?.filter(isOpen).length ?? 0

  useEffect(() => {
    if (openCount === 0) return
    const id = setInterval(() => {
      if (AppState.currentState === 'active') refresh()
    }, POLL_MS)
    return () => clearInterval(id)
  }, [openCount, refresh])

  const upsert = useCallback((order: Order) => {
    setOrders(prev => {
      const rest = (prev ?? []).filter(o => o.id !== order.id)
      return [order, ...rest].sort((a, b) => b.submitted_at.localeCompare(a.submitted_at))
    })
  }, [])

  return (
    <OrdersContext.Provider value={{ orders, error, refreshing, openCount, refresh, upsert }}>
      {children}
    </OrdersContext.Provider>
  )
}
