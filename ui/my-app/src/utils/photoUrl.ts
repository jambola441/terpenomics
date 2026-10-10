/* ============================================================================
   Product photos at the size they're drawn.

   Store photos are whatever a point-of-sale system holds: a 1636px, 1 MB PNG for
   a card drawn 160px wide. Most of them sit behind an image service that resizes
   on request, so asking for the drawn size costs nothing but a URL:

     Dutchie's bucket   images.dutchie.com, the imgix front its own menus use
                        (16,156 listings; median 79 KB -> 12 KB, 2026-10-10)
     Tymber             *.imgix.net (3,621; 141 KB -> 16 KB)
     Weedmaps           images.weedmaps.com, also imgix
     Shopify            cdn.shopify.com, where brand catalog photos live
     Our own copies     Supabase Storage, for store photos on hosts that can't
                        resize (scripts/photo_mirror.py): a 320px and a 640px file

   `auto=format` sends AVIF or WebP to a browser that takes them and the
   original format to one that doesn't; `fit=max` never enlarges. Sizes snap to
   a few steps so a card and the page that follows it share a cached file.

   A resized URL can fail where the original works (a service that changes its
   rules), so every caller falls back to the original before giving up.
   ========================================================================== */

const STEPS = [160, 320, 480, 640, 960, 1280]

/** The smallest step at least `px` wide, capped at the largest. */
function step(px: number): number {
  return STEPS.find(s => s >= px) ?? STEPS[STEPS.length - 1]
}

/** `base` with its query's `params` replaced. Plain string work rather than URL,
 *  which React Native only half implements; the app shares this file. */
function withParams(base: string, query: string, params: Record<string, string>): string {
  const replaced = new Set(Object.keys(params))
  const kept = query.replace(/^\?/, '').split('&')
    .filter(kv => kv && !replaced.has(kv.split('=')[0]))
  const added = Object.entries(params).map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
  return `${base}?${[...kept, ...added].join('&')}`
}

/** `src` resized to about `px` wide, or null when its host can't resize. */
export function photoAt(src: string | null | undefined, px: number): string | null {
  const m = src ? /^https:\/\/([^/?#]+)([^?#]*)(\?[^#]*)?$/i.exec(src) : null
  if (!m) return null
  const [, rawHost, path, query = ''] = m
  const host = rawHost.toLowerCase()
  const w = String(step(px))
  const imgix = { w, fit: 'max', auto: 'format' }

  // Dutchie's bucket, addressed either way S3 allows.
  if (host === 's3-us-west-2.amazonaws.com' && path.startsWith('/dutchie-images/')) {
    return withParams(`https://images.dutchie.com/${path.slice('/dutchie-images/'.length)}`, '', imgix)
  }
  if (host === 'dutchie-images.s3.us-west-2.amazonaws.com') {
    return withParams(`https://images.dutchie.com${path}`, '', imgix)
  }
  if (host.endsWith('.imgix.net') || host === 'images.weedmaps.com') {
    // A signed imgix URL (s=) breaks when its parameters change.
    if (/(^\?|&)s=/.test(query)) return null
    return withParams(`https://${rawHost}${path}`, query, imgix)
  }
  if (host === 'cdn.shopify.com' || path.includes('/cdn/shop/')) {
    return withParams(`https://${rawHost}${path}`, query, { width: w })
  }
  // Our copies come in two widths only.
  const copy = /^(\/storage\/v1\/object\/public\/photos\/store\/[^/]+\/)(320|640)\.webp$/.exec(path)
  if (host.endsWith('.supabase.co') && copy) {
    return `https://${rawHost}${copy[1]}${step(px) <= 320 ? 320 : 640}.webp`
  }
  return null
}

/** img attributes for a photo drawn `cssPx` wide: one file per screen density,
 *  or null when the host can't resize (draw `src` as it is). */
export function photoSrcSet(src: string | null | undefined, cssPx: number): { src: string; srcSet: string } | null {
  const one = photoAt(src, cssPx)
  if (!one) return null
  return { src: one, srcSet: `${one} 1x, ${photoAt(src, cssPx * 2)} 2x, ${photoAt(src, cssPx * 3)} 3x` }
}
