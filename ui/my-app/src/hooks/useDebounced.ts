import { useEffect, useState } from 'react'

/**
 * The value, but only once it has stopped changing for `delay` ms.
 *
 * For filtering that runs over the whole in-memory result set: a keystroke on a
 * large category would otherwise re-filter, re-count every facet and re-render
 * the grid on every character.
 */
export function useDebounced<T>(value: T, delay = 180): T {
  const [settled, setSettled] = useState(value)

  useEffect(() => {
    const id = setTimeout(() => setSettled(value), delay)
    return () => clearTimeout(id)
  }, [value, delay])

  return settled
}
