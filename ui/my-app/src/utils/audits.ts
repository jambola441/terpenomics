import type { AuditFix, AuditItem, ProposalKind } from '../types'
import type { tone } from '../theme'

/** An error rate (0-1) as a percentage, or a dash. */
export function pct(rate: number | null | undefined): string {
  return rate == null ? '—' : `${Math.round(rate * 1000) / 10}%`
}

export function statusTone(status: string): keyof typeof tone {
  if (status === 'ready' || status === 'applied') return 'success'
  if (status === 'failed' || status === 'rejected') return 'danger'
  if (status === 'measured') return 'accent'
  return 'warning'
}

/** Timestamps from the API are naive UTC. */
export function when(iso: string | null | undefined): string {
  return iso ? new Date(iso.endsWith('Z') ? iso : iso + 'Z').toLocaleString() : '—'
}

export const PROPOSAL_KINDS: { kind: ProposalKind; label: string; hint: string }[] = [
  { kind: 'manual-match', label: 'Manual match', hint: '{"listing_id", "entry"}' },
  { kind: 'add-product', label: 'Add product', hint: '{"category", "subtype", "line", "strain", "sizes": [...]}' },
  { kind: 'add-size', label: 'Add size', hint: '{"entry", "size"}' },
  { kind: 'rekey', label: 'Re-key', hint: '{"entry" or "entries", "line", "strain", "subtype", "only"}' },
  { kind: 'set-subtype', label: 'Set subtype', hint: '{"entry", "subtype"}' },
  { kind: 'deactivate', label: 'Deactivate', hint: '{"entry", "into"?}' },
  { kind: 'add-example', label: 'Add reading example', hint: '{"listing", "size_field"?, "entry": {"category", "strain", "size", ...}}' },
  { kind: 'remove-example', label: 'Remove reading example', hint: '{"example_id"}' },
]

/** A proposal's kind and params drafted from the judge's proposed fix (or a blank
 *  manual match when it proposed none). The admin edits them before creating it. */
export function draftFromFix(item: AuditItem): { kind: ProposalKind; params: Record<string, unknown> } {
  const fix: AuditFix = item.proposed_fix ?? { kind: 'none' }
  const ev = item.evidence
  const entry = fix.entry_id || ev.entry?.id || ''
  const keep = (o: Record<string, unknown>) =>
    Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined && v !== '' && v !== null))
  switch (fix.kind) {
    case 'add-product':
      return { kind: 'add-product', params: keep({ category: fix.category || ev.entry?.category, subtype: fix.subtype,
        line: fix.line, strain: fix.strain, sizes: fix.size ? [fix.size] : [] }) }
    case 'add-size':
      return { kind: 'add-size', params: keep({ entry, size: fix.size }) }
    case 'rekey':
      return { kind: 'rekey', params: keep({ entry, line: fix.line, strain: fix.strain, subtype: fix.subtype }) }
    case 'set-subtype':
      return { kind: 'set-subtype', params: keep({ entry, subtype: fix.subtype }) }
    case 'deactivate':
      return { kind: 'deactivate', params: keep({ entry }) }
    case 'add-example':
      return { kind: 'add-example', params: keep({ listing: ev.listing?.name, size_field: ev.listing?.size_field,
        entry: keep({ category: ev.entry?.category, strain: ev.entry?.strain, size: ev.entry?.variant }) }) }
    default:
      return { kind: 'manual-match', params: { listing_id: item.listing_id, entry } }
  }
}
