// The scroll every browse screen shares: hero (tinted, under the status bar),
// the toolbar that sticks under it, a status block, then either the two-column
// grid (virtualised a row at a time, the app's version of the web's windowed
// BrowseGrid) or a body of its own (shelves, a loading grid, an empty state).

import type { ReactNode, RefObject } from 'react'
import { FlatList, RefreshControl, StyleSheet, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { styles } from '@/components/ui'
import { GRID_GAP, GRID_GUTTER, HeroBackdrop, StatusStrip, useGridCardWidth } from './controls'
import { useKeyboardHeight } from '@/lib/useKeyboardHeight'
import { t, space } from '@/lib/theme'

type Row<T> =
  | { kind: 'hero' }
  | { kind: 'toolbar' }
  | { kind: 'status' }
  | { kind: 'pair'; items: T[]; key: string }
  | { kind: 'body' }

export type BrowseListProps<T> = {
  /** The page's hue: the hero's wash and the status bar strip. */
  color: string
  /** Opacity of the wash at the top (the web's first gradient stop). */
  wash?: number
  /** Sits behind the hero, e.g. the oversized glyph bled off the edge. */
  decoration?: ReactNode
  hero: ReactNode
  toolbar: ReactNode
  status?: ReactNode
  /** The grid's cards; ignored when `body` is given. */
  items?: T[]
  keyOf?: (item: T) => string
  renderCard?: (item: T, width: number) => ReactNode
  body?: ReactNode
  refreshing?: boolean
  onRefresh?: () => void
  /** For scrolling back to the top. */
  listRef?: RefObject<ScrollToTop | null>
}

/** The one thing the screens do with the list. */
export type ScrollToTop = { scrollToOffset: (o: { offset: number; animated?: boolean }) => void }

export default function BrowseList<T>({
  color, wash = 0.22, decoration, hero, toolbar, status, items, keyOf, renderCard, body,
  refreshing, onRefresh, listRef,
}: BrowseListProps<T>) {
  const insets = useSafeAreaInsets()
  const cardWidth = useGridCardWidth()
  // Search fields keep the keyboard up; pad by it so results scroll clear.
  const keyboard = useKeyboardHeight()

  const rows: Row<T>[] = [{ kind: 'hero' }, { kind: 'toolbar' }, { kind: 'status' }]
  if (body != null) rows.push({ kind: 'body' })
  else if (items && keyOf) {
    for (let i = 0; i < items.length; i += 2) {
      const pair = items.slice(i, i + 2)
      rows.push({ kind: 'pair', items: pair, key: pair.map(keyOf).join('·') })
    }
  }

  return (
    <View style={styles.screen}>
      <StatusStrip height={insets.top} color={color} strength={wash} />
      <FlatList
        ref={listRef as RefObject<FlatList<Row<T>> | null> | undefined}
        style={{ flex: 1 }}
        data={rows}
        stickyHeaderIndices={[1]}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        initialNumToRender={8}
        windowSize={7}
        contentContainerStyle={{ paddingBottom: space[8] + keyboard }}
        keyExtractor={row => (row.kind === 'pair' ? row.key : row.kind)}
        refreshControl={onRefresh
          ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={t.text3} />
          : undefined}
        renderItem={({ item: row }) => {
          switch (row.kind) {
            case 'hero':
              return (
                <View style={s.hero}>
                  <HeroBackdrop color={color} strength={wash} />
                  {decoration}
                  {hero}
                </View>
              )
            case 'toolbar':
              return <>{toolbar}</>
            case 'status':
              return <>{status ?? null}</>
            case 'body':
              return <>{body}</>
            case 'pair':
              return (
                <View style={s.row}>
                  {row.items.map(item => (
                    <View key={keyOf!(item)} style={{ flexDirection: 'row' }}>
                      {renderCard?.(item, cardWidth)}
                    </View>
                  ))}
                </View>
              )
          }
        }}
      />
    </View>
  )
}

const s = StyleSheet.create({
  hero: { position: 'relative', overflow: 'hidden', paddingTop: 8, paddingHorizontal: 16, paddingBottom: 18 },
  row: { flexDirection: 'row', gap: GRID_GAP, paddingHorizontal: GRID_GUTTER, paddingTop: GRID_GAP, alignItems: 'stretch' },
})
