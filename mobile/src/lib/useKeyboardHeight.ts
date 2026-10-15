import { useEffect, useState } from 'react'
import { Keyboard, LayoutAnimation, Platform } from 'react-native'

/**
 * How much of the screen the keyboard covers, in points (0 when hidden).
 *
 * For a screen that pads itself clear of the keyboard. KeyboardAvoidingView
 * misses a keyboard that opens while the screen is still mounting (an
 * autoFocus field), because it ignores the event until it has measured
 * itself, and then the form stays covered. This hook starts from
 * Keyboard.metrics(), so a keyboard already up counts, and it listens to
 * both the will- and did- events, so a late listener still hears it.
 */
export function useKeyboardHeight(): number {
  const [height, setHeight] = useState(() => Keyboard.metrics()?.height ?? 0)

  useEffect(() => {
    const ios = Platform.OS === 'ios'
    const update = (next: number) => {
      // Move with the keyboard rather than jump after it.
      if (ios) LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut)
      setHeight(prev => (prev === next ? prev : next))
    }
    const subs = [
      Keyboard.addListener(ios ? 'keyboardWillShow' : 'keyboardDidShow', e => update(e.endCoordinates.height)),
      Keyboard.addListener('keyboardDidShow', e => update(e.endCoordinates.height)),
      Keyboard.addListener(ios ? 'keyboardWillHide' : 'keyboardDidHide', () => update(0)),
    ]
    // The keyboard may have opened between the first render and these
    // listeners being added; pick that up too.
    const opened = Keyboard.metrics()?.height
    if (opened) update(opened)
    return () => subs.forEach(s => s.remove())
  }, [])

  return height
}
