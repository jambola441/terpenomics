import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import type { ListingDetail, CartItem } from '../types'

const CATEGORY_COLORS: Record<string, string> = {
  flower: '#4caf50',
  cart: '#2196f3',
  vaporizers: '#2196f3',
  edible: '#ff9800',
  concentrate: '#9c27b0',
  preroll: '#00bcd4',
  tincture: '#8bc34a',
  tinctures: '#8bc34a',
  topical: '#f44336',
  merch: '#607d8b',
  other: '#9e9e9e',
}

interface Props {
  dispensaryId: string
  listingId: string
  onProductClick?: (productId: string) => void
  onAddToCart?: (item: CartItem) => void
  cartQuantity?: number
}

export default function ListingDetailView({ dispensaryId, listingId, onProductClick, onAddToCart, cartQuantity = 0 }: Props) {
  const navigate = useNavigate()
  const [listing, setListing] = useState<ListingDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [addedFlash, setAddedFlash] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.portal.getListing(dispensaryId, listingId)
      .then(setListing)
      .catch(() => setError('Failed to load listing'))
      .finally(() => setLoading(false))
  }, [dispensaryId, listingId])

  const containerStyle: React.CSSProperties = {
    height: 'calc(100dvh - 64px)',
    overflowY: 'auto',
    background: '#0a0a0a',
  }

  if (loading) {
    return (
      <div style={{ ...containerStyle, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: '#555', fontSize: 14 }}>Loading…</span>
      </div>
    )
  }

  if (error || !listing) {
    return (
      <div style={{ ...containerStyle, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: '#f44336', fontSize: 14 }}>{error ?? 'Not found'}</span>
      </div>
    )
  }

  const cat = listing.scraped_category ?? 'other'
  const catColor = CATEGORY_COLORS[cat] ?? '#9e9e9e'
  const price = listing.price_cents ? `$${(listing.price_cents / 100).toFixed(2)}` : null
  const cartSupported = listing.dispensary_accepts_pickup
  const hasProductLink = !!(listing.product_id && onProductClick)
  const hasTerpenes = listing.terpenes.length > 0
  const hasCannabinoids = listing.cannabinoids.length > 0

  function handleAddToCart() {
    if (!onAddToCart || !listing) return
    onAddToCart({
      listingId: listing.id,
      dispensaryId: listing.dispensary_id,
      dispensarySlug: listing.dispensary_slug,
      dispensaryName: listing.dispensary_name,
      name: listing.scraped_name ?? '—',
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
      {/* Back button */}
      <button
        onClick={() => navigate(-1)}
        style={{
          position: 'absolute', top: 16, left: 16, zIndex: 10,
          background: 'rgba(0,0,0,0.6)', border: '1px solid #333',
          borderRadius: 20, color: '#fff', fontSize: 13,
          padding: '6px 14px', cursor: 'pointer',
        }}
      >
        ← {listing.dispensary_name}
      </button>

      {/* Hero image */}
      {listing.image_url ? (
        <div style={{ position: 'relative', width: '100%', paddingTop: '75%', background: '#111' }}>
          <img
            src={listing.image_url}
            alt={listing.scraped_name ?? ''}
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain' }}
            onError={e => { (e.target as HTMLImageElement).parentElement!.style.display = 'none' }}
          />
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, transparent 50%, #0a0a0a 100%)' }} />
        </div>
      ) : (
        <div style={{ height: 140, background: `linear-gradient(135deg, ${catColor}33 0%, #111 100%)` }} />
      )}

      {/* Content */}
      <div style={{ padding: '20px 20px 24px' }}>
        {/* Category + stock */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 14, alignItems: 'center' }}>
          <span style={{
            background: catColor + '22', border: `1px solid ${catColor}`,
            color: catColor, fontSize: 10, fontWeight: 700,
            padding: '3px 10px', borderRadius: 20,
            textTransform: 'uppercase', letterSpacing: '0.05em',
          }}>
            {cat}
          </span>
          {listing.variant && (
            <span style={{ background: '#1a1a1a', color: '#666', fontSize: 11, padding: '3px 10px', borderRadius: 20 }}>
              {listing.variant}
            </span>
          )}
          {!listing.in_stock && (
            <span style={{ background: '#1a1a1a', color: '#555', fontSize: 10, padding: '3px 10px', borderRadius: 20 }}>
              Out of stock
            </span>
          )}
        </div>

        {/* Name */}
        <div style={{ color: '#fff', fontSize: 24, fontWeight: 800, lineHeight: 1.2, marginBottom: 6 }}>
          {listing.scraped_name ?? '—'}
        </div>

        {/* Brand */}
        {listing.scraped_brand && (
          <div style={{ color: '#666', fontSize: 14, marginBottom: 20 }}>{listing.scraped_brand}</div>
        )}

        {/* Price + Order */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: (hasCannabinoids || hasTerpenes || hasProductLink) ? 28 : 0, flexWrap: 'wrap' }}>
          {price && (
            <div style={{ color: '#a8e063', fontWeight: 800, fontSize: 28 }}>{price}</div>
          )}
          {cartSupported && onAddToCart && (
            <button
              onClick={handleAddToCart}
              style={{
                background: addedFlash ? '#6abf2e' : '#a8e063',
                border: 'none', borderRadius: 10,
                color: '#0a0a0a', fontSize: 14, fontWeight: 700,
                padding: '10px 20px', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 6,
                transition: 'background 0.2s',
              }}
            >
              {addedFlash ? 'Added!' : cartQuantity > 0 ? `In cart (${cartQuantity})` : 'Add to cart'}
            </button>
          )}
        </div>

        {/* Cannabinoids */}
        {hasCannabinoids && (
          <div style={{ marginBottom: (hasTerpenes || hasProductLink) ? 24 : 0 }}>
            <div style={{ color: '#555', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
              Cannabinoids
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {listing.cannabinoids.map(c => (
                <div key={c.name} style={{
                  background: '#1a1a1a', border: '1px solid #2a2a2a',
                  borderRadius: 10, padding: '8px 14px',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, minWidth: 72,
                }}>
                  <span style={{ color: '#fff', fontWeight: 700, fontSize: 14 }}>{c.name}</span>
                  <span style={{
                    color: c.family === 'thc' ? '#a8e063' : '#2196f3',
                    fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
                  }}>
                    {c.family.toUpperCase()}
                  </span>
                  {c.percent != null && (
                    <span style={{ color: '#555', fontSize: 11 }}>{c.percent}%</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Terpenes */}
        {hasTerpenes && (
          <div style={{ marginBottom: hasProductLink ? 28 : 0 }}>
            <div style={{ color: '#555', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
              Terpenes
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {listing.terpenes.map(t => (
                <span key={t.name} style={{
                  background: '#1a1a1a', color: '#888', fontSize: 12,
                  padding: '5px 12px', borderRadius: 20,
                }}>
                  {t.name}{t.percent != null ? ` ${t.percent}%` : ''}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* See product link */}
        {listing.product_id && onProductClick && (
          <button
            onClick={() => onProductClick(listing.product_id!)}
            style={{
              marginTop: 'auto',
              width: '100%', background: 'transparent',
              border: '1px solid #2a2a2a', borderRadius: 10,
              color: '#555', fontSize: 13, padding: '12px',
              cursor: 'pointer', textAlign: 'center',
            }}
          >
            See product across dispensaries →
          </button>
        )}
      </div>
    </div>
  )
}
