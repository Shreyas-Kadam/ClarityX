import test from 'node:test'
import assert from 'node:assert/strict'
import { calculateDashboardCounts } from './dashboardMetrics.js'

test('1. calculateDashboardCounts accurately reflects complete dataset across more than 5 sessions', () => {
  // Scenario: User has 18 total sessions (11 completed, 4 processing, 3 pending).
  // The dashboard only fetches the 5 most recent records for the recent investigations list.
  const statsPayload = {
    total: 18,
    completed: 11,
    processing: 4,
    pending: 3,
    failed: 0,
  }

  const fiveRecentSessions = [
    { id: '1', status: 'completed' },
    { id: '2', status: 'completed' },
    { id: '3', status: 'processing' },
    { id: '4', status: 'pending' },
    { id: '5', status: 'completed' },
  ]

  const counts = calculateDashboardCounts(statsPayload, fiveRecentSessions, 18)

  // Verify counters are NOT constrained to the 5 recent sessions
  assert.equal(counts.total, 18)
  assert.equal(counts.completed, 11, 'Completed count must represent total dataset (11), not recent list (3)')
  assert.equal(counts.processing, 4, 'Processing count must represent total dataset (4), not recent list (1)')
  assert.equal(counts.pending, 3, 'Pending count must represent total dataset (3), not recent list (1)')
})

test('2. calculateDashboardCounts handles graceful fallback when statsData is null', () => {
  const recentSessions = [
    { id: '1', status: 'completed' },
    { id: '2', status: 'completed' },
    { id: '3', status: 'processing' },
    { id: '4', status: 'pending' },
  ]

  const counts = calculateDashboardCounts(null, recentSessions, 4)

  assert.equal(counts.total, 4)
  assert.equal(counts.completed, 2)
  assert.equal(counts.processing, 1)
  assert.equal(counts.pending, 1)
})

test('3. calculateDashboardCounts handles empty session state cleanly', () => {
  const countsEmpty = calculateDashboardCounts({ total: 0, completed: 0, processing: 0, pending: 0 })
  assert.equal(countsEmpty.total, 0)
  assert.equal(countsEmpty.completed, 0)
  assert.equal(countsEmpty.processing, 0)
  assert.equal(countsEmpty.pending, 0)

  const countsNull = calculateDashboardCounts(null, [], 0)
  assert.equal(countsNull.total, 0)
  assert.equal(countsNull.completed, 0)
})

