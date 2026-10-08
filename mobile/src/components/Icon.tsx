// Renders a glyph from the shared icon set (ui/my-app/src/design/icons.ts) with
// react-native-svg — the twin of the web's components/Icon.tsx. The set is one
// 24-unit line drawing per name, round caps and joins, no fill; the colour is
// passed in as `color` and reaches the strokes through `currentColor`.

import { createElement, type ComponentType } from 'react'
import { Text, View, type ColorValue, type StyleProp, type ViewStyle } from 'react-native'
import Svg, { Circle, Ellipse, Line, Path, Polygon, Polyline, Rect } from 'react-native-svg'
import { icons, type IconName } from '@web/design/icons'
import { categoryStyle } from '@web/design/tokens'
import { fonts, t } from '@/lib/theme'

export type { IconName }

type ShapeProps = Record<string, unknown>

// Every tag the icon data uses, mapped to its react-native-svg element. The
// attributes (d, cx, points, rx…) are the same names in both, so they pass
// straight through.
const SHAPES: Record<string, ComponentType<ShapeProps>> = {
  path: Path as ComponentType<ShapeProps>,
  circle: Circle as ComponentType<ShapeProps>,
  rect: Rect as ComponentType<ShapeProps>,
  line: Line as ComponentType<ShapeProps>,
  polyline: Polyline as ComponentType<ShapeProps>,
  polygon: Polygon as ComponentType<ShapeProps>,
  ellipse: Ellipse as ComponentType<ShapeProps>,
}

export function Icon({
  name,
  size = 20,
  color = t.text1,
  strokeWidth = 1.75,
  label,
  style,
}: {
  name: IconName
  size?: number
  color?: ColorValue
  strokeWidth?: number
  /** Accessible name; omit when adjacent text already says what it means. */
  label?: string
  style?: StyleProp<ViewStyle>
}) {
  return (
    <Svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      color={color}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={style}
      accessible={!!label}
      accessibilityRole={label ? 'image' : undefined}
      accessibilityLabel={label}
      importantForAccessibility={label ? 'yes' : 'no-hide-descendants'}
    >
      {icons[name].map(([tag, attrs], i) => {
        const Shape = SHAPES[tag]
        return Shape ? createElement(Shape, { key: i, ...attrs }) : null
      })}
    </Svg>
  )
}

/** The glyph for a product category (bud, cone, cartridge…), in the
 *  category's own colour unless given another. */
export function CategoryIcon({
  category,
  size = 20,
  color,
  strokeWidth,
  style,
}: {
  category: string | null | undefined
  size?: number
  color?: ColorValue
  strokeWidth?: number
  style?: StyleProp<ViewStyle>
}) {
  const c = categoryStyle(category)
  const name: IconName = c.icon in icons ? (c.icon as IconName) : 'package'
  return <Icon name={name} size={size} color={color ?? c.color} strokeWidth={strokeWidth} style={style} />
}

/** The Terpee mark — terpene ring and resin bead — with the wordmark
 *  beside it unless `wordmark={false}`. */
export function Logo({
  size = 28,
  wordmark = true,
  style,
}: {
  size?: number
  wordmark?: boolean
  style?: StyleProp<ViewStyle>
}) {
  const textSize = Math.round(size * 0.82)
  return (
    <View
      accessible
      accessibilityRole="image"
      accessibilityLabel="Terpee"
      style={[{ flexDirection: 'row', alignItems: 'center', gap: Math.round(size * 0.32) }, style]}
    >
      <Icon name="mark" size={size} color={t.accent} strokeWidth={1.9} />
      {wordmark ? (
        <Text
          style={{
            fontFamily: fonts.display,
            fontSize: textSize,
            lineHeight: Math.round(textSize * 1.2),
            letterSpacing: Math.round(textSize * -0.02 * 100) / 100,
            color: t.text1,
          }}
        >
          terpee
        </Text>
      ) : null}
    </View>
  )
}
