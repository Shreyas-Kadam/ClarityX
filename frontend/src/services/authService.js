/**
 * Authentication Service for ClarityX
 *
 * Interacts with FastAPI /api/auth endpoints for verified profile metadata.
 */

import { apiFetch, getAuthToken } from './api'

/**
 * Retrieves the currently authenticated user's profile from the backend.
 * Calls GET /api/auth/me
 *
 * @returns {Promise<{id: string, email: string, full_name: string, created_at: string, updated_at: string}>}
 */
export async function getCurrentUserProfile() {
  return await apiFetch('/api/auth/me')
}

// Backward-compatible alias
export const getCurrentUser = getCurrentUserProfile

export { getAuthToken }
