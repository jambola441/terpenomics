/* ============================================================================
   AdminTable.tsx — the one table used across every admin screen.

   Owns ONLY the table chrome: header row, sortable header affordance (↑/↓),
   row hover, row-click navigation, and the shared dark-admin style tokens.

   It does NOT own filtering or pagination — those stay custom per page. Each
   page computes its own `rows` (via URL params, hooks, cascade facets, …) and
   passes them in. Sorting is *controlled*: pass `sorting={{ sort, order, onSort }}`
   and the page keeps its existing handleSort/URL logic untouched.
   ========================================================================== */

import type { CSSProperties, ReactNode, Key } from 'react'

/* ── Shared admin style tokens (previously copy-pasted into every page) ─────── */

export const pageWrap: CSSProperties = { padding: 24, fontFamily: "'Inter', system-ui, sans-serif", background: '#080d18', minHeight: '100vh', color: '#f1f5f9' }
export const thStyle: CSSProperties = { padding: '8px 12px', fontWeight: 500, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }
export const tdStyle: CSSProperties = { padding: '10px 12px', color: '#cbd5e1' }
export const navBtnStyle: CSSProperties = { padding: '6px 12px', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 13 }
export const selectStyle: CSSProperties = { fontSize: 13, padding: '5px 8px', borderRadius: 4, background: '#0f172a', border: '1px solid #1e293b', color: '#94a3b8' }
export const badge: CSSProperties = { padding: '2px 7px', borderRadius: 4, fontSize: 11, fontWeight: 500 }

/** The muted em-dash used for empty cells everywhere. */
export const Dash = () => <span style={{ color: '#475569' }}>—</span>

const CATEGORY_COLORS: Record<string, { background: string; color: string }> = {
  flower:      { background: '#14532d', color: '#86efac' },
  preroll:     { background: '#1a2e05', color: '#a3e635' },
  vaporizers:  { background: '#1e1b4b', color: '#a5b4fc' },
  concentrate: { background: '#431407', color: '#fdba74' },
  edible:      { background: '#4a1942', color: '#f0abfc' },
  tinctures:   { background: '#0c4a6e', color: '#7dd3fc' },
  topical:     { background: '#3b3a2a', color: '#fde68a' },
  merch:       { background: '#1c1917', color: '#a8a29e' },
}

/** Badge background/foreground for a category (falls back to slate). */
export function categoryColor(cat: string) {
  return CATEGORY_COLORS[cat] ?? { background: '#1e293b', color: '#94a3b8' }
}

/* ── Types ──────────────────────────────────────────────────────────────────── */

export type SortState = {
  /** active sort column key */
  sort: string
  /** 'asc' | 'desc' */
  order: string
  /** called with a column key when a sortable header is clicked */
  onSort: (col: string) => void
}

export type Column<T> = {
  /** stable key; also the value passed to onSort when this column is sortable */
  key: string
  header: ReactNode
  /** show the sort affordance and call sorting.onSort on click */
  sortable?: boolean
  /** cell text alignment (header alignment is controlled via `th`) */
  align?: 'left' | 'center' | 'right'
  /** extra style merged into this column's <th> */
  th?: CSSProperties
  /** extra style merged into this column's <td> */
  td?: CSSProperties
  /** stop row-click propagation from inside this cell (e.g. external links) */
  stopPropagation?: boolean
  render: (row: T, index: number) => ReactNode
}

/* ── AdminTable ─────────────────────────────────────────────────────────────── */

export function AdminTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  sorting,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T, index: number) => Key
  onRowClick?: (row: T) => void
  sorting?: SortState
}) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
      <thead>
        <tr style={{ color: '#475569', textAlign: 'left', borderBottom: '1px solid #1e293b' }}>
          {columns.map(col => {
            if (col.sortable && sorting) {
              const active = sorting.sort === col.key
              return (
                <th
                  key={col.key}
                  style={{ ...thStyle, cursor: 'pointer', userSelect: 'none', ...col.th }}
                  onClick={() => sorting.onSort(col.key)}
                >
                  {col.header}
                  {active && <span style={{ marginLeft: 4, color: '#6366f1' }}>{sorting.order === 'asc' ? '↑' : '↓'}</span>}
                </th>
              )
            }
            return (
              <th key={col.key} style={{ ...thStyle, ...col.th }}>
                {col.header}
              </th>
            )
          })}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr
            key={rowKey(row, i)}
            style={{ borderBottom: '1px solid #0f172a', cursor: onRowClick ? 'pointer' : 'default' }}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            onMouseEnter={e => (e.currentTarget as HTMLTableRowElement).style.background = '#0f172a'}
            onMouseLeave={e => (e.currentTarget as HTMLTableRowElement).style.background = 'transparent'}
          >
            {columns.map(col => (
              <td
                key={col.key}
                style={{ ...tdStyle, ...(col.align ? { textAlign: col.align } : null), ...col.td }}
                onClick={col.stopPropagation ? e => e.stopPropagation() : undefined}
              >
                {col.render(row, i)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
