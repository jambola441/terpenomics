/* ============================================================================
   PreviewBadge.tsx — "which API am I actually looking at?"

   Renders nothing in normal production use. It only appears when the session is
   pointed somewhere other than the API this build was pinned to: a Render PR
   preview, or a manual ?api= override. That is exactly when it matters — the
   admin UI looks identical whether it is editing preview data or real data.

   Tap it to see the full API host and clear the override. See PREVIEWS.md.
   ========================================================================== */

import { useState } from 'react'
import { API_BASE, API_SOURCE, IS_NON_DEFAULT_API, clearApiOverride } from '../api/base'

export default function PreviewBadge() {
  const [open, setOpen] = useState(false)

  if (!IS_NON_DEFAULT_API) return null

  const isPr = API_SOURCE === 'pr-preview'
  const label = isPr ? 'PR preview' : 'Custom API'
  const accent = isPr ? '#fbbf24' : '#f87171'
  const host = API_BASE.replace(/^https?:\/\//, '')

  return (
    <div style={wrap}>
      {open && (
        <div style={panel}>
          <div style={panelLabel}>API</div>
          <div style={panelHost}>{host}</div>
          <button onClick={clearApiOverride} style={resetBtn}>
            Use default API
          </button>
        </div>
      )}
      <button
        onClick={() => setOpen(o => !o)}
        style={{ ...pill, borderColor: accent, color: accent }}
        title={API_BASE}
      >
        <span style={{ ...dot, background: accent }} />
        {label}
      </button>
    </div>
  )
}

const wrap: React.CSSProperties = {
  position: 'fixed',
  right: 12,
  bottom: 'calc(12px + env(safe-area-inset-bottom, 0px))',
  zIndex: 9999,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'flex-end',
  gap: 8,
  fontFamily: "'Inter', system-ui, sans-serif",
}

const pill: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  padding: '6px 11px',
  background: '#0f172a',
  border: '1px solid',
  borderRadius: 999,
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '0.04em',
  textTransform: 'uppercase',
  cursor: 'pointer',
  boxShadow: '0 6px 20px rgba(0,0,0,0.45)',
}

const dot: React.CSSProperties = { width: 6, height: 6, borderRadius: '50%' }

const panel: React.CSSProperties = {
  maxWidth: 'min(320px, calc(100vw - 24px))',
  background: '#0f172a',
  border: '1px solid #1e293b',
  borderRadius: 10,
  padding: '12px 14px',
  boxShadow: '0 16px 40px rgba(0,0,0,0.5)',
}

const panelLabel: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  color: '#475569',
  marginBottom: 4,
}

const panelHost: React.CSSProperties = {
  fontSize: 12,
  color: '#cbd5e1',
  wordBreak: 'break-all',
  marginBottom: 10,
  lineHeight: 1.4,
}

const resetBtn: React.CSSProperties = {
  width: '100%',
  padding: '7px 0',
  background: '#1e293b',
  border: 'none',
  borderRadius: 6,
  color: '#94a3b8',
  fontSize: 12,
  fontWeight: 500,
  cursor: 'pointer',
}
