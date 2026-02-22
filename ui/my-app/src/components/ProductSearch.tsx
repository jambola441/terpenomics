import { useState, useEffect, useRef } from 'react'
import api from '../api/client'
import type { Product } from '../types'

type ProductSearchProps = {
  onSelect: (product: Product) => void
  disabled?: boolean
  placeholder?: string
}

export function ProductSearch({ onSelect, disabled, placeholder = 'Search products...' }: ProductSearchProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Product[]>([])
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
        const data = await api.products.list({ q: query.trim(), limit: 10 })
        // Filter to only active products
        const activeProducts = data.filter(p => p.is_active)
        setResults(activeProducts)
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

  function handleSelect(product: Product) {
    onSelect(product)
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
          {results.map((product) => (
            <div
              key={product.id}
              onClick={() => handleSelect(product)}
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
              <div style={{ fontWeight: 500 }}>{product.name}</div>
              {product.brand && (
                <div style={{ fontSize: 12, color: 'white' }}>{product.brand}</div>
              )}
              <div style={{ fontSize: 11, color: '#999' }}>{product.category}</div>
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
          No products found
        </div>
      )}
    </div>
  )
}
