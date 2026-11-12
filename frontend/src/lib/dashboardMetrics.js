/**
 * Dashboard Metrics & Session Count Computation Helpers for ClarityX
 */

/**
 * Computes dashboard metric counters, prioritizing comprehensive database stats
 * across the entire user dataset over paginated recent session slices.
 *
 * @param {Object|null} statsData - Stats payload from GET /api/research/stats
 * @param {Array} [recentSessions=[]] - Paginated slice of recent sessions (e.g. limit 5)
 * @param {number|null} [totalFromList=null] - Total count metadata from paginated list endpoint
 * @returns {{total: number, completed: number, processing: number, pending: number}}
 */
export function calculateDashboardCounts(statsData, recentSessions = [], totalFromList = null) {
  if (statsData && typeof statsData === 'object') {
    return {
      total: Number(statsData.total ?? 0),
      completed: Number(statsData.completed ?? 0),
      processing: Number(statsData.processing ?? 0),
      pending: Number(statsData.pending ?? 0),
    }
  }

  // Fallback if statsData is not available
  const list = Array.isArray(recentSessions) ? recentSessions : []
  const total = totalFromList !== null && totalFromList !== undefined ? Number(totalFromList) : list.length

  return {
    total,
    completed: list.filter((s) => s?.status === 'completed').length,
    processing: list.filter((s) => s?.status === 'processing').length,
    pending: list.filter((s) => s?.status === 'pending').length,
  }
}

