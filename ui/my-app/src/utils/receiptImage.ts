/**
 * Shrink a receipt photo before upload.
 *
 * Phone photos are 3–12 MB; a receipt stays perfectly legible at 1600px on the
 * long edge as a JPEG, which is a few hundred KB. Receipts are stored in the
 * database (like lab-report PDFs), so this keeps rows small and uploads fast
 * on a phone connection.
 *
 * If the browser can't decode the file (some HEIC photos outside Safari), the
 * original goes up unchanged and the server's own size and type checks apply.
 */
const MAX_EDGE = 1600
const QUALITY = 0.82

export async function shrinkReceipt(file: File): Promise<Blob> {
  try {
    const bitmap = await createImageBitmap(file)
    const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height))
    const w = Math.round(bitmap.width * scale)
    const h = Math.round(bitmap.height * scale)
    const canvas = document.createElement('canvas')
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')
    if (!ctx) return file
    ctx.drawImage(bitmap, 0, 0, w, h)
    bitmap.close?.()
    const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', QUALITY))
    return blob && blob.size < file.size ? blob : file
  } catch {
    return file
  }
}
