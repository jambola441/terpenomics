/* ============================================================================
   AdminTable.tsx — the one table used across every admin screen.

   Owns ONLY the table chrome: header row, sortable header affordance (↑/↓),
   row hover, row-click navigation, and the shared dark-admin style tokens.

   It does NOT own filtering or pagination — those stay custom per page. Each
   page computes its own `rows` (via URL params, hooks, cascade facets, …) and
   passes them in. Sorting is *controlled*: pass `sorting={{ sort, order, onSort }}`
   and the page keeps its existing handleSort/URL logic untouched.

   Row selection is controlled the same way: pass `selection={{ selected, onToggle,
   onToggleAll }}` and a leading checkbox column appears. The table owns the checkbox
   chrome (header state, shift-click reporting, not letting a checkbox click count as
   a row click); the page owns the selected set and whatever it does with it.
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

export type SelectionState<T> = {
  /** keys (as returned by `rowKey`) of the currently selected rows */
  selected: Set<Key>
  /**
   * A row's checkbox was clicked. `shift` is true when the click was made with
   * shift held, which pages conventionally treat as "extend from the last click" —
   * the table reports it rather than interpreting it, because the anchor belongs to
   * the page's own list of rows.
   */
  onToggle: (row: T, index: number, shift: boolean) => void
  /** Header checkbox: select every row currently rendered, or clear the selection. */
  onToggleAll: (checked: boolean) => void
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
  selection,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T, index: number) => Key
  onRowClick?: (row: T) => void
  sorting?: SortState
  selection?: SelectionState<T>
}) {
  const selectedHere = selection ? rows.filter((r, i) => selection.selected.has(rowKey(r, i))).length : 0
  const allSelected = selectedHere > 0 && selectedHere === rows.length

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
      <thead>
        <tr style={{ color: '#475569', textAlign: 'left', borderBottom: '1px solid #1e293b' }}>
          {selection && (
            <th style={{ ...thStyle, width: 30, paddingRight: 0 }}>
              <input
                type="checkbox"
                checked={allSelected}
                // Some-but-not-all is a third state, and it is the one that matters
                // here: "select all" after a partial selection must add the rest
                // rather than look like it is already done.
                ref={el => { if (el) el.indeterminate = selectedHere > 0 && !allSelected }}
                onChange={e => selection.onToggleAll(e.target.checked)}
                title={allSelected ? 'Clear selection' : 'Select every row shown'}
                style={{ cursor: 'pointer' }}
              />
            </th>
          )}
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
        {rows.map((row, i) => {
          const key = rowKey(row, i)
          const isSelected = selection?.selected.has(key) ?? false
          const restingBg = isSelected ? '#111c33' : 'transparent'
          return (
          <tr
            key={key}
            style={{ borderBottom: '1px solid #0f172a', cursor: onRowClick ? 'pointer' : 'default', background: restingBg }}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            onMouseEnter={e => (e.currentTarget as HTMLTableRowElement).style.background = '#0f172a'}
            onMouseLeave={e => (e.currentTarget as HTMLTableRowElement).style.background = restingBg}
          >
            {selection && (
              <td
                style={{ ...tdStyle, width: 30, paddingRight: 0 }}
                // A checkbox click selects; it must never also open the row.
                onClick={e => e.stopPropagation()}
              >
                <input
                  type="checkbox"
                  checked={isSelected}
                  // Toggled from onClick rather than onChange: the change event does
                  // not carry modifier keys, and shift-click is how a range is
                  // selected. onChange still has to exist for a controlled checkbox.
                  onClick={e => selection.onToggle(row, i, e.shiftKey)}
                  onChange={() => {}}
                  style={{ cursor: 'pointer' }}
                />
              </td>
            )}
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
          )
        })}
      </tbody>
    </table>
  )
}
