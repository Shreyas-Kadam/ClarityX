/**
 * Research Session Service for ClarityX
 *
 * Implements CRUD API calls mapping to the backend /api/research endpoints.
 */

import { apiFetch } from './api'

/**
 * Retrieves paginated research sessions for the authenticated user.
 * Calls GET /api/research?limit=...&offset=...&status=...
 *
 * @param {Object} params
 * @param {number} [params.limit=10]
 * @param {number} [params.offset=0]
 * @param {string} [params.status=null]
 * @returns {Promise<{success: boolean, data: {research_sessions: Array, total: number, limit: number, offset: number}}>}
 */
export async function getResearchSessions({ limit = 10, offset = 0, status = null } = {}) {
  const query = new URLSearchParams()
  query.set('limit', String(limit))
  query.set('offset', String(offset))
  if (status) {
    query.set('status', status)
  }

  return await apiFetch(`/api/research?${query.toString()}`)
}

/**
 * Retrieves a single research session by ID.
 * Calls GET /api/research/:id
 *
 * @param {string} id - Research session UUID
 * @returns {Promise<{success: boolean, data: Object}>}
 */
export async function getResearchById(id) {
  return await apiFetch(`/api/research/${id}`)
}

/**
 * Creates a new research session for the authenticated user.
 * Calls POST /api/research
 *
 * @param {Object} payload
 * @param {string} payload.research_goal - The research question/objective
 * @returns {Promise<{success: boolean, message: string, data: Object}>}
 */
export async function createResearch({ research_goal }) {
  return await apiFetch('/api/research', {
    method: 'POST',
    body: JSON.stringify({ research_goal }),
  })
}

/**
 * Updates an existing research session.
 * Calls PATCH /api/research/:id
 *
 * @param {string} id - Research session UUID
 * @param {Object} updates - Fields to update (research_goal, status, summary)
 * @returns {Promise<{success: boolean, message: string, data: Object}>}
 */
export async function updateResearch(id, updates) {
  return await apiFetch(`/api/research/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  })
}

/**
 * Deletes a research session.
 * Calls DELETE /api/research/:id
 *
 * @param {string} id - Research session UUID
 * @returns {Promise<{success: boolean, message: string}>}
 */
export async function deleteResearch(id) {
  return await apiFetch(`/api/research/${id}`, {
    method: 'DELETE',
  })
}

