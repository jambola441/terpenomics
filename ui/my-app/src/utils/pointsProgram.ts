/**
 * What the Terpee points program is, in words, from the numbers the API keeps
 * (routes/pos_common.program_json). The web and the app both say it this way,
 * so the copy can't drift between them or from the rules. No imports, so the
 * app shares it.
 */

export type ProgramNumbers = {
  points_per_dollar: number
  pending_days: number
  claim_window_days: number
  /** What points can be used for, when rewards are set up (POINTS_REWARDS on the API). */
  rewards?: string | null
}

export const PARTNER_DEFINITION =
  'Partner stores are local businesses, not dispensaries, where what you buy earns Terpee points.'

export function rate(p: ProgramNumbers): string {
  return `${p.points_per_dollar === 1 ? '1 point' : `${p.points_per_dollar} points`} per $1`
}

/** "1 point per $1 before tax and tip" — the line under a partner's name. */
export function earnLine(p: ProgramNumbers): string {
  return `Earn ${rate(p)} before tax and tip`
}

export function steps(p: ProgramNumbers): { title: string; body: string }[] {
  return [
    {
      title: 'Shop at a partner store',
      body: 'Cafés, shops and other local businesses that work with Terpee. They\'re listed under Partner stores.',
    },
    {
      title: 'Give your phone number at checkout',
      body: 'The number you sign in to Terpee with. That\'s how the purchase finds you: there\'s no card to carry.',
    },
    {
      title: `Points are yours after ${p.pending_days} days`,
      body: `You earn ${rate(p)} you spend, before tax and tip. They show as pending for ${p.pending_days} days in case of a return, then they're yours.`,
    },
  ]
}

export function questions(p: ProgramNumbers): { q: string; a: string }[] {
  return [
    {
      q: 'I forgot to give my number.',
      a: `Send us the receipt from Points within ${p.claim_window_days} days. Someone checks it, and the points are added.`,
    },
    {
      q: 'I bought something before I joined Terpee.',
      a: `If you gave your phone number at checkout, join with that number within ${p.claim_window_days} days and the purchase is matched to you on its own.`,
    },
    {
      q: 'What if I return something?',
      a: `The points it earned come off. A return within the ${p.pending_days} pending days cancels them before they're yours.`,
    },
    {
      q: 'Do orders from dispensaries earn points?',
      a: 'No. Points come from partner stores only.',
    },
    {
      q: 'Do points expire?',
      a: 'Not while you have a Terpee account. Deleting your account removes them.',
    },
    ...(p.rewards ? [{ q: 'What can I use points for?', a: p.rewards }] : []),
  ]
}
