/**
 * In-memory source cache & request deduplication for ClarityX Source Viewer
 */

const sourceCache = new Map()
const inFlightRequests = new Map()

function makeKey(researchId, sourceId) {
  return `${researchId}:${sourceId}`
}

export function getCachedSource(researchId, sourceId) {
  if (!researchId || !sourceId) return null
  return sourceCache.get(makeKey(researchId, sourceId)) || null
}

export function setCachedSource(researchId, sourceId, data) {
  if (researchId && sourceId && data) {
    sourceCache.set(makeKey(researchId, sourceId), data)
  }
}

export function getInFlightRequest(researchId, sourceId) {
  if (!researchId || !sourceId) return null
  return inFlightRequests.get(makeKey(researchId, sourceId)) || null
}

export function setInFlightRequest(researchId, sourceId, promise) {
  if (researchId && sourceId && promise) {
    inFlightRequests.set(makeKey(researchId, sourceId), promise)
  }
}

export function deleteInFlightRequest(researchId, sourceId) {
  if (researchId && sourceId) {
    inFlightRequests.delete(makeKey(researchId, sourceId))
  }
}

export function invalidateSourceCache(researchId, sourceId) {
  if (researchId && sourceId) {
    sourceCache.delete(makeKey(researchId, sourceId))
  }
}

export function clearSourceCache() {
  sourceCache.clear()
  inFlightRequests.clear()
}

