// A brand page laid out by product line (flag `lines_grouped`), the twin of the
// web's components/LineShelves.tsx. The rule for which categories get shelves
// and how they split is shared (@web/utils/browseLogic groupByLine); this file
// only draws it: the best few pinned on top, then per category either a shelf
// per line plus a "More …" shelf, or the plain grid capped at six.

import type { ReactNode } from 'react'
import { Pressable, ScrollView, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native'
import Svg, { Rect } from 'react-native-svg'
import { categoryStyle } from '@web/design/tokens'
import {
  SECTION_CAP, SHELF_CAP, countLabel, shelfMeta,
  type BrowseItem, type CategorySection,
} from '@web/utils/browseLogic'
import { CategoryIcon, Icon } from '@/components/Icon'
import { categoryName } from '@/components/ui'
import { GRID_GAP, GRID_GUTTER } from './controls'
import { t, font, fonts, space } from '@/lib/theme'

/** Shelf cards are a fixed width, as on the web. */
export const SHELF_CARD_WIDTH = 156

/** A product line's mark: a diamond, after the subway's express bullet, in its
 *  category's hue. Hollow and dashed marks what is in no line. */
export function LineMark({ color, size = 12, hollow = false }: { color: string; size?: number; hollow?: boolean }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 12 12" accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <Rect
        x="2.5" y="2.5" width="7" height="7" transform="rotate(45 6 6)"
        fill={hollow ? 'none' : color}
        stroke={hollow ? t.text3 : 'none'}
        strokeWidth={hollow ? 1.2 : 0}
        strokeDasharray={hollow ? '2 1.6' : undefined}
      />
    </Svg>
  )
}

/** The category's label the way the web's categoryLabel reads: "Other" for none. */
function labelOf(category: string | null): string {
  return category ? categoryName(category) : 'Other'
}

export default function LineShelves<E>({
  sections, itemOf, renderCard, gridCardWidth, best, onSeeLine, onSeeRest, onSeeCategory,
}: {
  sections: CategorySection<E>[]
  itemOf: (e: E) => BrowseItem
  /** Renders one card at `width`; `inLine` is true on a line's own shelf, where
   *  the header already says the line. */
  renderCard: (e: E, inLine: boolean, width: number) => ReactNode
  gridCardWidth: number
  best: { entries: E[]; label: string }
  onSeeLine: (category: string | null, line: string) => void
  onSeeRest: (category: string | null, thinLines: string[]) => void
  onSeeCategory: (category: string | null) => void
}) {
  const rail = (entries: E[], inLine: boolean) => (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      snapToInterval={SHELF_CARD_WIDTH + GRID_GAP}
      decelerationRate="fast"
      contentContainerStyle={{ gap: GRID_GAP, paddingHorizontal: GRID_GUTTER, paddingBottom: 2, alignItems: 'stretch' }}
    >
      {entries.map(e => (
        <View key={itemOf(e).key} style={{ flexDirection: 'row' }}>
          {renderCard(e, inLine, SHELF_CARD_WIDTH)}
        </View>
      ))}
    </ScrollView>
  )

  return (
    <View style={{ paddingBottom: space[8] }}>
      {best.entries.length > 0 ? (
        <View style={{ paddingTop: 12, paddingBottom: 4 }}>
          <Eyebrow style={{ paddingHorizontal: 16, paddingBottom: 8 }}>{best.label}</Eyebrow>
          {rail(best.entries, false)}
        </View>
      ) : null}

      {sections.map(section => {
        const label = labelOf(section.category)
        const color = categoryStyle(section.category).color
        return (
          <View key={section.category ?? '—'} style={{ paddingTop: 18 }}>
            <View style={s.rule}>
              <CategoryIcon category={section.category} size={16} />
              <Eyebrow>{label}</Eyebrow>
              <View style={s.hairline} />
              <Eyebrow>{section.entries.length}</Eyebrow>
            </View>

            {section.shelves.map(shelf => (
              <ShelfBlock
                key={shelf.line}
                eyebrow={`Line · ${label} · ${countLabel(shelf.entries.length)}`}
                title={shelf.line}
                mark={<LineMark color={color} size={16} />}
                meta={shelfMeta(shelf.entries.map(itemOf))}
                total={shelf.entries.length}
                onSeeAll={() => onSeeLine(section.category, shelf.line)}
              >
                {rail(shelf.entries.slice(0, SHELF_CAP), true)}
              </ShelfBlock>
            ))}

            {section.rest.length > 0 ? (section.shelves.length > 0 ? (
              <ShelfBlock
                eyebrow={`Not in a line · ${countLabel(section.rest.length)}`}
                title={`More ${label.toLowerCase()}`}
                mark={<LineMark color={color} size={16} hollow />}
                meta={shelfMeta(section.rest.map(itemOf))}
                total={section.rest.length}
                onSeeAll={() => onSeeRest(section.category, section.thinLines)}
              >
                {rail(section.rest.slice(0, SHELF_CAP), false)}
              </ShelfBlock>
            ) : (
              // A category that is not laid out by line looks as it did: a grid.
              <>
                <View style={s.grid}>
                  {section.rest.slice(0, SECTION_CAP).map(e => (
                    <View key={itemOf(e).key} style={{ flexDirection: 'row' }}>
                      {renderCard(e, false, gridCardWidth)}
                    </View>
                  ))}
                </View>
                {section.rest.length > SECTION_CAP ? (
                  <SeeAll
                    total={section.rest.length}
                    onPress={() => onSeeCategory(section.category)}
                    style={{ paddingHorizontal: 16, paddingTop: 10, alignSelf: 'flex-start' }}
                  />
                ) : null}
              </>
            )) : null}
          </View>
        )
      })}
    </View>
  )
}

function ShelfBlock({ eyebrow, title, mark, meta, total, onSeeAll, children }: {
  eyebrow: string
  title: string
  mark: ReactNode
  meta: string
  total: number
  onSeeAll: () => void
  children: ReactNode
}) {
  return (
    <View style={s.shelf}>
      <View style={s.shelfHead}>
        <Eyebrow>{eyebrow}</Eyebrow>
        <View style={s.shelfTitleRow}>
          {mark}
          <Text numberOfLines={1} style={s.shelfTitle} accessibilityRole="header">{title}</Text>
          {total > 1 ? <SeeAll total={total} onPress={onSeeAll} /> : null}
        </View>
        {meta ? <Text style={s.meta}>{meta}</Text> : null}
      </View>
      {children}
    </View>
  )
}

function SeeAll({ total, onPress, style }: { total: number; onPress: () => void; style?: StyleProp<ViewStyle> }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" hitSlop={6} style={[s.seeAll, style]}>
      <Text style={s.seeAllText}>See all {total}</Text>
      <Icon name="chevron-right" size={14} color={t.text2} />
    </Pressable>
  )
}

function Eyebrow({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return (
    <View style={style}>
      <Text style={s.eyebrow}>{children}</Text>
    </View>
  )
}

const s = StyleSheet.create({
  rule: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingBottom: 6 },
  hairline: { flex: 1, height: 1, backgroundColor: t.border },
  eyebrow: {
    fontFamily: fonts.mono, fontSize: font.size.micro + 0.5, color: t.text3,
    textTransform: 'uppercase', letterSpacing: 0.63, fontVariant: ['tabular-nums'],
  },
  shelf: { marginTop: 10, paddingTop: 12, borderTopWidth: 1, borderTopColor: t.borderStrong },
  shelfHead: { paddingHorizontal: 16, paddingBottom: 10, gap: 6 },
  shelfTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  shelfTitle: {
    flex: 1, minWidth: 0, fontFamily: fonts.display, fontSize: font.size.heading,
    letterSpacing: -0.2, color: t.text1,
  },
  meta: { fontFamily: fonts.mono, fontSize: font.size.caption, color: t.text2, fontVariant: ['tabular-nums'] },
  seeAll: { flexDirection: 'row', alignItems: 'center', gap: 2, paddingVertical: 6 },
  seeAllText: { fontFamily: fonts.sans, fontSize: font.size.small, color: t.text2 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: GRID_GAP, paddingHorizontal: GRID_GUTTER, paddingTop: 4 },
})
