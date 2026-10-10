/**
 * Opening hours of a partner store, as the API sends them (Square's business
 * hours: one entry per open stretch, a close earlier than the open runs past
 * midnight), in words. No imports, so the app shares it.
 */

export type HoursPeriod = { day: string; open: string; close: string }

const DAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'] as const
const LABEL: Record<string, string> = { MON: 'Mon', TUE: 'Tue', WED: 'Wed', THU: 'Thu', FRI: 'Fri', SAT: 'Sat', SUN: 'Sun' }
const WEEK = 7 * 1440

/** "09:00" → "9am", "17:30" → "5:30pm", "00:00" → "12am". */
export function formatTime(hhmm: string): string {
  const [h, m] = hhmm.split(':').map(Number)
  const suffix = h < 12 || h === 24 ? 'am' : 'pm'
  const hour = h % 12 === 0 ? 12 : h % 12
  return `${hour}${m ? `:${String(m).padStart(2, '0')}` : ''}${suffix}`
}

/** One row per day, Monday first: "9am–5pm", two stretches joined, or "Closed". */
export function weekHours(hours: HoursPeriod[] | null | undefined): { day: string; label: string; text: string }[] {
  return DAYS.map(day => {
    const ranges = (hours ?? []).filter(p => p.day === day).map(p => `${formatTime(p.open)}–${formatTime(p.close)}`)
    return { day, label: LABEL[day], text: ranges.length ? ranges.join(', ') : 'Closed' }
  })
}

/** "Mon–Fri 9am–6pm · Sat 10am–4pm · Sun Closed", "Daily 8am–8pm", or null with no hours. */
export function hoursSummary(hours: HoursPeriod[] | null | undefined): string | null {
  if (!hours?.length) return null
  const week = weekHours(hours)
  if (week.every(d => d.text === week[0].text)) return `Daily ${week[0].text}`
  const groups: { from: string; to: string; text: string }[] = []
  for (const d of week) {
    const last = groups[groups.length - 1]
    if (last && last.text === d.text) last.to = d.label
    else groups.push({ from: d.label, to: d.label, text: d.text })
  }
  return groups.map(g => `${g.from === g.to ? g.from : `${g.from}–${g.to}`} ${g.text}`).join(' · ')
}

/** Minutes since Monday 00:00 in the store's time zone (the viewer's when it has none). */
function minuteOfWeek(now: Date, timeZone?: string | null): number {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: timeZone || undefined, weekday: 'short', hour: 'numeric', minute: 'numeric', hourCycle: 'h23',
    }).formatToParts(now)
    const get = (type: string) => parts.find(p => p.type === type)?.value ?? ''
    const day = DAYS.indexOf(get('weekday').slice(0, 3).toUpperCase() as typeof DAYS[number])
    if (day >= 0) return day * 1440 + (Number(get('hour')) % 24) * 60 + Number(get('minute'))
  } catch {
    // An unknown zone, or no Intl time zones: fall through to the viewer's clock.
  }
  return ((now.getDay() + 6) % 7) * 1440 + now.getHours() * 60 + now.getMinutes()
}

function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

/** "Open · closes 6pm" or "Closed · opens 9am Tue"; null with no hours. */
export function openStatus(
  hours: HoursPeriod[] | null | undefined, timeZone?: string | null, now: Date = new Date(),
): { open: boolean; text: string } | null {
  if (!hours?.length) return null
  const t = minuteOfWeek(now, timeZone)
  const today = Math.floor(t / 1440)
  let nextStart: { at: number; p: HoursPeriod } | null = null
  for (const p of hours) {
    const day = DAYS.indexOf(p.day as typeof DAYS[number])
    if (day < 0) continue
    const start = day * 1440 + toMinutes(p.open)
    let end = day * 1440 + toMinutes(p.close)
    if (end <= start) end += 1440
    for (const shift of [0, WEEK]) {
      if (t + shift >= start && t + shift < end) return { open: true, text: `Open · closes ${formatTime(p.close)}` }
    }
    const wait = (start - t + WEEK) % WEEK
    if (!nextStart || wait < nextStart.at) nextStart = { at: wait, p }
  }
  if (!nextStart) return null
  const day = Math.floor(((t + nextStart.at) % WEEK) / 1440)
  const when = day === today ? (nextStart.at >= 1440 ? ` next ${LABEL[DAYS[day]]}` : '')
    : day === (today + 1) % 7 ? ' tomorrow' : ` ${LABEL[DAYS[day]]}`
  return { open: false, text: `Closed · opens ${formatTime(nextStart.p.open)}${when}` }
}
