/* ============================================================================
   StoreScreen — a store's page, or one of its aisles, outside the Map tab.

   Home's "See all" and a listing's "Menu" used to open the store under Map,
   so the nav jumped to Map and Back landed somewhere the shopper never was.
   This holds the same store page inside whichever tab it was opened from.
   ========================================================================== */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import type { CartItem, PortalDispensary } from '../types'
import { t } from '../theme'
import { FeedState } from './ui'
import DispensaryListings from './DispensaryListings'
import AisleView from './AisleView'

export default function StoreScreen({
  section, dispensaryId, category, onAddToCart, cart,
}: {
  /** The section the store opened in; its links stay there. */
  section: string
  dispensaryId: string
  /** An aisle of the store, or null for the store's own page. */
  category: string | null
  onAddToCart: (item: CartItem) => void
  cart: CartItem[]
}) {
  const navigate = useNavigate()
  const [store, setStore] = useState<PortalDispensary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  // The store list is the map's too, and the client keeps it for a minute, so
  // coming from Home this is usually already in hand.
  useEffect(() => {
    let cancelled = false
    setError(null)
    api.portal.getDispensaries()
      .then(all => {
        if (cancelled) return
        const found = all.find(d => d.id === dispensaryId) ?? null
        setStore(found)
        if (!found) setError("This store isn't on Terpee any more.")
      })
      .catch(() => { if (!cancelled) setError("Couldn't load this store.") })
    return () => { cancelled = true }
  }, [dispensaryId, attempt])

  // Opened from a shared link there is nothing to go back to, so Back goes to
  // the section instead of out of the app.
  const goBack = () => {
    if ((window.history.state?.idx ?? 0) > 0) navigate(-1)
    else navigate(`/portal/${section}`, { replace: true })
  }

  const current = store?.id === dispensaryId ? store : null

  return (
    <div style={{ position: 'relative', height: 'calc(100dvh - var(--chrome-bottom, 64px))', overflowY: 'auto', background: t.bg }}>
      {error ? (
        <FeedState kind="error" message={error} onRetry={() => setAttempt(n => n + 1)} style={{ paddingTop: 80 }} />
      ) : !current ? (
        <FeedState kind="loading" message="Loading store…" style={{ paddingTop: 80 }} />
      ) : category ? (
        <AisleView
          key={current.id}
          dispensaryId={current.id}
          dispensaryName={current.name}
          dispensarySlug={current.slug}
          category={category}
          acceptsPickup={current.accepts_pickup}
          section={section}
          onAddToCart={onAddToCart}
          cart={cart}
        />
      ) : (
        <DispensaryListings
          key={current.id}
          dispensaryId={current.id}
          dispensaryName={current.name}
          dispensarySlug={current.slug}
          dispensaryAddress={current.address}
          dispensaryLat={current.lat}
          dispensaryLng={current.lng}
          dispensaryLogoUrl={null}
          dispensaryBannerUrl={null}
          acceptsPickup={current.accepts_pickup}
          section={section}
          backLabel="Back"
          onBack={goBack}
          onAddToCart={onAddToCart}
          cart={cart}
        />
      )}
    </div>
  )
}
