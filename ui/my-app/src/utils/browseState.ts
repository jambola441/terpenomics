/* ============================================================================
   Keeping a browse screen's place.

   Filters and scroll position lived in component state, and a browse screen
   unmounts the moment a shopper opens a product from it. Going back rebuilt the
   screen from scratch: filters cleared, scrolled to the top, place lost.

   So filters live in the URL and scroll position is remembered per history
   entry. Both are restored by going back, and a filtered screen is now a link
   that can be shared or reloaded.
   ========================================================================== */

import { useEffect, useLayoutEffect, useRef, type RefObject } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'

/* ── Reading filters back out of the URL ──────────────────────────────────── */

/** Multi-select facets are repeated params (`brand=Aeris&brand=Botanica`) rather
 *  than one delimited value, because brand names contain commas and slashes. */
export function readSet(params: URLSearchParams, key: string): Set<string> {
  return new Set(params.getAll(key))
}

export function readOne(params: URLSearchParams, key: string): string | null {
  return params.get(key)
}

export function readNumber(params: URLSearchParams, key: string): number | null {
  const raw = params.get(key)
  if (raw == null) return null
  const value = Number(raw)
  return Number.isFinite(value) ? value : null
}

/** An inclusive range, serialized as `lo-hi`. */
export function readRange(params: URLSearchParams, key: string): [number, number] | null {
  const raw = params.get(key)
  if (!raw) return null
  const [lo, hi] = raw.split('-').map(Number)
  return Number.isFinite(lo) && Number.isFinite(hi) ? [lo, hi] : null
}

/** One of a known set of values, or the fallback — so a hand-edited URL cannot
 *  put a screen into a state it has no UI for. */
export function readEnum<T extends string>(
  params: URLSearchParams, key: string, allowed: readonly T[], fallback: T,
): T {
  const raw = params.get(key) as T | null
  return raw != null && allowed.includes(raw) ? raw : fallback
}

export function writeRange(range: [number, number] | null): string[] {
  return range ? [`${range[0]}-${range[1]}`] : []
}

export function writeOne(value: string | number | null | undefined): string[] {
  return value == null || value === '' ? [] : [String(value)]
}

export function writeSet(values: Set<string>): string[] {
  return [...values]
}

/* ── Writing them back in ─────────────────────────────────────────────────── */

/**
 * Mirror this screen's filters into the query string.
 *
 * Replaces rather than pushes: a shopper toggling four facets wants one Back to
 * leave the screen, not four to undo the toggles. Keys the screen does not own
 * are left alone, and a write that would not change anything is skipped —
 * a redundant replace mints a new history entry, which would strand the scroll
 * position saved against the old one.
 */
export function useFilterParams(values: Record<string, string[]>): void {
  const [searchParams, setSearchParams] = useSearchParams()

  const owned = Object.keys(values)
  const desired = new URLSearchParams(searchParams)
  for (const key of owned) desired.delete(key)
  for (const key of owned) for (const value of values[key]) desired.append(key, value)

  const next = desired.toString()
  const current = searchParams.toString()

  useEffect(() => {
    if (next === current) return
    setSearchParams(new URLSearchParams(next), { replace: true })
    // `next` is the whole serialized intent; the setter identity is not stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [next, current])
}

/* ── Scroll position ──────────────────────────────────────────────────────── */

// Per history entry, not per URL: two visits to the same filtered screen are
// two places in the shopper's history and each keeps its own offset. Cleared on
// reload along with the history stack it describes.
const offsets = new Map<string, number>()

/**
 * Remember where a scroll container was, and put it back on return.
 *
 * `ready` should become true once the list has rendered — a container cannot be
 * scrolled past content it does not have yet, so restoring too early silently
 * clamps to the top.
 */
export function useScrollMemory(ref: RefObject<HTMLElement | null>, ready: boolean): void {
  const { key } = useLocation()
  const restored = useRef(false)

  useEffect(() => {
    restored.current = false
  }, [key])

  useEffect(() => {
    const node = ref.current
    if (!node) return
    const remember = () => { offsets.set(key, node.scrollTop) }
    node.addEventListener('scroll', remember, { passive: true })
    return () => node.removeEventListener('scroll', remember)
  }, [key, ref])

  useLayoutEffect(() => {
    const node = ref.current
    const saved = offsets.get(key)
    if (!node || !ready || restored.current || saved == null) return

    // The list is rendered but not yet laid out to its full height — images
    // resolve their aspect ratio a frame or two later — and a container cannot
    // scroll past content it does not have, so a single assignment silently
    // clamps to whatever the height was at that instant. Keep re-applying until
    // it takes, or until the shopper starts scrolling themselves.
    let frame = 0
    let raf = 0

    const finish = () => {
      restored.current = true
      cancelAnimationFrame(raf)
      node.removeEventListener('wheel', finish)
      node.removeEventListener('touchstart', finish)
    }

    const apply = () => {
      node.scrollTop = saved
      if (Math.abs(node.scrollTop - saved) < 1 || frame++ > 40) {
        finish()
        return
      }
      raf = requestAnimationFrame(apply)
    }

    node.addEventListener('wheel', finish, { passive: true, once: true })
    node.addEventListener('touchstart', finish, { passive: true, once: true })
    apply()

    return finish
  }, [key, ready, ref])
}

/** Forget where a screen was, for a change that invalidates the offset — a new
 *  filter renders a different list, so the old position means nothing. */
export function forgetScroll(key: string): void {
  offsets.delete(key)
}
