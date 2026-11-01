import test from 'node:test'
import assert from 'node:assert/strict'
import {
  calculateVerificationStats,
  groupFindingsByCategory,
  generateResearchConclusion,
  formatPrintDate,
} from './conclusionGenerator.js'

test('1. calculateVerificationStats accurately calculates total, completed, pending, and percentage', () => {
  const items = [
    { id: '1', status: 'completed' },
    { id: '2', status: 'completed' },
    { id: '3', status: 'pending' },
    { id: '4', status: 'pending' },
  ]
  const stats = calculateVerificationStats(items)
  assert.equal(stats.total, 4)
  assert.equal(stats.completed, 2)
  assert.equal(stats.pending, 2)
  assert.equal(stats.percentage, 50)

  // Empty items test
  const emptyStats = calculateVerificationStats([])
  assert.equal(emptyStats.total, 0)
  assert.equal(emptyStats.percentage, 0)
})

test('2. groupFindingsByCategory cleanly groups into missing, outdated, conflicting, and unverified', () => {
  const findings = [
    { id: '1', category: 'missing', title: 'Cathode timeline missing' },
    { id: '2', category: 'outdated', title: '2022 projections used' },
    { id: '3', category: 'conflicting', title: 'Cost discrepancy between sources' },
    { id: '4', category: 'unverified', title: 'Lab yield claim without data' },
    { id: '5', category: 'MISSING', title: 'Case insensitive test' },
  ]
  const groups = groupFindingsByCategory(findings)
  assert.equal(groups.missing.length, 2)
  assert.equal(groups.outdated.length, 1)
  assert.equal(groups.conflicting.length, 1)
  assert.equal(groups.unverified.length, 1)
})

test('3. generateResearchConclusion handles full report with all four finding categories and high severity', () => {
  const session = {
    id: 'test-session-123',
    research_goal: 'Assess commercial viability of solid-state lithium cells by 2027',
    summary: 'Preliminary analysis indicates technical feasibility in lab conditions but significant supply chain divergence.',
  }
  const sources = [
    { id: 's1', source_code: 'S1', title: 'Battery Tech Report 2026', url: 'https://example.com/s1' },
    { id: 's2', source_code: 'S2', title: 'Industry Raw Materials Quarterly', url: 'https://example.com/s2' },
  ]
  const findings = [
    {
      id: 'f1',
      category: 'missing',
      title: 'Lithium sulfide raw material yield omitted',
      severity: 'high',
      recommended_action: 'Acquire supplier supply volume projections.',
    },
    {
      id: 'f2',
      category: 'outdated',
      title: 'Cost model relies on 2021 nickel prices',
      severity: 'medium',
      recommended_action: 'Update pricing matrix to current spot rates.',
    },
    {
      id: 'f3',
      category: 'conflicting',
      title: 'Cycle life claims conflict between S1 and S2',
      severity: 'high',
      recommended_action: 'Verify independent third-party degradation benchmarks.',
    },
    {
      id: 'f4',
      category: 'unverified',
      title: 'Giga-factory ramp-up schedule unverified',
      severity: 'low',
      recommended_action: 'Check municipal construction permits.',
    },
  ]
  const verificationItems = [
    { id: 'v1', task: 'Check supplier volume', status: 'completed' },
    { id: 'v2', task: 'Obtain nickel spot prices', status: 'pending' },
  ]
  const unresolvedQuestions = [
    { id: 'u1', task: 'What is the true failure rate under cold-weather operating conditions?' },
  ]

  const conclusion = generateResearchConclusion({
    session,
    sources,
    findings,
    verificationItems,
    unresolvedQuestions,
  })

  assert.equal(conclusion.researchGoal, session.research_goal)
  assert.match(conclusion.supportedText, /Preliminary analysis indicates/)
  assert.match(conclusion.gapsText, /4 significant gap\(s\)/)
  assert.match(conclusion.gapsText, /2 high-severity gap\(s\)/)
  assert.match(conclusion.verificationText, /50% completion/)
  assert.match(conclusion.verificationText, /1 unresolved research question\(s\)/)
  assert.equal(conclusion.verdictTitle, 'INCONCLUSIVE — SUBSTANTIAL INFORMATION GAPS IDENTIFIED')
  assert.ok(conclusion.actionableSteps.length > 0)
})

test('4. generateResearchConclusion handles empty findings cleanly without fabricating gaps or certainty', () => {
  const session = {
    id: 'clean-session-456',
    research_goal: 'Confirm definition of IEEE 802.11be protocol standard',
    summary: 'All sources provide aligned documentation matching the ratified standard.',
  }
  const sources = [
    { id: 's1', source_code: 'S1', title: 'IEEE Standard 802.11be' },
  ]

  const conclusion = generateResearchConclusion({
    session,
    sources,
    findings: [],
    verificationItems: [],
    unresolvedQuestions: [],
  })

  assert.match(conclusion.gapsText, /No explicit information gaps or empirical contradictions were detected/)
  assert.match(conclusion.verdictTitle, /SUBSTANTIATED BASELINE/)
  assert.equal(conclusion.highSeverityCount, 0)
  assert.equal(conclusion.totalFindings, 0)
  assert.equal(conclusion.unresolvedCount, 0)
})

test('5. formatPrintDate handles timestamps and nulls gracefully', () => {
  const formatted = formatPrintDate('2026-11-01T12:00:00Z')
  assert.ok(typeof formatted === 'string')
  assert.match(formatted, /2026/)

  const nullFormatted = formatPrintDate(null)
  assert.ok(typeof nullFormatted === 'string')
})

