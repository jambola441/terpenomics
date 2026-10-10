/* Product lines: the few rules every screen that shows them shares. */

/** The line option for products in no line. Without it, picking a line would
 *  quietly hide every product the brand never named a line for, and the counts
 *  would only add up to part of the page. */
export const NO_LINE = 'No line'

/** A line counts as one, for its filter and its links, from this many products
 *  up. Below that a "line" is often one product under a flavour or effect name,
 *  and a filter of one-item options reads as noise. */
export const LINE_MIN_PRODUCTS = 3

/** A product's name once its line is already said around it. compose()
 *  (services/display_name.py) writes "Palms Blue Dream"; under a Palms heading
 *  or filter that is just "Blue Dream". A name that is only the line stays. */
export function nameWithinLine(name: string, line: string | null): string {
  if (!line) return name
  const prefix = `${line} `
  return name.toLowerCase().startsWith(prefix.toLowerCase()) && name.length > prefix.length
    ? name.slice(prefix.length)
    : name
}
