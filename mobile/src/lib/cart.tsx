import { createContext, use, useEffect, useState, type PropsWithChildren } from 'react'
import { Platform } from 'react-native'
import type { CartItem, ListingDetail } from '@web/types'
import { keychainStorage } from './supabase'

// Mirrors the limits in routes/orders.py, so the app stops the shopper before
// the backend has to reject the order.
export const MAX_QTY_PER_LINE = 12
export const MAX_LINES = 40

/** One cart, one store: an order is placed with a single dispensary, so the
 *  cart can only ever hold one store's items. */
type CartState = {
  items: CartItem[]
  count: number
  totalCents: number
  /** 'other-store' means nothing was added; the caller asks before replacing. */
  add: (listing: ListingDetail) => 'added' | 'other-store' | 'full'
  replaceWith: (listing: ListingDetail) => void
  setQuantity: (listingId: string, quantity: number) => void
  remove: (listingId: string) => void
  clear: () => void
}

const CartContext = createContext<CartState | null>(null)

export function useCart(): CartState {
  const value = use(CartContext)
  if (!value) throw new Error('useCart must be used inside <CartProvider>')
  return value
}

function toItem(l: ListingDetail): CartItem {
  return {
    listingId: l.id,
    dispensaryId: l.dispensary_id,
    dispensarySlug: l.dispensary_slug,
    dispensaryName: l.dispensary_name,
    name: l.display_name,
    brand: l.scraped_brand ?? null,
    variant: l.variant ?? null,
    price_cents: l.price_cents ?? null,
    url: l.url ?? null,
    image_url: l.image_url ?? null,
    quantity: 1,
  }
}

/* The cart is saved per shopper on the device, so closing the app, or the
   system killing it in the background, doesn't empty it. Prices and stock are
   checked again when the order is placed; a cart older than a day is dropped
   rather than shown with prices that may have moved. Same rule as the web. */
const CART_TTL_MS = 24 * 60 * 60 * 1000
const cartKey = (userId: string) => `terpee.cart.${userId}`
const cartStorage = Platform.OS === 'web'
  ? {
      getItem: async (k: string) => globalThis.localStorage?.getItem(k) ?? null,
      setItem: async (k: string, v: string) => globalThis.localStorage?.setItem(k, v),
      removeItem: async (k: string) => globalThis.localStorage?.removeItem(k),
    }
  : keychainStorage

async function readCart(userId: string): Promise<CartItem[]> {
  try {
    const saved = JSON.parse((await cartStorage.getItem(cartKey(userId))) ?? 'null')
    if (!saved || !Array.isArray(saved.items) || Date.now() - saved.savedAt > CART_TTL_MS) return []
    return saved.items
  } catch {
    return []
  }
}

function writeCart(userId: string, items: CartItem[]) {
  const write = items.length
    ? cartStorage.setItem(cartKey(userId), JSON.stringify({ savedAt: Date.now(), items }))
    : cartStorage.removeItem(cartKey(userId))
  // A failed save leaves the cart working for this session; nothing to tell the shopper.
  write.catch(() => {})
}

/** Mounted per signed-in user (the layout keys it on the user id). */
export function CartProvider({ userId, children }: PropsWithChildren<{ userId?: string }>) {
  const [items, setItems] = useState<CartItem[]>([])
  // Nothing is saved until the saved cart has been read, so an empty first
  // render can't overwrite it.
  const [loaded, setLoaded] = useState(!userId)

  useEffect(() => {
    if (!userId) return
    let cancelled = false
    readCart(userId).then(saved => {
      if (cancelled) return
      // Something added in the moment before the read finished wins.
      setItems(current => (current.length ? current : saved))
      setLoaded(true)
    })
    return () => { cancelled = true }
  }, [userId])

  useEffect(() => {
    if (userId && loaded) writeCart(userId, items)
  }, [userId, loaded, items])

  function add(l: ListingDetail): 'added' | 'other-store' | 'full' {
    if (items.length && items[0].dispensaryId !== l.dispensary_id) return 'other-store'
    const existing = items.find(i => i.listingId === l.id)
    if (existing ? existing.quantity >= MAX_QTY_PER_LINE : items.length >= MAX_LINES) return 'full'
    setItems(prev =>
      existing
        ? prev.map(i => (i.listingId === l.id ? { ...i, quantity: i.quantity + 1 } : i))
        : [...prev, toItem(l)],
    )
    return 'added'
  }

  function setQuantity(listingId: string, quantity: number) {
    const q = Math.min(quantity, MAX_QTY_PER_LINE)
    setItems(prev => (q <= 0 ? prev.filter(i => i.listingId !== listingId) : prev.map(i => (i.listingId === listingId ? { ...i, quantity: q } : i))))
  }

  const value: CartState = {
    items,
    count: items.reduce((n, i) => n + i.quantity, 0),
    totalCents: items.reduce((n, i) => n + (i.price_cents ?? 0) * i.quantity, 0),
    add,
    replaceWith: l => setItems([toItem(l)]),
    setQuantity,
    remove: listingId => setItems(prev => prev.filter(i => i.listingId !== listingId)),
    clear: () => setItems([]),
  }
  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}
