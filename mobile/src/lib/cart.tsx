import { createContext, use, useState, type PropsWithChildren } from 'react'
import type { CartItem, ListingDetail } from '@web/types'

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

export function CartProvider({ children }: PropsWithChildren) {
  const [items, setItems] = useState<CartItem[]>([])

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
