/* ============================================================================
   ConfirmSheet — a question with two labelled answers, from the bottom.

   Stands in for the browser's confirm(), which can't be styled, can't label
   its buttons (so "OK" ends up meaning "empty my cart"), and on a phone looks
   like a security prompt. The safe answer is focused first, so Enter or a
   stray tap never takes the destructive one.
   ========================================================================== */

import { useId, useRef, type ReactNode } from 'react'
import { t, radius, font, tone } from '../theme'
import { useDialog } from '../hooks/useDialog'

export default function ConfirmSheet({
  open, title, children, confirmLabel, cancelLabel = 'Cancel', destructive = false, busy = false,
  onConfirm, onCancel,
}: {
  open: boolean
  title: string
  children?: ReactNode
  confirmLabel: string
  cancelLabel?: string
  /** Draws the confirm answer in the danger tone. */
  destructive?: boolean
  /** The confirmed action is running: both answers wait. */
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const sheet = useRef<HTMLDivElement>(null)
  const safe = useRef<HTMLButtonElement>(null)
  const titleId = useId()
  useDialog(sheet, open, { onEscape: busy ? undefined : onCancel, initialFocus: safe })

  if (!open) return null
  return (
    <>
      <div
        onClick={busy ? undefined : onCancel}
        style={{ position: 'fixed', inset: 0, background: t.scrim, zIndex: 2500, backdropFilter: 'blur(2px)' }}
      />
      <div
        ref={sheet}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        style={{
          position: 'fixed', left: 0, right: 0, bottom: 0, zIndex: 2600,
          background: t.surface1, borderTop: `1px solid ${t.border}`,
          borderRadius: `${radius['2xl']} ${radius['2xl']} 0 0`, boxShadow: 'var(--e-3)',
          padding: '20px 20px calc(20px + env(safe-area-inset-bottom, 0px))',
          animation: 'ds-fade-in 0.2s ease',
        }}
      >
        <div style={{ maxWidth: 520, margin: '0 auto' }}>
          <h2 id={titleId} style={{
            margin: 0, color: t.text1, fontFamily: font.family.display, fontWeight: font.weight.semibold,
            fontSize: font.size.heading, letterSpacing: '-0.015em',
          }}>
            {title}
          </h2>
          {children && (
            <div style={{ color: t.text2, fontSize: font.size.body, lineHeight: 1.55, marginTop: 8 }}>{children}</div>
          )}
          <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
            <button
              ref={safe}
              onClick={onCancel}
              disabled={busy}
              style={{
                flex: 1, minHeight: 48, background: t.surface2, border: `1px solid ${t.borderStrong}`,
                borderRadius: radius.md, color: t.text1, fontSize: font.size.callout,
                fontWeight: font.weight.semibold, cursor: busy ? 'default' : 'pointer',
              }}
            >
              {cancelLabel}
            </button>
            <button
              onClick={onConfirm}
              disabled={busy}
              style={{
                flex: 1, minHeight: 48, borderRadius: radius.md, fontSize: font.size.callout,
                fontWeight: font.weight.bold, cursor: busy ? 'default' : 'pointer',
                ...(destructive
                  ? { background: 'transparent', border: `1px solid ${tone.danger.edge}`, color: tone.danger.fg }
                  : { background: t.accent, border: 'none', color: t.accentInk }),
              }}
            >
              {busy ? 'One moment…' : confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
