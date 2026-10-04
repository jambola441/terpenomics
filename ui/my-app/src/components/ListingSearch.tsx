import { useState, useEffect, useRef } from 'react'
import api from '../api/client'
import type { Listing } from '../types'
import { formatDollars } from '../utils/format'

/**
 * Pick a store listing by name. Listings, not products, are what purchases and
 * lab reports attach to: a product is a view derived from listings and has no
 * id of its own.
 */
type ListingSearchProps = {
  onSelect: (listing: Listing) => void
  disabled?: boolean
  placeholder?: string
}

export function ListingSearch({ onSelect, disabled, placeholder = 'Search listings...' }: ListingSearchProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Listing[]>([])
  const [loading, setLoading] = useState(false)
  const [showDropdown, setShowDropdown] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)

  // Debounced search
  useEffect(() => {
    if (!query.trim()) {
      setResults([])
      setShowDropdown(false)
      return
    }

    const timer = setTimeout(async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await api.listings.list({ q: query.trim(), limit: 10 })
        setResults(data.filter(l => l.is_active))
        setShowDropdown(true)
      } catch (e: any) {
        setError(e?.message ?? String(e))
        setResults([])
      } finally {
        setLoading(false)
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [query])

  // Click outside to close dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setShowDropdown(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  function handleSelect(listing: Listing) {
    onSelect(listing)
    setQuery('')
    setResults([])
    setShowDropdown(false)
  }

  return (
    <div ref={wrapperRef} style={{ position: 'relative', minWidth: 300 }}>
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        style={{ width: '100%', padding: 8 }}
      />
      
      {loading && (
        <div style={{ 
          position: 'absolute', 
          right: 8, 
          top: '50%', 
          transform: 'translateY(-50%)',
          fontSize: 12,
          opacity: 0.6,
        }}>
          Searching...
        </div>
      )}

      {error && (
        <div style={{ color: 'crimson', fontSize: 12, marginTop: 4 }}>
          {error}
        </div>
      )}

      {showDropdown && results.length > 0 && (
        <div style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          right: 0,
          backgroundColor: 'darkgray',
          border: '1px solid #ccc',
          borderRadius: 4,
          maxHeight: 300,
          overflowY: 'auto',
          zIndex: 1000,
          marginTop: 4,
          boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        }}>
          {results.map((listing) => (
            <div
              key={listing.id}
              onClick={() => handleSelect(listing)}
              style={{
                padding: '8px 12px',
                cursor: 'pointer',
                borderBottom: '1px solid #eee',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = 'gray'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'darkgray'
              }}
            >
              <div style={{ fontWeight: 500 }}>{listing.scraped_name ?? '(unnamed listing)'}</div>
              {listing.scraped_brand && (
                <div style={{ fontSize: 12, color: 'white' }}>{listing.scraped_brand}</div>
              )}
              <div style={{ fontSize: 11, color: '#eee' }}>
                {[listing.dispensary_name, listing.variant, listing.price_cents != null ? formatDollars(listing.price_cents) : null]
                  .filter(Boolean).join(' · ')}
              </div>
            </div>
          ))}
        </div>
      )}

      {showDropdown && results.length === 0 && !loading && query.trim() && (
        <div style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          right: 0,
          backgroundColor: 'darkgray',
          border: '1px solid #ccc',
          borderRadius: 4,
          padding: '12px',
          marginTop: 4,
          fontSize: 14,
          color: 'white',
          zIndex: 1000,
        }}>
          No listings found
        </div>
      )}
    </div>
  )
}
