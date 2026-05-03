import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from './api/client'
import type { UnmatchedListing, MatchCandidate } from './types'

const SCORE_HIGH = 0.8
const SCORE_MED  = 0.65

function scoreColor(score: number): string {
  if (score >= SCORE_HIGH) return '#22c55e'
  if (score >= SCORE_MED)  return '#f59e0b'
  return '#475569'
}

function scoreBadge(score: number) {
  const pct = Math.round(score * 100)
  return (
    <span style={{
      display: 'inline-block',
      padding: '1px 7px',
      borderRadius: 10,
      fontSize: 12,
      fontWeight: 600,
      color: '#0f172a',
      background: scoreColor(score),
      marginRight: 6,
    }}>
      {pct}%
    </span>
  )
}

function CandidateRow({
  candidate,
  onConfirm,
  confirming,
}: {
  candidate: MatchCandidate
  onConfirm: (productId: string) => void
  confirming: boolean
}) {
  return (
    <tr style={{ background: '#111827' }}>
      <td />
      <td />
      <td style={{ paddingLeft: 32, paddingTop: 6, paddingBottom: 6, color: '#cbd5e1', fontSize: 13 }}>
        {scoreBadge(candidate.score)}
        <span style={{ opacity: 0.5, fontSize: 11, marginRight: 8 }}>{candidate.match_basis}</span>
      </td>
      <td style={{ color: '#cbd5e1', fontSize: 13 }}>{candidate.product_name}</td>
      <td style={{ color: '#94a3b8', fontSize: 13 }}>{candidate.product_brand ?? '—'}</td>
      <td style={{ color: '#94a3b8', fontSize: 13 }}>{candidate.product_variant ?? '—'}</td>
      <td style={{ color: '#94a3b8', fontSize: 13 }}>{candidate.product_category}</td>
      <td style={{ fontSize: 11, color: '#475569' }}>
        {candidate.dispensary_slugs.length === 0 ? '—' : candidate.dispensary_slugs.map((d, i) => (
          <span key={d.slug}>
            {i > 0 && ', '}
            {d.url
              ? <a href={d.url} target="_blank" rel="noreferrer" style={{ color: '#64748b' }}>{d.slug}</a>
              : <span>{d.slug}</span>
            }
          </span>
        ))}
      </td>
      <td />
      <td style={{ textAlign: 'right', paddingRight: 12 }}>
        <button
          onClick={() => onConfirm(candidate.product_id)}
          disabled={confirming}
          style={{
            padding: '3px 12px', fontSize: 12,
            cursor: confirming ? 'not-allowed' : 'pointer',
            background: '#1d4ed8', color: '#fff',
            border: 'none', borderRadius: 4,
          }}
        >
          Confirm
        </button>
      </td>
    </tr>
  )
}

function ListingRow({
  listing,
  onMatched,
  selected,
  onToggleSelect,
}: {
  listing: UnmatchedListing
  onMatched: (id: string) => void
  selected: boolean
  onToggleSelect: (id: string) => void
}) {
  const [expanded, setExpanded]     = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [error, setError]           = useState<string | null>(null)

  async function handleConfirm(productId: string) {
    setConfirming(true)
    setError(null)
    try {
      await api.listings.match(listing.id, productId)
      onMatched(listing.id)
    } catch (e: any) {
      setError(e.message)
      setConfirming(false)
    }
  }

  async function handleCreateNew() {
    setConfirming(true)
    setError(null)
    try {
      await api.listings.createAndMatch(listing.id)
      onMatched(listing.id)
    } catch (e: any) {
      setError(e.message)
      setConfirming(false)
    }
  }

  const topCandidate = listing.candidates[0]

  return (
    <>
      <tr
        style={{ borderBottom: '1px solid #0f172a', cursor: 'pointer', background: expanded ? '#111827' : 'transparent' }}
        onClick={() => setExpanded(e => !e)}
        onMouseEnter={e => { if (!expanded) (e.currentTarget as HTMLTableRowElement).style.background = '#0a0f1a' }}
        onMouseLeave={e => { if (!expanded) (e.currentTarget as HTMLTableRowElement).style.background = 'transparent' }}
      >
        <td style={{ width: 32, textAlign: 'center', padding: '10px 8px' }} onClick={e => e.stopPropagation()}>
          <input type="checkbox" checked={selected} onChange={() => onToggleSelect(listing.id)} style={{ cursor: 'pointer' }} />
        </td>
        <td style={{ width: 24, textAlign: 'center', padding: '10px 4px', color: '#475569', userSelect: 'none', fontSize: 11 }}>
          {listing.candidates.length > 0 ? (expanded ? '▼' : '▶') : '—'}
        </td>
        <td style={tdStyle}>
          {listing.url
            ? <a href={listing.url} target="_blank" rel="noreferrer" style={{ color: '#64748b' }}>{listing.dispensary_slug}</a>
            : <span style={{ color: '#64748b' }}>{listing.dispensary_slug}</span>}
        </td>
        <td style={{ ...tdStyle, color: '#f1f5f9' }}>{listing.scraped_name}</td>
        <td style={tdStyle}>{listing.scraped_brand ?? <span style={{ color: '#475569' }}>—</span>}</td>
        <td style={tdStyle}>{listing.variant ?? <span style={{ color: '#475569' }}>—</span>}</td>
        <td style={tdStyle}>{listing.scraped_category ?? <span style={{ color: '#475569' }}>—</span>}</td>
        <td style={{ ...tdStyle, fontVariantNumeric: 'tabular-nums' }}>
          {listing.price_cents != null ? `$${(listing.price_cents / 100).toFixed(2)}` : <span style={{ color: '#475569' }}>—</span>}
        </td>
        <td style={tdStyle}>
          {topCandidate ? (
            <span>{scoreBadge(topCandidate.score)}<span style={{ color: '#94a3b8' }}>{topCandidate.product_name}</span></span>
          ) : (
            <span style={{ color: '#475569' }}>no candidates</span>
          )}
        </td>
        <td style={{ ...tdStyle, textAlign: 'right' }} onClick={e => e.stopPropagation()}>
          <button
            onClick={handleCreateNew}
            disabled={confirming}
            style={{
              padding: '3px 10px', fontSize: 12,
              cursor: confirming ? 'not-allowed' : 'pointer',
              background: '#1e293b', color: '#94a3b8',
              border: '1px solid #334155', borderRadius: 4,
            }}
          >
            New Product
          </button>
        </td>
      </tr>

      {error && (
        <tr>
          <td colSpan={10} style={{ color: '#f87171', padding: '4px 12px', fontSize: 12, background: '#1a0a0a' }}>
            {error}
          </td>
        </tr>
      )}

      {expanded && listing.candidates.map(c => (
        <CandidateRow key={c.product_id} candidate={c} onConfirm={handleConfirm} confirming={confirming} />
      ))}
    </>
  )
}

export default function ListingMatch() {
  const [listings, setListings]   = useState<UnmatchedListing[]>([])
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState<string | null>(null)
  const [hasMore, setHasMore]     = useState(true)
  const [selected, setSelected]   = useState<Set<string>>(new Set())
  const [bulking, setBulking]     = useState(false)
  const [bulkError, setBulkError] = useState<string | null>(null)
  const [sortDesc, setSortDesc]   = useState(true)
  const navigate = useNavigate()
  const LIMIT = 50

  useEffect(() => { load(true) }, [])

  async function load(reset = false, currentListings: UnmatchedListing[] = []) {
    setLoading(true)
    setError(null)
    const offset = reset ? 0 : currentListings.length
    try {
      const data = await api.listings.listUnmatched({ limit: LIMIT, offset })
      setListings(reset ? data : [...currentListings, ...data])
      setHasMore(data.length === LIMIT)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function handleMatched(id: string) {
    setListings(prev => prev.filter(l => l.id !== id))
    setSelected(prev => { const s = new Set(prev); s.delete(id); return s })
  }

  function toggleSelect(id: string) {
    setSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s })
  }

  const sorted = [...listings].sort((a, b) => {
    const sa = a.candidates[0]?.score ?? -1
    const sb = b.candidates[0]?.score ?? -1
    return sortDesc ? sb - sa : sa - sb
  })

  const allSelected = listings.length > 0 && listings.every(l => selected.has(l.id))
  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(listings.map(l => l.id)))
  }

  async function handleBulkNewProduct() {
    if (selected.size === 0) return
    setBulking(true)
    setBulkError(null)
    try {
      const result = await api.listings.bulkCreateProducts(Array.from(selected))
      setListings(prev => prev.filter(l => !selected.has(l.id)))
      setSelected(new Set())
      if (result.errors.length > 0) {
        setBulkError(`${result.created} created, ${result.errors.length} errors: ${result.errors.map(e => e.error).join(', ')}`)
      }
    } catch (e: any) {
      setBulkError(e.message)
    } finally {
      setBulking(false)
    }
  }

  return (
    <div style={{ padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <button onClick={() => navigate('/admin')} style={navBtnStyle}>← Admin</button>
          <div>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Unmatched Listings</h2>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: '#475569' }}>
              {listings.length} listing{listings.length !== 1 ? 's' : ''} — click a row to see candidates
            </p>
          </div>
          <button onClick={() => navigate('/admin/listings')} style={{ ...navBtnStyle, marginLeft: 'auto' }}>
            All listings →
          </button>
        </div>

        {selected.size > 0 && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12,
            background: '#0f172a', padding: '10px 16px', borderRadius: 6,
            marginBottom: 12, border: '1px solid #1e293b',
          }}>
            <span style={{ fontSize: 13, color: '#94a3b8' }}>{selected.size} selected</span>
            <button
              onClick={handleBulkNewProduct}
              disabled={bulking}
              style={{ padding: '4px 14px', fontSize: 13, background: '#1e293b', color: '#94a3b8', border: '1px solid #334155', borderRadius: 4, cursor: bulking ? 'not-allowed' : 'pointer' }}
            >
              {bulking ? 'Creating…' : `New Product for ${selected.size} selected`}
            </button>
            <button
              onClick={() => setSelected(new Set())}
              style={{ padding: '4px 10px', fontSize: 12, background: 'transparent', color: '#64748b', border: '1px solid #1e293b', borderRadius: 4, cursor: 'pointer' }}
            >
              Clear
            </button>
            {bulkError && <span style={{ color: '#f87171', fontSize: 12 }}>{bulkError}</span>}
          </div>
        )}

        {error && <div style={{ color: '#f87171', marginBottom: 12 }}>{error}</div>}

        {!loading && listings.length === 0 ? (
          <div style={{ color: '#475569', padding: 16 }}>All listings matched.</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ color: '#475569', textAlign: 'left', borderBottom: '1px solid #1e293b' }}>
                <th style={{ width: 32, padding: '8px', textAlign: 'center' }}>
                  <input type="checkbox" checked={allSelected} onChange={toggleAll} style={{ cursor: 'pointer' }} />
                </th>
                <th style={{ width: 24 }} />
                <th style={thStyle}>Dispensary</th>
                <th style={thStyle}>Scraped Name</th>
                <th style={thStyle}>Brand</th>
                <th style={thStyle}>Variant</th>
                <th style={thStyle}>Category</th>
                <th style={thStyle}>Price</th>
                <th style={{ ...thStyle, cursor: 'pointer', userSelect: 'none' }} onClick={() => setSortDesc(d => !d)}>
                  Top Match {sortDesc ? '↓' : '↑'}
                </th>
                <th style={thStyle} />
              </tr>
            </thead>
            <tbody>
              {sorted.map(l => (
                <ListingRow
                  key={l.id}
                  listing={l}
                  onMatched={handleMatched}
                  selected={selected.has(l.id)}
                  onToggleSelect={toggleSelect}
                />
              ))}
            </tbody>
          </table>
        )}

        {hasMore && !loading && listings.length > 0 && (
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <button onClick={() => load(false, listings)} style={navBtnStyle}>Load more</button>
          </div>
        )}

        {loading && (
          <div style={{ marginTop: 16, textAlign: 'center', color: '#475569' }}>Loading…</div>
        )}
      </div>
    </div>
  )
}

const thStyle: React.CSSProperties = { padding: '8px 12px', fontWeight: 500, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }
const tdStyle: React.CSSProperties = { padding: '10px 12px', color: '#cbd5e1' }
const navBtnStyle: React.CSSProperties = { padding: '6px 12px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 13 }
