/**
 * Formatting and validation utilities for ClarityX frontend.
 */

/**
 * Safely formats an ISO timestamp or date string.
 * Returns null if the timestamp is missing, empty, or invalid, preventing "Invalid Date" output.
 *
 * @param {string|null|undefined} timestamp
 * @returns {string|null}
 */
export function formatTimestamp(timestamp) {
  if (!timestamp) return null
  const date = new Date(timestamp)
  if (isNaN(date.getTime())) return null
  return date.toLocaleString()
}

/**
 * Validates a website URL string.
 *
 * @param {string} urlString
 * @returns {boolean}
 */
export function isValidUrl(urlString) {
  if (!urlString || typeof urlString !== 'string') return false
  const trimmed = urlString.trim()
  if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
    return false
  }
  try {
    const parsed = new URL(trimmed)
    return Boolean(parsed.hostname)
  } catch {
    return false
  }
}

/**
 * Formats file size in bytes to a human-readable string.
 *
 * @param {number} bytes
 * @returns {string}
 */
export function formatFileSize(bytes) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

