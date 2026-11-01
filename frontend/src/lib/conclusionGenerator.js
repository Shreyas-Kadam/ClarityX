/**
 * ClarityX Research Conclusion Generator
 *
 * Synthesizes a structured, evidence-grounded research conclusion from actual
 * session data without making unnecessary external AI inference requests.
 *
 * Adheres strictly to the ClarityX Core Principle:
 * "Don't just tell users what you found. Tell them what you haven't found."
 */

/**
 * Calculates verification checklist completion metrics.
 *
 * @param {Array} verificationItems
 * @returns {{ total: number, completed: number, pending: number, percentage: number }}
 */
export function calculateVerificationStats(verificationItems = []) {
  const safeItems = Array.isArray(verificationItems) ? verificationItems : []
  const total = safeItems.length
  const completed = safeItems.filter((t) => t.status === 'completed').length
  const pending = safeItems.filter((t) => t.status !== 'completed').length
  const percentage = total > 0 ? Math.round((completed / total) * 100) : 0
  return { total, completed, pending, percentage }
}

/**
 * Groups findings by the four canonical ClarityX categories.
 *
 * @param {Array} findings
 * @returns {{ missing: Array, outdated: Array, conflicting: Array, unverified: Array }}
 */
export function groupFindingsByCategory(findings = []) {
  const safeFindings = Array.isArray(findings) ? findings : []
  const groups = {
    missing: [],
    outdated: [],
    conflicting: [],
    unverified: [],
  }

  for (const f of safeFindings) {
    const cat = (f.category || '').toLowerCase().trim()
    if (cat in groups) {
      groups[cat].push(f)
    } else {
      groups.unverified.push(f)
    }
  }

  return groups
}

/**
 * Formats a timestamp into a clean printable date string.
 *
 * @param {string|Date|null} timestamp
 * @returns {string}
 */
export function formatPrintDate(timestamp) {
  if (!timestamp) return new Date().toLocaleDateString('en-US', { dateStyle: 'long' })
  const date = new Date(timestamp)
  if (isNaN(date.getTime())) return new Date().toLocaleDateString('en-US', { dateStyle: 'long' })
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Generates an objective, evidence-grounded conclusion from actual session data.
 *
 * @param {Object} params
 * @param {Object} [params.session={}]
 * @param {Array} [params.sources=[]]
 * @param {Array} [params.findings=[]]
 * @param {Array} [params.verificationItems=[]]
 * @param {Array} [params.unresolvedQuestions=[]]
 * @returns {Object} Structured conclusion data
 */
export function generateResearchConclusion({
  session = {},
  sources = [],
  findings = [],
  verificationItems = [],
  unresolvedQuestions = [],
}) {
  const researchGoal = session?.research_goal || 'Research Investigation'
  const summary = session?.summary || ''
  const safeSources = Array.isArray(sources) && sources.length > 0
    ? sources
    : (Array.isArray(session?.sources) ? session.sources : [])
  const safeFindings = Array.isArray(findings) && findings.length > 0
    ? findings
    : (Array.isArray(session?.findings) ? session.findings : [])
  const safeVerification = Array.isArray(verificationItems) && verificationItems.length > 0
    ? verificationItems
    : (Array.isArray(session?.verification_items) ? session.verification_items : [])
  const safeQuestions = Array.isArray(unresolvedQuestions) && unresolvedQuestions.length > 0
    ? unresolvedQuestions
    : (Array.isArray(session?.unresolved_questions) ? session.unresolved_questions : [])

  const grouped = groupFindingsByCategory(safeFindings)
  const vStats = calculateVerificationStats(safeVerification)

  const highSeverityFindings = safeFindings.filter(
    (f) => (f.severity || '').toLowerCase() === 'high'
  )
  const missingCount = grouped.missing.length
  const outdatedCount = grouped.outdated.length
  const conflictingCount = grouped.conflicting.length
  const unverifiedCount = grouped.unverified.length
  const totalFindings = safeFindings.length

  // 1. Scope of Current Evidence (What the analyzed information currently supports)
  let supportedText
  if (summary && summary.trim()) {
    supportedText = summary.trim()
  } else if (safeSources.length > 0) {
    supportedText = `Cross-referencing across ${safeSources.length} analyzed source(s) establishes baseline evidence regarding "${researchGoal}". Core definitions, contextual timelines, and source-attributed statements were cataloged.`
  } else {
    supportedText = `Preliminary investigation into "${researchGoal}" has been registered.`
  }

  // 2. Critical Information Gaps (What important gaps remain)
  const gapHighlights = []
  if (missingCount > 0) {
    gapHighlights.push(`${missingCount} critical missing parameter(s) where sources omitted necessary variables or empirical criteria`)
  }
  if (outdatedCount > 0) {
    gapHighlights.push(`${outdatedCount} outdated claim(s) relying on superseded historical timelines or obsolete benchmarks`)
  }
  if (conflictingCount > 0) {
    gapHighlights.push(`${conflictingCount} conflicting statement(s) presenting direct empirical or narrative contradictions between sources`)
  }
  if (unverifiedCount > 0) {
    gapHighlights.push(`${unverifiedCount} unverified assertion(s) lacking traceable citations or testable validation`)
  }

  let gapsText
  if (gapHighlights.length > 0) {
    gapsText = `Information gap detection flagged ${totalFindings} significant gap(s) (${gapHighlights.join('; ')}). ${
      highSeverityFindings.length > 0
        ? `${highSeverityFindings.length} high-severity gap(s) pose critical risk to analytical soundness.`
        : 'Identified gaps represent areas where evidentiary completeness is compromised.'
    }`
  } else {
    gapsText = 'No explicit information gaps or empirical contradictions were detected within the analyzed source set.'
  }

  // 3. Verification & Uncertainty Status (What information requires further verification)
  let verificationText
  if (vStats.total > 0) {
    verificationText = `The verification checklist tracks ${vStats.total} specific corroboration task(s), currently at ${vStats.percentage}% completion (${vStats.completed} completed, ${vStats.pending} pending).`
    if (vStats.pending > 0) {
      verificationText += ` ${vStats.pending} task(s) remain unresolved, requiring active ground-truth validation.`
    }
  } else {
    verificationText = 'No structured verification checklist tasks are currently registered.'
  }

  if (safeQuestions.length > 0) {
    verificationText += ` Additionally, ${safeQuestions.length} unresolved research question(s) remain open that cannot be answered by the currently available source corpus.`
  }

  // 4. Actionable Next Steps (What additional research would be useful)
  const actionableSteps = []
  for (const f of safeFindings) {
    if (f.recommended_action && typeof f.recommended_action === 'string' && f.recommended_action.trim()) {
      const trimmed = f.recommended_action.trim()
      if (!actionableSteps.includes(trimmed)) {
        actionableSteps.push(trimmed)
      }
    }
  }

  if (safeQuestions.length > 0) {
    actionableSteps.push('Conduct focused secondary retrieval to address open unresolved research questions.')
  }
  if (safeSources.length < 3) {
    actionableSteps.push('Ingest additional independent sources to enhance cross-verification confidence.')
  }
  if (actionableSteps.length === 0) {
    actionableSteps.push('Monitor primary industry disclosures and scientific literature for subsequent updates.')
  }

  // 5. ClarityX Analytical Verdict
  let verdictTitle
  let verdictSummary

  if (highSeverityFindings.length > 0 || conflictingCount > 0 || safeQuestions.length >= 2) {
    verdictTitle = 'INCONCLUSIVE — SUBSTANTIAL INFORMATION GAPS IDENTIFIED'
    verdictSummary = `Due to ${highSeverityFindings.length} high-severity gap(s), ${conflictingCount} contradictory claim(s), and ${safeQuestions.length} unresolved question(s), the available evidence does not currently warrant conclusive validation. Decisive claims regarding "${researchGoal}" should be withheld until the identified dark spots are corroborated.`
  } else if (totalFindings > 0 || vStats.pending > 0) {
    verdictTitle = 'PARTIALLY SUBSTANTIATED — CONDITIONAL VALIDITY'
    verdictSummary = `The core thesis is partially supported by available materials, but ${totalFindings} gap(s) and ${vStats.pending} pending verification task(s) indicate that critical dependencies remain unverified.`
  } else {
    verdictTitle = 'SUBSTANTIATED BASELINE — CONSISTENT DOCUMENTATION'
    verdictSummary = `The analyzed source material demonstrates internal coherence without detected omissions or contradictions, providing a defensible baseline for "${researchGoal}".`
  }

  return {
    researchGoal,
    supportedText,
    gapsText,
    gapHighlights,
    verificationText,
    verificationStats: vStats,
    actionableSteps: actionableSteps.slice(0, 5),
    verdictTitle,
    verdictSummary,
    highSeverityCount: highSeverityFindings.length,
    totalFindings,
    unresolvedCount: safeQuestions.length,
  }
}
