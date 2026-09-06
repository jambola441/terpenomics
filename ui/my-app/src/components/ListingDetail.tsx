/* ============================================================================
   ListingDetail — one product, on one store's shelf.

   A listing is a product *at a place for a price*, and the screen used to show
   only the product half. The three things it was missing are the three a
   store's own menu can never tell you:

     who is selling this      the store, where it is, whether you can order
     who else sells it        every other store carrying the same product, and
                              for how much — this is the whole reason the app
                              tracks more than one menu
     what else is like it     the neighbours on this shelf, so deciding between
                              two things does not mean going back to a list

   Everything arrives in the one request that loads the listing, because all of
   it is derived from the same row and splitting it would paint the screen in
   pieces.
   ========================================================================== */

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import type { CartItem, ListingDetail, PortalDispensary, SimilarListing } from '../types'
import { t, radius, font, categoryColor, alpha } from '../theme'
import {
  FeedState, Pill, CategoryTag, Label, ClassificationTag, DetailBlock,
  CollapsibleBlock, SpecRow, Pressable, ProductImage,
} from './ui'
import { formatDist, formatDollars, haversineMi } from '../utils/format'

interface Props {
  dispensaryId: string
  listingId: string
  onAddToCart?: (item: CartItem) => void
  cartQuantity?: number
  /** The same product at another store. */
  onOpenListing?: (dispensaryId: string, listingId: string) => void
  /** This store's own menu. */
  onOpenDispensary?: (dispensaryId: string) => void
  /** The cross-store product page. */
  onOpenProduct?: (brand: string | null, productKey: string) => void
}

/** "3 hours ago", roughly — precision past that is not information a shopper
 *  can act on, and a scrape time to the minute reads as false certainty. */
function checkedAgo(iso: string | null): string | null {
  if (!iso) return null
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (!Number.isFinite(minutes) || minutes < 0) return null
  if (minutes < 90) return `${Math.max(1, minutes)} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 36) return `${hours} hr ago`
  return `${Math.round(hours / 24)} days ago`
}

export default function ListingDetailView({
  dispensaryId, listingId, onAddToCart, cartQuantity = 0,
  onOpenListing, onOpenDispensary, onOpenProduct,
}: Props) {
  const navigate = useNavigate()
  const [listing, setListing] = useState<ListingDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [addedFlash, setAddedFlash] = useState(false)
  const [userPos, setUserPos] = useState<{ lat: number; lng: number } | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.portal.getListing(dispensaryId, listingId)
      .then(setListing)
      .catch(() => setError('Failed to load listing'))
      .finally(() => setLoading(false))
  }, [dispensaryId, listingId])

  useEffect(() => {
    navigator.geolocation?.getCurrentPosition(pos => {
      setUserPos({ lat: pos.coords.latitude, lng: pos.coords.longitude })
    })
  }, [])

  const distanceTo = useMemo(() => (store: PortalDispensary): number | null => {
    if (!userPos || store.lat == null || store.lng == null) return null
    return haversineMi(userPos.lat, userPos.lng, store.lat, store.lng)
  }, [userPos])

  const containerStyle: React.CSSProperties = {
    height: 'calc(100dvh - 64px)',
    overflowY: 'auto',
    background: t.bg,
  }

  if (loading) {
    return <div style={containerStyle}><FeedState kind="loading" message="Loading…" style={{ height: '100%' }} /></div>
  }
  if (error || !listing) {
    return <div style={containerStyle}><FeedState kind="error" message={error ?? 'Not found'} style={{ height: '100%' }} /></div>
  }

  const cat = listing.scraped_category ?? 'other'
  const catColor = categoryColor(cat)
  const cartSupported = listing.dispensary_accepts_pickup
  // Defaulted rather than assumed: these arrive with the listing, but the screen
  // should degrade to the product half rather than blank out if one is missing.
  const context = listing.price_context ?? {
    other_store_count: 0, min_cents: null, avg_cents: null, max_cents: null, is_cheapest: false,
  }
  const elsewhere = listing.also_available_at ?? []
  const similar = listing.similar_at_dispensary ?? []
  const checked = checkedAgo(listing.last_seen_at ?? null)

  function handleAddToCart() {
    if (!onAddToCart || !listing) return
    onAddToCart({
      listingId: listing.id,
      dispensaryId: listing.dispensary_id,
      dispensarySlug: listing.dispensary_slug,
      dispensaryName: listing.dispensary_name,
      name: listing.display_name,
      brand: listing.scraped_brand ?? null,
      variant: listing.variant ?? null,
      price_cents: listing.price_cents ?? null,
      url: listing.url ?? null,
      image_url: listing.image_url ?? null,
      quantity: 1,
    })
    setAddedFlash(true)
    setTimeout(() => setAddedFlash(false), 1500)
  }

  return (
    <div style={containerStyle}>
      <button
        onClick={() => navigate(-1)}
        style={{
          position: 'absolute', top: 16, left: 16, zIndex: 10,
          background: alpha('#000', 0.55), border: `1px solid ${alpha('#fff', 0.15)}`,
          backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
          borderRadius: radius.pill, color: '#fff', fontSize: font.size.small, fontWeight: font.weight.medium,
          padding: '7px 14px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 5,
          maxWidth: 'calc(100% - 32px)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}
      >
        ← {listing.dispensary_name}
      </button>

      {listing.image_url ? (
        <div style={{ position: 'relative', width: '100%', paddingTop: '100%', background: t.tile }}>
          <img
            src={listing.image_url}
            alt={listing.display_name}
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', padding: 24, boxSizing: 'border-box' }}
            onError={e => { (e.target as HTMLImageElement).parentElement!.style.display = 'none' }}
          />
        </div>
      ) : (
        <div style={{ height: 150, background: `linear-gradient(135deg, ${alpha(catColor, 0.28)} 0%, ${t.surface1} 100%)` }} />
      )}

      <div style={{ padding: '20px 20px 32px' }}>
        {/* ── Identity ── */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 14, alignItems: 'center', flexWrap: 'wrap' }}>
          <CategoryTag category={cat} />
          {listing.classification && <ClassificationTag classification={listing.classification} />}
          {listing.variant && <Pill>{listing.variant}</Pill>}
          {!listing.in_stock && <Pill color={t.danger} tone="category">Out of stock</Pill>}
        </div>

        <div style={{ color: t.text1, fontSize: font.size.display, fontWeight: font.weight.heavy, lineHeight: 1.2, marginBottom: 6, letterSpacing: '-0.01em' }}>
          {listing.display_name}
        </div>

        {listing.scraped_brand && (
          <div style={{ color: t.text2, fontSize: font.size.body, marginBottom: 18 }}>{listing.scraped_brand}</div>
        )}

        {/* ── Price, and how it compares ── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          {listing.price_cents != null && (
            <div style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: font.size.hero, letterSpacing: '-0.01em' }}>
              {formatDollars(listing.price_cents)}
            </div>
          )}
          {cartSupported && onAddToCart && listing.in_stock && (
            <button
              onClick={handleAddToCart}
              style={{
                background: addedFlash ? '#7fae46' : t.accent,
                border: 'none', borderRadius: radius.md,
                color: t.accentInk, fontSize: font.size.body, fontWeight: font.weight.bold,
                padding: '11px 22px', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 6,
                boxShadow: 'var(--e-1)',
                transition: `background var(--t-base), transform var(--t-fast)`,
              }}
            >
              {addedFlash ? '✓ Added' : cartQuantity > 0 ? `In cart (${cartQuantity})` : 'Add to cart'}
            </button>
          )}
        </div>

        <PriceContextLine listing={listing} />

        {checked && (
          <div style={{ color: t.text4, fontSize: font.size.caption, marginTop: 8 }}>
            Stock last checked {checked}
          </div>
        )}

        {/* ── The store selling it ── */}
        {listing.dispensary && <StoreCard
          store={listing.dispensary}
          distanceMi={distanceTo(listing.dispensary)}
          onOpenDispensary={onOpenDispensary}
        />}

        {/* ── The same product, elsewhere ── */}
        {elsewhere.length > 0 && (
          <div style={{ marginTop: 28 }}>
            <Label style={{ marginBottom: 4 }}>Also available at</Label>
            <div style={{ color: t.text4, fontSize: font.size.caption, marginBottom: 10 }}>
              {elsewhere.length} other {elsewhere.length === 1 ? 'store' : 'stores'} carry this exact product
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {elsewhere.map(row => (
                <AlternativeRow
                  key={row.listing_id}
                  name={row.dispensary.name}
                  address={row.dispensary.address}
                  priceCents={row.price_cents}
                  herePriceCents={listing.price_cents}
                  distanceMi={distanceTo(row.dispensary)}
                  acceptsPickup={row.dispensary.accepts_pickup}
                  onClick={onOpenListing ? () => onOpenListing(row.dispensary.id, row.listing_id) : undefined}
                />
              ))}
            </div>
            {onOpenProduct && (
              <button
                onClick={() => onOpenProduct(listing.scraped_brand ?? null, listing.product_key)}
                style={{
                  width: '100%', marginTop: 10, boxSizing: 'border-box',
                  background: 'transparent', border: `1px solid ${t.border}`, borderRadius: radius.md,
                  color: t.text2, fontSize: font.size.small, fontWeight: font.weight.medium,
                  padding: 12, cursor: 'pointer',
                }}
              >
                Compare all {context.other_store_count + 1} stores →
              </button>
            )}
          </div>
        )}

        {/* ── Lab data ── */}
        {listing.cannabinoids.length > 0 && (
          <div style={{ marginTop: 28 }}>
            <Label style={{ marginBottom: 10 }}>Cannabinoids</Label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {listing.cannabinoids.map(c => (
                <div key={c.name} style={{
                  background: t.surface1, border: `1px solid ${t.border}`,
                  borderRadius: radius.md, padding: '9px 14px',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, minWidth: 74,
                }}>
                  <span style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.body }}>{c.name}</span>
                  {/* The family only says something when it is not the name
                      again — THC over THC is a tile of one word twice. */}
                  {c.family.toUpperCase() !== c.name.toUpperCase() && (
                    <span style={{
                      color: c.family === 'thc' ? t.accent : '#3b9bf0',
                      fontSize: font.size.micro, fontWeight: font.weight.bold, textTransform: 'uppercase', letterSpacing: '0.05em',
                    }}>
                      {c.family.toUpperCase()}
                    </span>
                  )}
                  {c.percent != null && (
                    <span style={{ color: t.text3, fontSize: font.size.caption }}>{c.percent}%</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {listing.terpenes.length > 0 && (
          <div style={{ marginTop: 24 }}>
            <Label style={{ marginBottom: 10 }}>Terpenes</Label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
              {listing.terpenes.map(tp => (
                <span key={tp.name} style={{
                  background: t.surface2, color: t.text2, fontSize: font.size.small,
                  padding: '6px 12px', borderRadius: radius.pill, border: `1px solid ${t.border}`,
                }}>
                  {tp.name}{tp.percent != null ? ` ${tp.percent}%` : ''}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* ── Specs and description ── */}
        {(listing.strain || listing.subtype || listing.product_line || listing.variant || listing.classification) && (
          <DetailBlock title="Details" style={{ marginTop: 28 }}>
            <div>
              {listing.strain && <SpecRow label="Strain" value={listing.strain} />}
              {listing.classification && <SpecRow label="Type" value={listing.classification} />}
              {listing.subtype && <SpecRow label="Form" value={listing.subtype} />}
              {listing.product_line && <SpecRow label="Product line" value={listing.product_line} />}
              {listing.variant && <SpecRow label="Size" value={listing.variant} />}
            </div>
          </DetailBlock>
        )}

        {listing.description && (
          <CollapsibleBlock title="Product Description" style={{ marginTop: 28 }}>
            <p style={{ color: t.text2, fontSize: font.size.small, lineHeight: 1.6, margin: 0, whiteSpace: 'pre-wrap' }}>
              {listing.description}
            </p>
          </CollapsibleBlock>
        )}
      </div>

      {/* ── More on this shelf ── */}
      {similar.length > 0 && (
        <SimilarRail
          items={similar}
          storeName={listing.dispensary_name}
          onOpen={row => onOpenListing?.(listing.dispensary_id, row.id)}
        />
      )}

      <div style={{ height: 28 }} />
    </div>
  )
}

/* ── Where this price sits ─────────────────────────────────────────────────── */

function PriceContextLine({ listing }: { listing: ListingDetail }) {
  const { price_context: context, price_cents: price } = listing

  if (!context || context.other_store_count === 0) {
    return (
      <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 8 }}>
        No other store we track carries this.
      </div>
    )
  }
  if (price == null || context.avg_cents == null) return null

  const gap = context.avg_cents - price
  const stores = `${context.other_store_count} other ${context.other_store_count === 1 ? 'store' : 'stores'}`

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
      {context.is_cheapest && (
        <span style={{
          background: alpha(t.accent, 0.16), border: `1px solid ${alpha(t.accent, 0.4)}`,
          color: t.accent, fontSize: font.size.caption, fontWeight: font.weight.bold,
          borderRadius: radius.pill, padding: '3px 9px',
        }}>
          Cheapest of {context.other_store_count + 1}
        </span>
      )}
      <span style={{ color: t.text3, fontSize: font.size.small }}>
        {gap > 0
          ? `${formatDollars(gap)} below the average at ${stores}`
          : gap < 0
            ? `${formatDollars(-gap)} above the average at ${stores}`
            : `The same as the average at ${stores}`}
      </span>
    </div>
  )
}

/* ── The store ─────────────────────────────────────────────────────────────── */

function StoreCard({ store, distanceMi, onOpenDispensary }: {
  store: PortalDispensary
  distanceMi: number | null
  onOpenDispensary?: (dispensaryId: string) => void
}) {
  const directions = store.lat != null && store.lng != null
    ? `https://www.google.com/maps/dir/?api=1&destination=${store.lat},${store.lng}`
    : store.address
      ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(store.address)}`
      : null

  return (
    <div style={{
      marginTop: 26, background: t.surface1, border: `1px solid ${t.border}`,
      borderRadius: radius.lg, padding: 14,
    }}>
      <Label style={{ marginBottom: 12 }}>Sold at</Label>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{
          width: 44, height: 44, borderRadius: radius.md, flexShrink: 0, overflow: 'hidden',
          background: t.surface2, border: `1px solid ${t.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          {store.logo_url ? (
            <img
              src={store.logo_url}
              alt=""
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          ) : (
            <span style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: 19 }}>
              {store.name.charAt(0).toUpperCase()}
            </span>
          )}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.body,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {store.name}
          </div>
          <div style={{ color: t.text3, fontSize: font.size.caption, marginTop: 2 }}>
            {store.address ?? 'Address unknown'}
            {distanceMi != null && ` · ${formatDist(distanceMi)}`}
          </div>
        </div>
      </div>

      <div style={{ marginTop: 12 }}>
        {store.accepts_pickup
          ? <Pill color={categoryColor('flower')} tone="category">🛒 Order for pickup</Pill>
          : <Pill>In-store only</Pill>}
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
        {onOpenDispensary && (
          <StoreAction label="Menu" onClick={() => onOpenDispensary(store.id)} />
        )}
        {directions && <StoreAction label="Directions" href={directions} />}
        {store.website_url && <StoreAction label="Website" href={store.website_url} />}
      </div>
    </div>
  )
}

function StoreAction({ label, onClick, href }: { label: string; onClick?: () => void; href?: string }) {
  const style: React.CSSProperties = {
    flex: 1, minWidth: 92, textAlign: 'center', textDecoration: 'none',
    background: t.surface2, border: `1px solid ${t.border}`, borderRadius: radius.md,
    color: t.text2, fontSize: font.size.small, fontWeight: font.weight.semibold,
    padding: '10px 12px', cursor: 'pointer', display: 'block', boxSizing: 'border-box',
    whiteSpace: 'nowrap',
  }
  if (href) {
    return <a href={href} target="_blank" rel="noreferrer" style={style}>{label}</a>
  }
  return <button onClick={onClick} style={style}>{label}</button>
}

/* ── The same product somewhere else ───────────────────────────────────────── */

function AlternativeRow({ name, address, priceCents, herePriceCents, distanceMi, acceptsPickup, onClick }: {
  name: string
  address: string | null
  priceCents: number | null
  herePriceCents: number | null
  distanceMi: number | null
  acceptsPickup: boolean
  onClick?: () => void
}) {
  // The number that matters is the difference, not the price: a shopper on this
  // screen has already seen what it costs here.
  const gap = priceCents != null && herePriceCents != null ? priceCents - herePriceCents : null
  const gapColor = gap == null || gap === 0 ? t.text3 : gap < 0 ? t.accent : t.danger

  return (
    <Pressable
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '11px 13px',
        background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg,
      }}
    >
      <div style={{ flex: 1, minWidth: 0, textAlign: 'left' }}>
        <div style={{
          color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.small + 1,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {name}
        </div>
        <div style={{ color: t.text3, fontSize: font.size.caption, marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {distanceMi != null ? formatDist(distanceMi) : address ?? '—'}
          {acceptsPickup && ' · pickup'}
        </div>
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.body }}>
          {priceCents != null ? formatDollars(priceCents) : '—'}
        </div>
        {gap != null && (
          <div style={{ color: gapColor, fontSize: font.size.caption, fontWeight: font.weight.semibold, marginTop: 1 }}>
            {gap === 0 ? 'same price' : `${gap < 0 ? '−' : '+'}${formatDollars(Math.abs(gap))}`}
          </div>
        )}
      </div>
    </Pressable>
  )
}

/* ── Neighbours on this shelf ──────────────────────────────────────────────── */

function SimilarRail({ items, storeName, onOpen }: {
  items: SimilarListing[]
  storeName: string
  onOpen: (row: SimilarListing) => void
}) {
  return (
    <div style={{ marginTop: 4 }}>
      <div style={{ padding: '0 20px 10px' }}>
        <Label style={{ marginBottom: 4 }}>Similar at this store</Label>
        <div style={{ color: t.text4, fontSize: font.size.caption }}>
          More like this on {storeName}&apos;s shelf
        </div>
      </div>
      <div
        className="no-scrollbar"
        style={{
          display: 'flex', gap: 10, overflowX: 'auto',
          padding: '0 20px 4px', scrollSnapType: 'x proximity',
        }}
      >
        {items.map(row => {
          const color = categoryColor(row.scraped_category)
          return (
            <Pressable
              key={row.id}
              onClick={() => onOpen(row)}
              lift
              style={{
                width: 142, flexShrink: 0, scrollSnapAlign: 'start',
                background: t.surface1, border: `1px solid ${t.border}`,
                borderRadius: radius.lg, overflow: 'hidden', textAlign: 'left',
              }}
            >
              <ProductImage
                src={row.image_url}
                alt={row.display_name}
                category={row.scraped_category}
              />
              <div style={{ padding: '8px 10px 10px' }}>
                {row.scraped_brand && (
                  <div style={{
                    color: t.text3, fontSize: font.size.caption, fontWeight: font.weight.semibold,
                    marginBottom: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>
                    {row.scraped_brand}
                  </div>
                )}
                <div style={{
                  color: t.text1, fontWeight: font.weight.semibold, fontSize: font.size.small,
                  lineHeight: 1.3, height: '2.6em', overflow: 'hidden',
                }}>
                  {row.display_name}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6, marginTop: 7 }}>
                  <span style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.small + 1 }}>
                    {row.price_cents != null ? formatDollars(row.price_cents) : '—'}
                  </span>
                  {row.variant && (
                    <span style={{
                      color, fontSize: font.size.caption, fontWeight: font.weight.semibold,
                      background: alpha(color, 0.12), borderRadius: radius.pill, padding: '2px 7px',
                    }}>
                      {row.variant}
                    </span>
                  )}
                </div>
              </div>
            </Pressable>
          )
        })}
      </div>
    </div>
  )
}
