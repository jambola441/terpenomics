import { useState } from 'react'
import { photoSrcSet } from '../utils/photoUrl'

/** img attributes for a product photo drawn about `cssPx` wide: the resized file
 *  where the host can make one (utils/photoUrl), then the original if that fails,
 *  then null, when the caller draws its placeholder. */
export function usePhoto(src: string | null | undefined, cssPx: number) {
  // Failures are remembered with the photo they belong to, so a card reused for
  // another listing starts again from the resized file.
  const [failed, setFailed] = useState<{ src: string; tries: number } | null>(null)
  if (!src) return null
  const tries = failed?.src === src ? failed.tries : 0
  const steps = [photoSrcSet(src, cssPx), { src, srcSet: undefined }].filter(Boolean) as
    { src: string; srcSet: string | undefined }[]
  const step = steps[tries]
  if (!step) return null
  return { ...step, onError: () => setFailed({ src, tries: tries + 1 }) }
}
