/* ============================================================================
   css.ts — writes the tokens onto :root as CSS custom properties.

   Called once from main.jsx before the first render, so index.css, inline
   `var(--token)` styles and theme.ts all read the values in design/tokens.ts
   rather than a second copy of them.
   ========================================================================== */

import { color, radii, space, duration, typeface } from './tokens'

const kebab = (s: string) => s.replace(/([a-z])([A-Z0-9])/g, '$1-$2').toLowerCase()

const ease = 'cubic-bezier(0.4, 0, 0.2, 1)'

export function tokenDeclarations(): string {
  const vars: Record<string, string> = {}

  for (const [k, v] of Object.entries(color)) vars[kebab(k)] = v
  for (const [k, v] of Object.entries(radii)) vars[`r-${k}`] = `${v}px`
  for (const [k, v] of Object.entries(space)) vars[`s-${k}`] = `${v}px`

  vars['t-fast'] = `${duration.fast}ms ${ease}`
  vars['t-base'] = `${duration.base}ms ${ease}`
  vars['t-slow'] = `${duration.slow}ms ${ease}`
  vars['ease-spring'] = 'cubic-bezier(0.32, 0.72, 0, 1)'

  // Elevation: on a dark ground a shadow only reads as a soft falloff, so the
  // edge that separates a raised surface is its hairline, not this.
  vars['e-1'] = '0 1px 2px rgba(0, 0, 0, 0.4)'
  vars['e-2'] = '0 8px 24px rgba(0, 0, 0, 0.42)'
  vars['e-3'] = '0 16px 48px rgba(0, 0, 0, 0.56)'
  vars['ring'] = `0 0 0 2px ${color.bg}, 0 0 0 4px ${color.accent}`

  vars['font-display'] = `'${typeface.display} Variable', '${typeface.display}', Georgia, 'Times New Roman', serif`
  vars['font-sans'] = `'${typeface.sans} Variable', '${typeface.sans}', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif`
  vars['font-mono'] = `'${typeface.mono}', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`

  return `:root{${Object.entries(vars).map(([k, v]) => `--${k}:${v}`).join(';')}}`
}

export function installTokens(doc: Document = document): void {
  const id = 'design-tokens'
  let el = doc.getElementById(id) as HTMLStyleElement | null
  if (!el) {
    el = doc.createElement('style')
    el.id = id
    doc.head.prepend(el)
  }
  el.textContent = tokenDeclarations()
}
