// utils/phone.ts
// Phone helpers for SMS login. Supabase/Twilio require E.164 ("+15551234567").

const DEFAULT_COUNTRY_CODE =
  String(import.meta.env.VITE_DEFAULT_COUNTRY_CODE || '1').replace(/\D/g, '') || '1'

export const defaultCountryCode = DEFAULT_COUNTRY_CODE

/**
 * Normalize user input to E.164, or null if it can't be a valid number.
 * Anything typed with a leading "+" is treated as already international.
 */
export function toE164(input: string, countryCode: string = DEFAULT_COUNTRY_CODE): string | null {
  const raw = (input || '').trim()
  if (!raw) return null

  if (raw.startsWith('+')) {
    const digits = raw.slice(1).replace(/\D/g, '')
    return digits.length >= 8 && digits.length <= 15 ? `+${digits}` : null
  }

  let digits = raw.replace(/\D/g, '')
  if (!digits) return null

  if (countryCode === '1') {
    // NANP: 10 digits, or 11 with the leading country code.
    if (digits.length === 11 && digits.startsWith('1')) digits = digits.slice(1)
    if (digits.length !== 10) return null
    return `+1${digits}`
  }

  // Other countries: drop a national trunk prefix, add the country code if missing.
  digits = digits.replace(/^0+/, '')
  if (!digits.startsWith(countryCode)) digits = countryCode + digits
  return digits.length >= 8 && digits.length <= 15 ? `+${digits}` : null
}

/** Format as the user types. US numbers get (555) 123-4567; everything else is left alone. */
export function formatPhoneInput(input: string, countryCode: string = DEFAULT_COUNTRY_CODE): string {
  if (input.trim().startsWith('+') || countryCode !== '1') return input

  const d = input.replace(/\D/g, '').slice(0, 10)
  if (d.length <= 3) return d
  if (d.length <= 6) return `(${d.slice(0, 3)}) ${d.slice(3)}`
  return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`
}

/** Human-readable version of an E.164 number, for the "we sent a code to ..." line. */
export function formatE164ForDisplay(e164: string): string {
  if (/^\+1\d{10}$/.test(e164)) {
    const d = e164.slice(2)
    return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`
  }
  return e164
}
