import type { CSSProperties } from 'react'

/** Shared bits for the partner-store admin pages. */

export const inputStyle: CSSProperties = {
  fontSize: 13, padding: '8px 10px', borderRadius: 6,
  background: '#0f172a', border: '1px solid #1e293b', color: '#f1f5f9', outline: 'none',
}

export function primaryBtn(disabled = false): CSSProperties {
  return {
    padding: '8px 14px', borderRadius: 6, fontSize: 13, fontWeight: 500,
    background: disabled ? '#1e293b' : '#3730a3', border: '1px solid #4338ca',
    color: disabled ? '#64748b' : '#e0e7ff', cursor: disabled ? 'default' : 'pointer',
  }
}

export function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
}

export function money(cents: number, currency = 'USD'): string {
  return (cents / 100).toLocaleString(undefined, { style: 'currency', currency })
}

/** "3 min ago" for recent timestamps, the date otherwise. */
export function ago(iso: string | null): string {
  if (!iso) return 'never'
  const ms = Date.now() - new Date(iso).getTime()
  const min = Math.round(ms / 60000)
  if (min < 1) return 'just now'
  if (min < 60) return `${min} min ago`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr} hr ago`
  return new Date(iso).toLocaleDateString()
}

export function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—'
}
