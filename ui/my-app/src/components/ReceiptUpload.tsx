/* ============================================================================
   ReceiptUpload — claim points for a partner purchase that didn't match.

   The POS sync finds purchases by the phone number given at checkout. When a
   shopper didn't give one, or the store's POS isn't connected, they upload the
   receipt here; a person checks it and the points follow (connectors/receipts.py).
   Lives in the Points pane, with the shopper's past uploads and their status.
   ========================================================================== */

import { useEffect, useRef, useState } from 'react'
import api from '../api/client'
import type { MyReceipt, PartnerOption } from '../types'
import { t, radius, font } from '../theme'
import { Label, Spinner } from './ui'
import { Icon } from './Icon'
import { formatDate, formatDollars } from '../utils/format'
import { shrinkReceipt } from '../utils/receiptImage'

function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const field = {
  width: '100%', boxSizing: 'border-box' as const, padding: '11px 12px', borderRadius: radius.md,
  background: t.surface2, border: `1px solid ${t.border}`, color: t.text1, fontSize: font.size.callout,
}

export default function ReceiptUpload({ onUploaded }: { onUploaded?: () => void }) {
  const [open, setOpen] = useState(false)
  const [partners, setPartners] = useState<PartnerOption[] | null>(null)
  const [receipts, setReceipts] = useState<MyReceipt[] | null>(null)
  const [partnerId, setPartnerId] = useState('')
  const [day, setDay] = useState(today())
  const [note, setNote] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  function loadReceipts() {
    api.me.getReceipts().then(setReceipts).catch(() => setReceipts([]))
  }

  useEffect(() => { loadReceipts() }, [])
  useEffect(() => {
    if (open && partners === null) api.me.getPartners().then(setPartners).catch(() => setPartners([]))
  }, [open, partners])
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])

  function pick(f: File | null) {
    setFile(f)
    setError(null)
    if (preview) URL.revokeObjectURL(preview)
    setPreview(f ? URL.createObjectURL(f) : null)
  }

  async function submit() {
    if (!file || !partnerId) return
    setBusy(true)
    setError(null)
    try {
      const image = await shrinkReceipt(file)
      await api.me.uploadReceipt({
        partnerId, purchasedOn: day, note: note.trim() || undefined, image,
        filename: image === file ? file.name : 'receipt.jpg',
      })
      setDone(true)
      setOpen(false)
      pick(null)
      setNote('')
      loadReceipts()
      onUploaded?.()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {!open ? (
        <button
          onClick={() => { setOpen(true); setDone(false) }}
          style={{
            padding: '13px 16px', borderRadius: radius.lg, cursor: 'pointer',
            background: 'transparent', border: `1px dashed ${t.borderStrong}`,
            color: t.text1, fontSize: font.size.callout, fontWeight: font.weight.semibold, textAlign: 'left',
            display: 'flex', alignItems: 'flex-start', gap: 12,
          }}
        >
          <Icon name="receipt" size={20} color={t.text3} style={{ marginTop: 1 }} />
          <span>
            Upload a receipt
            <span style={{ display: 'block', color: t.text3, fontSize: font.size.small, fontWeight: font.weight.regular, marginTop: 3, lineHeight: 1.45 }}>
              Didn't give your number at a partner store? Send us the receipt and we'll add the points.
            </span>
          </span>
        </button>
      ) : (
        <div style={{
          background: t.surface1, border: `1px solid ${t.border}`, borderRadius: radius.lg,
          padding: 16, display: 'flex', flexDirection: 'column', gap: 12,
        }}>
          <div style={{ color: t.text1, fontWeight: font.weight.bold, fontSize: font.size.callout }}>Upload a receipt</div>

          <div>
            <Label>Store</Label>
            <select value={partnerId} onChange={e => setPartnerId(e.target.value)} style={{ ...field, marginTop: 6 }} aria-label="Store">
              <option value="">{partners === null ? 'Loading…' : 'Choose the store'}</option>
              {(partners ?? []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>

          <div>
            <Label>Date of purchase</Label>
            <input type="date" value={day} max={today()} onChange={e => setDay(e.target.value)} style={{ ...field, marginTop: 6 }} aria-label="Date of purchase" />
          </div>

          <div>
            <Label>Photo of the receipt</Label>
            <input
              ref={input}
              type="file"
              accept="image/*"
              capture="environment"
              onChange={e => pick(e.target.files?.[0] ?? null)}
              style={{ display: 'none' }}
              aria-label="Receipt photo"
            />
            {preview ? (
              <div style={{ marginTop: 6, display: 'flex', gap: 12, alignItems: 'center' }}>
                <img src={preview} alt="Receipt" style={{ width: 72, height: 96, objectFit: 'cover', borderRadius: radius.sm, border: `1px solid ${t.border}` }} />
                <button onClick={() => input.current?.click()} style={{ ...field, width: 'auto', cursor: 'pointer' }}>Retake</button>
              </div>
            ) : (
              <button onClick={() => input.current?.click()} style={{ ...field, marginTop: 6, cursor: 'pointer', textAlign: 'left', color: t.text3 }}>
                Take or choose a photo
              </button>
            )}
            <div style={{ color: t.text4, fontSize: font.size.small, marginTop: 6 }}>
              Make sure the store name, date and total are readable.
            </div>
          </div>

          <div>
            <Label>Note (optional)</Label>
            <input value={note} onChange={e => setNote(e.target.value)} maxLength={500} placeholder="Anything we should know" style={{ ...field, marginTop: 6 }} />
          </div>

          {error && <div style={{ color: t.danger, fontSize: font.size.small }}>{error}</div>}

          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={submit}
              disabled={busy || !file || !partnerId}
              style={{
                flex: 1, padding: '12px 0', borderRadius: radius.pill, border: 'none',
                background: busy || !file || !partnerId ? t.surface3 : t.accent,
                color: busy || !file || !partnerId ? t.text4 : t.accentInk,
                fontWeight: font.weight.bold, fontSize: font.size.callout,
                cursor: busy || !file || !partnerId ? 'default' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              }}
            >
              {busy && <Spinner size={14} />} {busy ? 'Uploading…' : 'Submit for review'}
            </button>
            <button
              onClick={() => { setOpen(false); setError(null) }}
              style={{ padding: '12px 16px', borderRadius: radius.pill, background: 'none', border: `1px solid ${t.border}`, color: t.text3, cursor: 'pointer' }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {done && (
        <div style={{ color: t.success, fontSize: font.size.small }}>
          Thanks! We'll check your receipt and add the points, usually within a day.
        </div>
      )}

      {receipts && receipts.length > 0 && (
        <div>
          <Label>Your receipts</Label>
          <div style={{ display: 'flex', flexDirection: 'column', marginTop: 4 }}>
            {receipts.map(r => (
              <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 2px', borderBottom: `1px solid ${t.border}` }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ color: t.text1, fontSize: font.size.callout, fontWeight: font.weight.semibold }}>{r.partner_name ?? 'Store'}</div>
                  <div style={{ color: t.text3, fontSize: font.size.small, marginTop: 2 }}>
                    {r.purchased_on ? formatDate(r.purchased_on + 'T12:00:00') : formatDate(r.created_at)}
                    {r.status === 'approved' && r.subtotal_cents != null ? ` · ${formatDollars(r.subtotal_cents)}` : ''}
                    {r.status === 'rejected' && r.reject_reason ? ` · ${r.reject_reason}` : ''}
                  </div>
                </div>
                <div style={{
                  fontSize: font.size.small, fontWeight: font.weight.bold,
                  color: r.status === 'approved' ? t.success : r.status === 'rejected' ? t.danger : t.text3,
                }}>
                  {r.status === 'approved' ? `+${r.points ?? 0}` : r.status === 'rejected' ? 'Not approved' : 'In review'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
