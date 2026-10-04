import { Platform } from 'react-native'
import * as SecureStore from 'expo-secure-store'

// Device-local for now: the backend has no date-of-birth field, so this is a
// self-attestation, which is what App Review checks for. Moving it onto the
// customer record would make it follow the account across devices.
const KEY = 'age_confirmed_21'

export async function isAgeConfirmed(): Promise<boolean> {
  if (Platform.OS === 'web') return true
  return (await SecureStore.getItemAsync(KEY)) === 'yes'
}

export async function confirmAge(): Promise<void> {
  if (Platform.OS !== 'web') await SecureStore.setItemAsync(KEY, 'yes')
}
