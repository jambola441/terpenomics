// base.ts — resolves which API a given browser session talks to.
//
// Why this exists: VITE_API_BASE_URL is baked in at build time, and Render PR
// previews inherit the base service's env vars. Without this, a preview build of
// the UI would silently point at the production API. See PREVIEWS.md.
//
// Resolution order (first match wins):
//   1. ?api=<url> query param  (?api=reset clears the stored override)
//   2. a previously stored override in localStorage
//   3. derived from the hostname when running as a Render PR preview
//   4. VITE_API_BASE_URL from the build
//   5. hardcoded dev fallback

const STORAGE_KEY = 'terpenomics.apiBase'

// Name of the Render web service running the API. A preview of it is published
// at https://<name>-pr-<number>.onrender.com.
const API_SERVICE_NAME = import.meta.env.VITE_PREVIEW_API_SERVICE || 'terpenomics'

const BUILD_API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  'https://sturdy-parakeet-qg59j4pjp9q29j9j-8000.app.github.dev'

// Any Render preview host: terpenomics-ui-pr-42.onrender.com
const PREVIEW_HOST = /-pr-(\d+)\.onrender\.com$/

export type ApiSource = 'override' | 'pr-preview' | 'build' | 'fallback'

function trimSlash(url: string): string {
  return url.replace(/\/+$/, '')
}

function readStored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStored(url: string | null): void {
  try {
    if (url) localStorage.setItem(STORAGE_KEY, url)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    // private browsing / storage disabled — the override just won't persist
  }
}

// Pulls ?api= off the URL, persists it, and rewrites the address bar so the
// param doesn't get copied around with every subsequent link.
function consumeQueryOverride(): string | null {
  const params = new URLSearchParams(window.location.search)
  const raw = params.get('api')
  if (raw === null) return null

  const value = raw.trim()
  const cleared = value === '' || value === 'reset' || value === 'clear'
  const next = cleared ? null : trimSlash(value)

  writeStored(next)

  params.delete('api')
  const qs = params.toString()
  window.history.replaceState(
    {},
    '',
    window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash,
  )

  return next
}

function resolve(): { base: string; source: ApiSource } {
  if (typeof window === 'undefined') {
    return { base: trimSlash(BUILD_API_BASE), source: 'build' }
  }

  const fromQuery = consumeQueryOverride()
  if (fromQuery) return { base: fromQuery, source: 'override' }

  const stored = readStored()
  if (stored) return { base: trimSlash(stored), source: 'override' }

  const pr = window.location.hostname.match(PREVIEW_HOST)
  if (pr) {
    return {
      base: `https://${API_SERVICE_NAME}-pr-${pr[1]}.onrender.com`,
      source: 'pr-preview',
    }
  }

  return {
    base: trimSlash(BUILD_API_BASE),
    source: import.meta.env.VITE_API_BASE_URL ? 'build' : 'fallback',
  }
}

const resolved = resolve()

export const API_BASE = resolved.base
export const API_SOURCE: ApiSource = resolved.source

// True when this session is NOT talking to the API the build was pinned to —
// i.e. a PR preview or a manual override. Used to show the preview badge.
export const IS_NON_DEFAULT_API =
  API_SOURCE === 'override' || API_SOURCE === 'pr-preview'

export function clearApiOverride(): void {
  writeStored(null)
  window.location.reload()
}
