/**
 * Where to send someone once they have signed in.
 *
 * The value originates from a URL the visitor was trying to reach, so it is
 * treated as untrusted: only same-origin absolute paths are honoured, never a
 * full URL or a protocol-relative one. Otherwise the login page could be
 * handed "//evil.example" and turned into an open redirect.
 */
const KEY = 'auth:next'

// Control characters, which can be used to smuggle a scheme past the checks
// below.
const CONTROL_CHARS = /[\u0000-\u001F\u007F]/

export function safeNext(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const path = value.trim()

  // Must be an absolute path on this origin.
  if (!path.startsWith('/')) return null
  // "//host" and "/\host" are protocol-relative — a browser reads them as
  // pointing at another origin.
  if (path.startsWith('//') || path.startsWith('/\\')) return null
  if (CONTROL_CHARS.test(path)) return null

  // Returning to the login page after logging in would loop.
  if (path === '/' || path.startsWith('/auth/callback')) return null

  return path
}

/**
 * OAuth leaves the app entirely, so router state does not survive the round
 * trip. sessionStorage does, and is scoped to this tab and origin.
 */
export function rememberNext(value: string | null): void {
  try {
    if (value) sessionStorage.setItem(KEY, value)
    else sessionStorage.removeItem(KEY)
  } catch {
    // Private mode or blocked storage: fall back to the default destination.
  }
}

export function takeNext(): string | null {
  try {
    const stored = sessionStorage.getItem(KEY)
    sessionStorage.removeItem(KEY)
    return safeNext(stored)
  } catch {
    return null
  }
}
