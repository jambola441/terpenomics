import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePagination } from './hooks/usePagination'
import { useSearch } from './hooks/useSearch'
import { SearchBar } from './components/SearchBar'
import api from './api/client'
import type { Listing } from './types'

const MATCH_FILTERS = [
  { label: 'All', value: undefined },
  { label: 'Matched', value: true },
  { label: 'Unmatched', value: false },
]

export default function Listings() {
  const [listings, setListings] = useState<Listing[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dispensaries, setDispensaries] = useState<{ id: string; name: string }[]>([])
  const [filterDispensary, setFilterDispensary] = useState('')
  const [filterMatched, setFilterMatched] = useState<boolean | undefined>(undefined)
  const [unmatchingId, setUnmatchingId] = useState<string | null>(null)

  const navigate = useNavigate()
  const { hasMore, limit, offset, loadMore, reset: resetPagination, updateHasMore } = usePagination(50)
  const { search, searchInput, setSearchInput, handleSearch, clearSearch } = useSearch()

  useEffect(() => {
    api.dispensaries.list({ limit: 200 }).then(setDispensaries).catch(() => {})
  }, [])

  useEffect(() => {
    fetchListings(true)
  }, [search, filterDispensary, filterMatched])

  async function fetchListings(reset: boolean = false) {
    setLoading(true)
    setError(null)
    try {
      const currentOffset = reset ? 0 : offset
      const data = await api.listings.list({
        q: search || undefined,
        dispensary_id: filterDispensary || undefined,
        matched: filterMatched,
        limit,
        offset: currentOffset,
      })
      setListings(prev => reset ? data : [...prev, ...data])
      updateHasMore(data.length)
      if (reset) resetPagination()
      else loadMore()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleUnmatch(e: React.MouseEvent, listingId: string) {
    e.stopPropagation()
    setUnmatchingId(listingId)
    try {
      const updated = await api.listings.unmatch(listingId)
      setListings(prev => prev.map(l => l.id === listingId ? updated : l))
    } catch (err: any) {
      setError(err.message)
    } finally {
      setUnmatchingId(null)
    }
  }

  const activeFilters = [filterDispensary].filter(Boolean).length

  function clearFilters() {
    setFilterDispensary('')
    setFilterMatched(undefined)
    clearSearch()
  }

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}>← Admin</button>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Listings</h2>
          <button onClick={() => navigate('/admin/listings/match')} style={{ ...navBtnStyle, marginLeft: 'auto' }}>
            Match unmatched →
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
          <SearchBar
            value={searchInput}
            onChange={setSearchInput}
            onSearch={handleSearch}
            onClear={clearSearch}
            placeholder="Search by name or brand…"
            disabled={loading}
            showClearButton={!!search}
          />

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <select
              value={filterDispensary}
              onChange={e => setFilterDispensary(e.target.value)}
              style={selectStyle}
            >
              <option value="">All dispensaries</option>
              {dispensaries.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>

            {(activeFilters > 0 || search) && (
              <button onClick={clearFilters} style={{ fontSize: 12, padding: '4px 10px', cursor: 'pointer', background: 'transparent', border: '1px solid #374151', borderRadius: 4, color: '#94a3b8' }}>
                Clear all
              </button>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
          {MATCH_FILTERS.map(f => (
            <button
              key={String(f.value)}
              onClick={() => setFilterMatched(f.value)}
              style={{
                padding: '6px 14px',
                borderRadius: 6,
                border: '1px solid',
                borderColor: filterMatched === f.value ? '#6366f1' : '#1e293b',
                background: filterMatched === f.value ? '#1e1b4b' : '#0f172a',
                color: filterMatched === f.value ? '#a5b4fc' : '#94a3b8',
                cursor: 'pointer',
                fontSize: 13,
              }}
            >
              {f.label}
            </button>
          ))}
        </div>

        {error && <div style={{ color: '#f87171', marginBottom: 16 }}>{error}</div>}

        <p style={{ fontSize: 13, color: '#475569', marginBottom: 12 }}>
          {search ? <>Searching: <strong style={{ color: '#94a3b8' }}>{search}</strong> — </> : null}
          Showing {listings.length} listing(s)
        </p>

        {loading && listings.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>Loading…</div>
        ) : listings.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>No listings found.</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ color: '#475569', textAlign: 'left', borderBottom: '1px solid #1e293b' }}>
                <th style={thStyle}>Scraped Name</th>
                <th style={thStyle}>Brand</th>
                <th style={thStyle}>Variant</th>
                <th style={thStyle}>Category</th>
                <th style={thStyle}>Dispensary</th>
                <th style={thStyle}>Price</th>
                <th style={thStyle}>Product</th>
                <th style={thStyle}>In Stock</th>
                <th style={thStyle}></th>
              </tr>
            </thead>
            <tbody>
              {listings.map(l => (
                <tr
                  key={l.id}
                  style={{ borderBottom: '1px solid #0f172a', cursor: l.product_id ? 'pointer' : 'default' }}
                  onClick={() => l.product_id && navigate(`/admin/products/${l.product_id}`)}
                  onMouseEnter={e => { if (l.product_id) (e.currentTarget as HTMLTableRowElement).style.background = '#0f172a' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLTableRowElement).style.background = 'transparent' }}
                >
                  <td style={tdStyle}>{l.scraped_name ?? <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={tdStyle}>{l.scraped_brand ?? <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={tdStyle}>{l.variant ?? <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={tdStyle}>{l.scraped_category ?? <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={tdStyle}>{l.dispensary_name}</td>
                  <td style={tdStyle}>{l.price_cents != null ? `$${(l.price_cents / 100).toFixed(2)}` : <span style={{ color: '#475569' }}>—</span>}</td>
                  <td style={tdStyle}>
                    {l.product_name
                      ? <span style={{ color: '#86efac' }}>{l.product_name}</span>
                      : <span style={{ color: '#f87171' }}>unmatched</span>}
                  </td>
                  <td style={tdStyle}>{l.in_stock ? '✓' : <span style={{ color: '#475569' }}>✗</span>}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>
                    {l.product_id && (
                      <button
                        onClick={e => handleUnmatch(e, l.id)}
                        disabled={unmatchingId === l.id}
                        style={{ padding: '3px 8px', fontSize: 11, background: 'transparent', border: '1px solid #374151', borderRadius: 4, color: '#94a3b8', cursor: 'pointer' }}
                      >
                        {unmatchingId === l.id ? '…' : 'unmatch'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {loading && listings.length > 0 && (
          <div style={{ padding: 16, color: '#475569', textAlign: 'center' }}>Loading more…</div>
        )}

        {!loading && hasMore && listings.length > 0 && (
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <button onClick={() => fetchListings(false)} style={{ padding: '8px 20px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, color: '#94a3b8', cursor: 'pointer' }}>
              Load more
            </button>
          </div>
        )}

      </div>
    </div>
  )
}

const thStyle: React.CSSProperties = { padding: '8px 12px', fontWeight: 500, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }
const tdStyle: React.CSSProperties = { padding: '10px 12px', color: '#cbd5e1' }
const navBtnStyle: React.CSSProperties = { padding: '6px 12px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 13 }
const selectStyle: React.CSSProperties = { fontSize: 13, padding: '5px 8px', borderRadius: 4, background: '#0f172a', border: '1px solid #1e293b', color: '#94a3b8' }
