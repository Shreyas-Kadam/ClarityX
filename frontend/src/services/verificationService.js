/**
 * Verification Checklist Service for ClarityX
 *
 * Implements status updates for actionable verification items.
 */

import { apiFetch } from './api'

/**
 * Updates the completion status of a verification checklist item.
 * Calls PATCH /api/verification/:itemId
 *
 * @param {string} itemId - Verification item UUID
 * @param {'pending'|'completed'} status - Target completion status
 * @returns {Promise<{success: boolean, message: string, data: Object}>}
 */
export async function updateVerificationStatus(itemId, status) {
  return await apiFetch(`/api/verification/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}

/**
 * Convenience wrapper to mark a verification item as completed.
 * Calls PATCH /api/verification/:itemId with status: 'completed'
 *
 * @param {string} itemId - Verification item UUID
 * @returns {Promise<{success: boolean, message: string, data: Object}>}
 */
export async function markVerificationCompleted(itemId) {
  return await updateVerificationStatus(itemId, 'completed')
}

/**
 * Convenience wrapper to revert a verification item to pending.
 * Calls PATCH /api/verification/:itemId with status: 'pending'
 *
 * @param {string} itemId - Verification item UUID
 * @returns {Promise<{success: boolean, message: string, data: Object}>}
 */
export async function markVerificationPending(itemId) {
  return await updateVerificationStatus(itemId, 'pending')
}

