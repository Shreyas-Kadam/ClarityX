/**
 * Source Management Service for ClarityX
 *
 * Implements source ingestion (website, pasted text, PDF/DOCX document),
 * listing with content previews, full content retrieval, and source deletion.
 */

import { apiFetch } from './api'

/**
 * Retrieves paginated source previews for a research session.
 * Calls GET /api/research/:researchId/sources?limit=...&offset=...
 *
 * @param {string} researchId - Research session UUID
 * @param {Object} [params]
 * @param {number} [params.limit=50]
 * @param {number} [params.offset=0]
 * @returns {Promise<{success: boolean, message: string, data: {sources: Array, total: number, limit: number, offset: number}}>}
 */
export async function getSources(researchId, { limit = 50, offset = 0 } = {}) {
  const query = new URLSearchParams()
  query.set('limit', String(limit))
  query.set('offset', String(offset))

  return await apiFetch(`/api/research/${researchId}/sources?${query.toString()}`)
}

/**
 * Retrieves a single source by ID including its full extracted content.
 * Calls GET /api/research/:researchId/sources/:sourceId
 *
 * @param {string} researchId - Research session UUID
 * @param {string} sourceId - Source UUID
 * @returns {Promise<{success: boolean, message: string, data: Object}>}
 */
export async function getSourceById(researchId, sourceId) {
  return await apiFetch(`/api/research/${researchId}/sources/${sourceId}`)
}

/**
 * Extracts and persists a website source from a target URL.
 * Calls POST /api/research/:researchId/sources/website
 *
 * @param {string} researchId - Research session UUID
 * @param {Object} payload
 * @param {string} payload.url - Valid HTTP/HTTPS website URL
 * @returns {Promise<{success: boolean, message: string, data: Object}>}
 */
export async function addWebsiteSource(researchId, { url }) {
  return await apiFetch(`/api/research/${researchId}/sources/website`, {
    method: 'POST',
    body: JSON.stringify({ url }),
  })
}

/**
 * Normalizes, sanitizes, and persists user-submitted pasted text.
 * Calls POST /api/research/:researchId/sources/pasted-text
 *
 * @param {string} researchId - Research session UUID
 * @param {Object} payload
 * @param {string} payload.text - Raw text content
 * @param {string|null} [payload.title=null] - Optional title override
 * @returns {Promise<{success: boolean, message: string, data: Object}>}
 */
export async function addPastedTextSource(researchId, { text, title = null }) {
  return await apiFetch(`/api/research/${researchId}/sources/pasted-text`, {
    method: 'POST',
    body: JSON.stringify({ text, title }),
  })
}

/**
 * Uploads, extracts, and persists a PDF or DOCX document source.
 * Uses FormData without manually setting Content-Type.
 * Calls POST /api/research/:researchId/sources/document
 *
 * @param {string} researchId - Research session UUID
 * @param {Object} payload
 * @param {File|Blob} payload.file - Uploaded document file object
 * @param {string|null} [payload.title=null] - Optional title override
 * @returns {Promise<{success: boolean, message: string, data: Object}>}
 */
export async function addDocumentSource(researchId, payload, optionalTitle = null) {
  const formData = new FormData()

  let file
  let title

  if (payload && typeof payload === 'object' && 'file' in payload) {
    file = payload.file
    title = payload.title ?? optionalTitle
  } else if (payload instanceof Blob || (typeof File !== 'undefined' && payload instanceof File)) {
    file = payload
    title = optionalTitle
  }

  if (file) {
    formData.append('file', file)
  }

  if (title && typeof title === 'string' && title.trim()) {
    formData.append('title', title.trim())
  }

  return await apiFetch(`/api/research/${researchId}/sources/document`, {
    method: 'POST',
    body: formData,
  })
}

/**
 * Permanently deletes a source from a research session.
 * Calls DELETE /api/research/:researchId/sources/:sourceId
 *
 * @param {string} researchId - Research session UUID
 * @param {string} sourceId - Source UUID
 * @returns {Promise<{success: boolean, message: string}>}
 */
export async function deleteSource(researchId, sourceId) {
  return await apiFetch(`/api/research/${researchId}/sources/${sourceId}`, {
    method: 'DELETE',
  })
}

