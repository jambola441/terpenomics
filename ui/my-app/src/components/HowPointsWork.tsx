/* ============================================================================
   HowPointsWork — the points program in three steps and a few questions.

   The words come from utils/pointsProgram.ts and the numbers from the API, so
   this page, the partners list and the app all say the same thing, and none of
   them can promise a rule the ledger doesn't keep.
   ========================================================================== */

import { useEffect, useState } from 'react'
import api from '../api/client'
import type { PointsProgram } from '../types'
import { t, radius, font } from '../theme'
import { PARTNER_DEFINITION, questions, steps } from '../utils/pointsProgram'
import { BackButton, FeedState, Label, PageTitle } from './ui'
import { Icon } from './Icon'

/** The three numbered steps, for this page and the top of the partners list. */
export function PointsSteps({ program, compact = false }: { program: PointsProgram; compact?: boolean }) {
  return (
    <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: compact ? 12 : 18 }}>
      {steps(program).map((s, i) => (
        <li key={s.title} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <span aria-hidden style={{
            width: 26, height: 26, borderRadius: '50%', flexShrink: 0, marginTop: 1,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            background: t.accentTint, border: `1px solid ${t.accentDim}`, color: t.accent,
            fontFamily: font.family.mono, fontSize: font.size.small, fontWeight: font.weight.bold,
          }}>
            {i + 1}
          </span>
          <div style={{ minWidth: 0 }}>
            <div style={{ color: t.text1, fontSize: font.size.callout, fontWeight: font.weight.semibold }}>{s.title}</div>
            {!compact && <div style={{ color: t.text2, fontSize: font.size.small + 1, lineHeight: 1.55, marginTop: 3 }}>{s.body}</div>}
          </div>
        </li>
      ))}
    </ol>
  )
}

export default function HowPointsWork({ onBack, onOpenPartners }: { onBack: () => void; onOpenPartners: () => void }) {
  const [program, setProgram] = useState<PointsProgram | null>(null)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let live = true
    setError(false)
    api.portal.getPartners()
      .then(r => { if (live) setProgram(r.program) })
      .catch(() => { if (live) setError(true) })
    return () => { live = false }
  }, [attempt])

  return (
    <div style={{ height: 'calc(100dvh - var(--chrome-bottom, 64px))', overflowY: 'auto', background: t.bg }}>
      <div style={{ padding: 'calc(env(safe-area-inset-top, 0px) + 16px) 16px 32px', maxWidth: 560, margin: '0 auto' }}>
        <BackButton onClick={onBack} />
        <PageTitle sub={PARTNER_DEFINITION} style={{ margin: '16px 0 24px' }}>How points work</PageTitle>

        {error ? (
          <FeedState kind="error" message="Couldn't load the details" onRetry={() => setAttempt(n => n + 1)} />
        ) : !program ? (
          <FeedState kind="loading" message="Loading…" />
        ) : (
          <>
            <PointsSteps program={program} />

            <button
              onClick={onOpenPartners}
              style={{
                marginTop: 24, width: '100%', minHeight: 48, borderRadius: radius.md, cursor: 'pointer',
                background: t.accent, border: 'none', color: t.accentInk,
                fontSize: font.size.callout, fontWeight: font.weight.semibold,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              }}
            >
              <Icon name="pin" size={17} />
              See partner stores
            </button>

            <Label style={{ margin: '32px 0 6px' }}>Questions</Label>
            <div>
              {questions(program).map(item => (
                <div key={item.q} style={{ padding: '14px 0', borderBottom: `1px solid ${t.border}` }}>
                  <div style={{ color: t.text1, fontSize: font.size.callout, fontWeight: font.weight.semibold }}>{item.q}</div>
                  <div style={{ color: t.text2, fontSize: font.size.small + 1, lineHeight: 1.55, marginTop: 4 }}>{item.a}</div>
                </div>
              ))}
            </div>
            <div style={{ color: t.text3, fontSize: font.size.small, lineHeight: 1.5, marginTop: 16 }}>
              The full rules are in the <a href="/terms" style={{ color: t.text2 }}>Terms</a>.
            </div>
          </>
        )}
      </div>
    </div>
  )
}
