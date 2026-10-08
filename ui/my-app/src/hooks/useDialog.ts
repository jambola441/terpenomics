import { useEffect, useRef, type RefObject } from 'react'

const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'input:not([disabled])', 'select:not([disabled])',
  'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])',
].join(',')

/**
 * What a modal sheet owes keyboard and screen-reader users: focus moves into
 * it when it opens, Tab stays inside it, Escape asks it to close, and focus
 * goes back to whatever opened it when it closes.
 *
 * `onEscape` is optional so a sheet can refuse to close (an order being
 * placed, say); `initialFocus` picks the first element to focus, defaulting to
 * the first focusable one.
 */
export function useDialog(
  ref: RefObject<HTMLElement | null>,
  open: boolean,
  { onEscape, initialFocus }: { onEscape?: () => void; initialFocus?: RefObject<HTMLElement | null> } = {},
) {
  const escape = useRef(onEscape)
  useEffect(() => { escape.current = onEscape })

  useEffect(() => {
    if (!open) return
    const opener = document.activeElement as HTMLElement | null
    const node = ref.current
    const first = initialFocus?.current ?? node?.querySelector<HTMLElement>(FOCUSABLE)
    // After the frame that mounts the sheet, so the element is focusable.
    const id = requestAnimationFrame(() => (first ?? node)?.focus())

    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        escape.current?.()
        return
      }
      if (e.key !== 'Tab' || !node) return
      const items = [...node.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(el => el.offsetParent !== null)
      if (items.length === 0) return
      const head = items[0], tail = items[items.length - 1]
      if (e.shiftKey && document.activeElement === head) { e.preventDefault(); tail.focus() }
      else if (!e.shiftKey && document.activeElement === tail) { e.preventDefault(); head.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      cancelAnimationFrame(id)
      document.removeEventListener('keydown', onKey)
      opener?.focus?.()
    }
  }, [open, ref, initialFocus])
}
