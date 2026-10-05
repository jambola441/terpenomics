// Take or pick a receipt photo and shrink it before upload, as the web portal
// does in ui/my-app/src/utils/receiptImage.ts: the longest side down to 1600px,
// re-encoded as JPEG. A phone camera photo is several MB and the reviewer only
// needs to read the store, date and subtotal.
import * as ImagePicker from 'expo-image-picker'
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator'

const MAX_SIDE = 1600

export type ReceiptPhoto = { uri: string; type: string; name: string; width: number; height: number }

/** Returns null when the shopper cancels. Throws when permission is denied. */
export async function pickReceipt(source: 'camera' | 'library'): Promise<ReceiptPhoto | null> {
  const options: ImagePicker.ImagePickerOptions = {
    mediaTypes: 'images',
    quality: 1,
    // A JPEG rather than HEIC from the photo library, for older browsers in the review queue.
    preferredAssetRepresentationMode: ImagePicker.UIImagePickerPreferredAssetRepresentationMode.Compatible,
  }
  if (source === 'camera') {
    const perm = await ImagePicker.requestCameraPermissionsAsync()
    if (!perm.granted) throw new Error('Allow camera access in Settings to photograph a receipt.')
  }
  const result = source === 'camera'
    ? await ImagePicker.launchCameraAsync(options)
    : await ImagePicker.launchImageLibraryAsync(options)
  if (result.canceled || !result.assets?.length) return null
  return shrink(result.assets[0])
}

async function shrink(asset: ImagePicker.ImagePickerAsset): Promise<ReceiptPhoto> {
  const context = ImageManipulator.manipulate(asset.uri)
  const longest = Math.max(asset.width, asset.height)
  if (longest > MAX_SIDE) {
    // Both sides given: a null side breaks the web build's canvas resize.
    const scale = MAX_SIDE / longest
    context.resize({ width: Math.round(asset.width * scale), height: Math.round(asset.height * scale) })
  }
  const rendered = await context.renderAsync()
  const saved = await rendered.saveAsync({ format: SaveFormat.JPEG, compress: 0.82 })
  return { uri: saved.uri, type: 'image/jpeg', name: 'receipt.jpg', width: saved.width, height: saved.height }
}
