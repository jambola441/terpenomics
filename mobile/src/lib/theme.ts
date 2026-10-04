// The web portal's design tokens (ui/my-app/src/index.css) as plain values,
// since React Native has no CSS variables. Keep the two in step.

export const t = {
  bg: '#0b0b0d',
  surface1: '#141418',
  surface2: '#1c1c21',
  surface3: '#26262d',
  tile: '#f3f2ee',

  border: '#26262d',
  borderStrong: '#34343d',

  text1: '#f4f5f7',
  text2: '#aab0b9',
  text3: '#7d828c',
  text4: '#585d66',

  accent: '#a8e063',
  accentStrong: '#baee78',
  accentDim: '#7faa46',
  accentInk: '#0c1605',
  accentTint: 'rgba(168, 224, 99, 0.12)',

  danger: '#f0655a',
  success: '#a8e063',
  warning: '#ffb454',
} as const

export const radius = { xs: 6, sm: 8, md: 10, lg: 14, xl: 18, '2xl': 22, pill: 999 } as const

export const space = { 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 7: 32, 8: 40 } as const

export const font = {
  size: { micro: 10, caption: 11, small: 12, body: 14, callout: 15, title: 17, heading: 20, display: 24, hero: 28 },
  weight: { regular: '400', medium: '500', semibold: '600', bold: '700', heavy: '800' },
} as const
