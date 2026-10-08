// The app's view of the design language (DESIGN.md). Every value comes from the
// web portal's token file, imported as `@web/design/tokens`, so there is one
// copy: change a colour there and both platforms follow. This file only adds
// what React Native needs on top — the loaded font family names and text-style
// presets — since RN has no CSS variables or font-weight-aware families.

import { StyleSheet, type TextStyle } from 'react-native'
import { color, fontSize, radii, space as spaceScale } from '@web/design/tokens'

/** Colour roles (bg, surface1, text1, accent, success…). Never write a hex. */
export const t = color

export const radius = radii

export const space = spaceScale

export const font = { size: fontSize } as const

/** Family names as registered by `useFonts` in app/_layout.tsx. Each is one
 *  face: on React Native a custom family must not be combined with
 *  `fontWeight` (Android then picks the wrong face), so the weight lives in
 *  the family name and the presets below set `fontFamily` only. */
export const fonts = {
  display: 'Fraunces_600SemiBold',
  sans: 'PublicSans_400Regular',
  sansMedium: 'PublicSans_500Medium',
  sansSemibold: 'PublicSans_600SemiBold',
  sansBold: 'PublicSans_700Bold',
  mono: 'IBMPlexMono_400Regular',
  monoMedium: 'IBMPlexMono_500Medium',
} as const

/** Letter-spacing in em (as tokens.ts writes it) → points for a given size. */
const em = (size: number, value: number) => Math.round(size * value * 100) / 100

const tabular: TextStyle['fontVariant'] = ['tabular-nums']

/** The mono eyebrow, like the field on a specimen label. */
const label: TextStyle = {
  fontFamily: fonts.monoMedium,
  fontSize: fontSize.caption,
  lineHeight: 14,
  letterSpacing: em(fontSize.caption, 0.08),
  textTransform: 'uppercase',
  color: t.text3,
}

/** Text-style presets. Spread or compose them; override colour as needed. */
export const type = StyleSheet.create({
  /** Page titles: Fraunces 30. */
  display: {
    fontFamily: fonts.display,
    fontSize: fontSize.hero,
    lineHeight: 36,
    letterSpacing: em(fontSize.hero, -0.015),
    color: t.text1,
  },
  /** Section headers, store names, sheet titles: Fraunces 20. */
  title: {
    fontFamily: fonts.display,
    fontSize: fontSize.heading,
    lineHeight: 26,
    letterSpacing: em(fontSize.heading, -0.015),
    color: t.text1,
  },
  /** A UI heading in the text face: Public Sans semibold 17. */
  heading: { fontFamily: fonts.sansSemibold, fontSize: fontSize.title, lineHeight: 22, color: t.text1 },
  body: { fontFamily: fonts.sans, fontSize: fontSize.body, lineHeight: 20, color: t.text1 },
  /** Names and values in a list: Public Sans semibold 14. */
  bodyStrong: { fontFamily: fonts.sansSemibold, fontSize: fontSize.body, lineHeight: 20, color: t.text1 },
  /** Paragraph copy on a screen of its own (age gate, sign-in): 15 in text2. */
  copy: { fontFamily: fonts.sans, fontSize: fontSize.callout, lineHeight: 22, color: t.text2 },
  /** Captions and secondary facts. */
  meta: { fontFamily: fonts.sans, fontSize: fontSize.small, lineHeight: 16, color: t.text3 },
  label,
  /** Same as `label`: the design doc calls the mono label an eyebrow. */
  eyebrow: label,
  /** Data: sizes, potency, lab percentages. */
  mono: { fontFamily: fonts.mono, fontSize: fontSize.small, lineHeight: 16, color: t.text2, fontVariant: tabular },
  /** Pickup codes: read out at a counter, so big, mono and spaced. */
  code: {
    fontFamily: fonts.monoMedium,
    fontSize: fontSize.hero,
    lineHeight: 36,
    letterSpacing: em(fontSize.hero, 0.08),
    color: t.text1,
    fontVariant: tabular,
  },
  /** Prices are paper white, never accent, and line up. */
  price: { fontFamily: fonts.sansBold, fontSize: fontSize.body, lineHeight: 20, color: t.text1, fontVariant: tabular },
  /** Any other figure that must line up (points, counts). */
  number: { fontFamily: fonts.sansSemibold, fontSize: fontSize.body, color: t.text1, fontVariant: tabular },
  button: { fontFamily: fonts.sansSemibold, fontSize: fontSize.callout, lineHeight: 20 },
  /** A text action inside a card ("Change", "See all"). */
  link: { fontFamily: fonts.sansSemibold, fontSize: fontSize.body, color: t.text2 },
  input: { fontFamily: fonts.sans, fontSize: fontSize.title, color: t.text1 },
})
