import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import type { ListingDetail, CartItem } from '../types'
import { t, radius, font, categoryColor, alpha } from '../theme'
import { FeedState, Pill, CategoryTag, Label, ClassificationTag, DetailBlock, CollapsibleBlock, SpecRow } from './ui'

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
  const price = listing.price_cents ? `$${(listing.price_cents / 100).toFixed(2)}` : null
  const cartSupported = listing.dispensary_accepts_pickup
  const hasProductLink = !!(listing.product_id && onProductClick)
  const hasTerpenes = listing.terpenes.length > 0
  const hasCannabinoids = listing.cannabinoids.length > 0
  const hasSpecs = !!(listing.strain || listing.subtype || listing.product_line || listing.variant || listing.classification)

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
      {/* Back button */}
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

      {/* Hero image — unified light product plate */}
      {listing.image_url ? (
        <div style={{ position: 'relative', width: '100%', paddingTop: '72%', background: t.tile }}>
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

      {/* Content */}
      <div style={{ padding: '20px 20px 32px' }}>
        {/* Category + stock */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 14, alignItems: 'center', flexWrap: 'wrap' }}>
          <CategoryTag category={cat} />
          {listing.classification && <ClassificationTag classification={listing.classification} />}
          {listing.variant && <Pill>{listing.variant}</Pill>}
          {!listing.in_stock && <Pill color={t.danger} tone="category">Out of stock</Pill>}
        </div>

        {/* Name */}
        <div style={{ color: t.text1, fontSize: font.size.display, fontWeight: font.weight.heavy, lineHeight: 1.2, marginBottom: 6, letterSpacing: '-0.01em' }}>
          {listing.display_name}
        </div>

        {/* Brand */}
        {listing.scraped_brand && (
          <div style={{ color: t.text2, fontSize: font.size.body, marginBottom: 20 }}>{listing.scraped_brand}</div>
        )}

        {/* Price + Order */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: (hasCannabinoids || hasTerpenes || hasProductLink) ? 28 : 0, flexWrap: 'wrap' }}>
          {price && (
            <div style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: font.size.hero, letterSpacing: '-0.01em' }}>{price}</div>
          )}
          {cartSupported && onAddToCart && (
            <button
              onClick={handleAddToCart}
              style={{
                background: addedFlash ? '#7fae46' : t.accent,
                border: 'none', borderRadius: radius.md,
                color: '#0a0a0a', fontSize: font.size.body, fontWeight: font.weight.bold,
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

        {/* Cannabinoids */}
        {hasCannabinoids && (
          <div style={{ marginBottom: (hasTerpenes || hasProductLink) ? 24 : 0 }}>
            <Label style={{ marginBottom: 10 }}>Cannabinoids</Label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {listing.cannabinoids.map(c => (
                <div key={c.name} style={{
                  background: t.surface1, border: `1px solid ${t.border}`,
                  borderRadius: radius.md, padding: '9px 14px',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, minWidth: 74,
                }}>
                  <span style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.body }}>{c.name}</span>
                  <span style={{
                    color: c.family === 'thc' ? t.accent : '#3b9bf0',
                    fontSize: font.size.micro, fontWeight: font.weight.bold, textTransform: 'uppercase', letterSpacing: '0.05em',
                  }}>
                    {c.family.toUpperCase()}
                  </span>
                  {c.percent != null && (
                    <span style={{ color: t.text3, fontSize: font.size.caption }}>{c.percent}%</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Terpenes */}
        {hasTerpenes && (
          <div style={{ marginBottom: hasProductLink ? 28 : 0 }}>
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

        {/* Specs */}
        {hasSpecs && (
          <DetailBlock title="Details" style={{ marginTop: (hasCannabinoids || hasTerpenes) ? 28 : 0 }}>
            <div>
              {listing.strain && <SpecRow label="Strain" value={listing.strain} />}
              {listing.classification && <SpecRow label="Type" value={listing.classification} />}
              {listing.subtype && <SpecRow label="Form" value={listing.subtype} />}
              {listing.product_line && <SpecRow label="Product line" value={listing.product_line} />}
              {listing.variant && <SpecRow label="Size" value={listing.variant} />}
            </div>
          </DetailBlock>
        )}

        {/* Description */}
        {listing.description && (
          <CollapsibleBlock title="Product Description" style={{ marginTop: 28 }}>
            <p style={{ color: t.text2, fontSize: font.size.small, lineHeight: 1.6, margin: 0, whiteSpace: 'pre-wrap' }}>
              {listing.description}
            </p>
          </CollapsibleBlock>
        )}

        {/* See product link */}
        {listing.product_id && onProductClick && (
          <button
            onClick={() => onProductClick(listing.product_id!)}
            style={{
              marginTop: 'auto',
              width: '100%', background: 'transparent',
              border: `1px solid ${t.border}`, borderRadius: radius.md,
              color: t.text2, fontSize: font.size.small + 1, fontWeight: font.weight.medium, padding: '13px',
              cursor: 'pointer', textAlign: 'center',
              transition: `border-color var(--t-fast), color var(--t-fast)`,
            }}
          >
            See product across dispensaries →
          </button>
        )}
      </div>
    </div>
  )
}
