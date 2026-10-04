// The web portal's ui/my-app/src/utils/phone.ts, minus its Vite env read (Metro
// has no import.meta.env). Keep the two in step.

const COUNTRY_CODE = '1'

/** Normalize user input to E.164, or null if it can't be a valid number. */
export function toE164(input: string): string | null {
  const raw = (input || '').trim()
  if (!raw) return null

  if (raw.startsWith('+')) {
    const digits = raw.slice(1).replace(/\D/g, '')
    return digits.length >= 8 && digits.length <= 15 ? `+${digits}` : null
  }

  let digits = raw.replace(/\D/g, '')
  if (digits.length === 11 && digits.startsWith(COUNTRY_CODE)) digits = digits.slice(1)
  return digits.length === 10 ? `+${COUNTRY_CODE}${digits}` : null
}

/** US numbers get (555) 123-4567 as they are typed; "+..." is left alone. */
export function formatPhoneInput(input: string): string {
  if (input.trim().startsWith('+')) return input
  const d = input.replace(/\D/g, '').slice(0, 10)
  if (d.length <= 3) return d
  if (d.length <= 6) return `(${d.slice(0, 3)}) ${d.slice(3)}`
  return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`
}

export function formatE164ForDisplay(e164: string): string {
  if (/^\+1\d{10}$/.test(e164)) {
    const d = e164.slice(2)
    return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`
  }
  return e164
}
