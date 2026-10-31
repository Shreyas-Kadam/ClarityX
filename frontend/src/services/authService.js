/**
 * Authentication Service for ClarityX
 */

import { apiFetch, getAuthToken, setAuthToken } from './api'

/**
 * Retrieves the currently authenticated user's profile from the backend.
 * Calls GET /api/auth/me
 *
 * @returns {Promise<{id: string, email: string, full_name: string, created_at: string, updated_at: string}>}
 */
export async function getCurrentUser() {
  const token = getAuthToken()
  if (!token) {
    return null
  }
  return await apiFetch('/api/auth/me')
}

export { getAuthToken, setAuthToken }

