/**
 * Workflow and validation logic for the New Research Session page.
 *
 * Handles source preparation, validation, 5-source capacity enforcement,
 * and the two-phase session initialization workflow:
 * Phase 1: Research session creation via researchService.
 * Phase 2: Sequential source ingestion via sourceService.
 */

import { isValidUrl, formatFileSize } from './formatters.js'

export const MAX_SOURCES = 5
export const MAX_DOCUMENT_SIZE = 10 * 1024 * 1024 // 10 MB in bytes
export const MAX_PASTED_TEXT_LENGTH = 1048576 // 1 MB character limit

/**
 * Validates and prepares a website URL source item.
 *
 * @param {string} url - Target website URL
 * @param {Array} existingSources - Currently prepared sources
 * @returns {{ valid: boolean, error?: string, source?: Object }}
 */
export function validateWebsiteSource(url, existingSources = []) {
  if (existingSources.length >= MAX_SOURCES) {
    return { valid: false, error: `Maximum of ${MAX_SOURCES} sources allowed per research session.` }
  }

  const trimmed = typeof url === 'string' ? url.trim() : ''
  if (!trimmed) {
    return { valid: false, error: 'Please enter a target website URL.' }
  }

  if (!isValidUrl(trimmed)) {
    return { valid: false, error: 'Please enter a valid HTTP or HTTPS URL (e.g. https://example.com/article).' }
  }

  const isDuplicate = existingSources.some(
    (s) => s.type === 'website' && s.url.toLowerCase() === trimmed.toLowerCase()
  )
  if (isDuplicate) {
    return { valid: false, error: 'This website URL has already been added to the session.' }
  }

  let title
  try {
    const parsed = new URL(trimmed)
    title = parsed.hostname + (parsed.pathname !== '/' && parsed.pathname ? parsed.pathname : '')
  } catch {
    title = trimmed
  }

  const source = {
    id: `src-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    type: 'website',
    url: trimmed,
    title,
    status: 'pending',
    error: null,
  }

  return { valid: true, source }
}

/**
 * Validates and prepares a pasted text source item.
 *
 * @param {Object} params
 * @param {string} params.text - Pasted text content
 * @param {string} [params.title] - Optional title
 * @param {Array} existingSources - Currently prepared sources
 * @returns {{ valid: boolean, error?: string, source?: Object }}
 */
export function validatePastedTextSource({ text, title = '' }, existingSources = []) {
  if (existingSources.length >= MAX_SOURCES) {
    return { valid: false, error: `Maximum of ${MAX_SOURCES} sources allowed per research session.` }
  }

  const trimmedText = typeof text === 'string' ? text.trim() : ''
  if (!trimmedText) {
    return { valid: false, error: 'Pasted text content must not be empty or whitespace only.' }
  }

  if (trimmedText.length > MAX_PASTED_TEXT_LENGTH) {
    return { valid: false, error: 'Pasted text exceeds the maximum character limit (1,048,576 characters).' }
  }

  const trimmedTitle = typeof title === 'string' ? title.trim() : ''
  const displayTitle = trimmedTitle || `Pasted Excerpt (${trimmedText.slice(0, 40).replace(/\s+/g, ' ')}...)`

  const source = {
    id: `src-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    type: 'pasted_text',
    text: trimmedText,
    title: displayTitle,
    userTitle: trimmedTitle || null,
    charCount: trimmedText.length,
    status: 'pending',
    error: null,
  }

  return { valid: true, source }
}

/**
 * Validates and prepares an uploaded document (PDF/DOCX) source item.
 *
 * @param {Object} params
 * @param {File|Blob} params.file - Uploaded document file
 * @param {string} [params.title] - Optional title override
 * @param {Array} existingSources - Currently prepared sources
 * @returns {{ valid: boolean, error?: string, source?: Object }}
 */
export function validateDocumentSource({ file, title = '' }, existingSources = []) {
  if (existingSources.length >= MAX_SOURCES) {
    return { valid: false, error: `Maximum of ${MAX_SOURCES} sources allowed per research session.` }
  }

  if (!file) {
    return { valid: false, error: 'Please select a PDF or DOCX document to upload.' }
  }

  const filename = file.name || 'document'
  const lowerName = filename.toLowerCase()
  const isPdf = lowerName.endsWith('.pdf')
  const isDocx = lowerName.endsWith('.docx')

  if (!isPdf && !isDocx) {
    return { valid: false, error: 'Unsupported file type. Only PDF and DOCX files are supported.' }
  }

  if (file.size > MAX_DOCUMENT_SIZE) {
    return {
      valid: false,
      error: `Selected document (${formatFileSize(file.size)}) exceeds the maximum allowable limit of 10 MB.`,
    }
  }

  const isDuplicate = existingSources.some(
    (s) => s.type === 'document' && s.file && s.file.name === file.name && s.file.size === file.size
  )
  if (isDuplicate) {
    return { valid: false, error: 'This document has already been added to the session.' }
  }

  const trimmedTitle = typeof title === 'string' ? title.trim() : ''
  const displayTitle = trimmedTitle || filename

  const source = {
    id: `src-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    type: 'document',
    file,
    title: displayTitle,
    userTitle: trimmedTitle || null,
    fileSize: file.size,
    status: 'pending',
    error: null,
  }

  return { valid: true, source }
}

/**
 * Executes two-phase session initialization and sequential source upload.
 *
 * @param {Object} options
 * @param {string} options.researchGoal
 * @param {Array} options.preparedSources
 * @param {string|null} [options.activeSessionId=null]
 * @param {Function} options.createResearchFn
 * @param {Function} options.addWebsiteSourceFn
 * @param {Function} options.addPastedTextSourceFn
 * @param {Function} options.addDocumentSourceFn
 * @param {Function} [options.onSourceStatusChange]
 * @returns {Promise<{
 *   success: boolean,
 *   sessionId: string,
 *   updatedSources: Array,
 *   failedCount: number,
 *   error?: string
 * }>}
 */
export async function executeSessionInitialization({
  researchGoal,
  preparedSources,
  activeSessionId = null,
  createResearchFn,
  addWebsiteSourceFn,
  addPastedTextSourceFn,
  addDocumentSourceFn,
  onSourceStatusChange,
}) {
  const trimmedGoal = typeof researchGoal === 'string' ? researchGoal.trim() : ''
  if (!trimmedGoal) {
    throw new Error('Please enter a specific research goal or question.')
  }

  let sessionId = activeSessionId

  // Phase 1: Create session if not already existing from a prior partial run
  if (!sessionId) {
    const sessionResponse = await createResearchFn({ research_goal: trimmedGoal })
    const createdId = sessionResponse?.data?.id
    if (!createdId) {
      throw new Error('Failed to obtain research session ID from backend.')
    }
    sessionId = createdId
  }

  // Phase 2: Sequential upload of prepared sources
  const updatedSources = [...preparedSources]
  let failedCount = 0

  for (let i = 0; i < updatedSources.length; i++) {
    const src = { ...updatedSources[i] }

    // If source already succeeded in a prior attempt, skip it
    if (src.status === 'success') {
      continue
    }

    src.status = 'uploading'
    src.error = null
    updatedSources[i] = src
    if (onSourceStatusChange) {
      onSourceStatusChange([...updatedSources])
    }

    try {
      if (src.type === 'website') {
        await addWebsiteSourceFn(sessionId, { url: src.url })
      } else if (src.type === 'pasted_text') {
        await addPastedTextSourceFn(sessionId, { text: src.text, title: src.userTitle })
      } else if (src.type === 'document') {
        await addDocumentSourceFn(sessionId, { file: src.file, title: src.userTitle })
      }
      src.status = 'success'
      src.error = null
    } catch (err) {
      src.status = 'failed'
      src.error = err?.message || 'Failed to extract or ingest source content.'
      failedCount++
    }

    updatedSources[i] = src
    if (onSourceStatusChange) {
      onSourceStatusChange([...updatedSources])
    }
  }

  const overallSuccess = failedCount === 0

  return {
    success: overallSuccess,
    sessionId,
    updatedSources,
    failedCount,
  }
}
