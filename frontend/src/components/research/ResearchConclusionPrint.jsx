import {
  formatPrintDate,
  groupFindingsByCategory,
  calculateVerificationStats,
  generateResearchConclusion,
} from '@/lib/conclusionGenerator'

/**
 * ResearchConclusionPrint Component
 *
 * Renders an official, publication-grade research assessment document
 * specifically formatted for browser printing and "Save as PDF" export.
 *
 * Hidden in screen display via `hidden print:block`.
 *
 * @param {Object} props
 * @param {Object} props.session - Normalized research session data
 * @param {Array} props.sources - Array of source previews
 */
export function ResearchConclusionPrint({ session, sources = [] }) {
  if (!session) return null

  const findingsList = Array.isArray(session.findings) ? session.findings : []
  const verificationList = Array.isArray(session.verification_items)
    ? session.verification_items
    : []
  const unresolvedList = Array.isArray(session.unresolved_questions)
    ? session.unresolved_questions
    : verificationList.filter((item) => !item.finding_id)
  const checklistTasks = verificationList.filter((item) => Boolean(item.finding_id))

  const groupedFindings = groupFindingsByCategory(findingsList)
  const vStats = calculateVerificationStats(checklistTasks.length > 0 ? checklistTasks : verificationList)

  const conclusion = generateResearchConclusion({
    session,
    sources,
    findings: findingsList,
    verificationItems: checklistTasks.length > 0 ? checklistTasks : verificationList,
    unresolvedQuestions: unresolvedList,
  })

  // Build a lookup map of sources by ID and code
  const sourcesMap = new Map()
  for (const s of sources) {
    if (s.id) sourcesMap.set(String(s.id), s)
    if (s.source_code) sourcesMap.set(String(s.source_code), s)
  }

  // Build findings lookup by ID
  const findingsMap = new Map()
  for (const f of findingsList) {
    if (f.id) findingsMap.set(String(f.id), f)
  }

  // Flatten all genuine evidence references
  const allEvidence = []
  for (const f of findingsList) {
    if (Array.isArray(f.evidence_references)) {
      for (const ev of f.evidence_references) {
        allEvidence.push({
          ...ev,
          findingTitle: f.title,
          findingCategory: f.category,
        })
      }
    }
  }

  const generationDate = formatPrintDate(session.updated_at || session.created_at || new Date())

  return (
    <div className="hidden print:block w-full max-w-[210mm] mx-auto bg-white text-slate-900 font-sans p-6 space-y-6 text-[10pt] leading-normal print-document">
      {/* =====================================================================
          A. BRANDING HEADER
          ===================================================================== */}
      <header className="border-b-2 border-slate-900 pb-4 flex items-start justify-between gap-4 break-inside-avoid">
        <div>
          <div className="flex items-center gap-2">
            <div className="size-6 rounded-md bg-[#D90429] flex items-center justify-center text-white font-black text-xs">
              CX
            </div>
            <h1 className="text-xl font-black tracking-tight text-slate-900 font-heading">
              CLARITYX
            </h1>
          </div>
          <p className="text-[8pt] uppercase tracking-widest font-semibold text-slate-500 mt-0.5">
            AI-Assisted Information Gap Detection Platform
          </p>
        </div>

        <div className="text-right">
          <div className="text-[11pt] font-black tracking-wide text-slate-900 uppercase">
            RESEARCH CONCLUSION
          </div>
          <div className="text-[8pt] text-slate-600 mt-0.5">
            Generated: {generationDate}
          </div>
          <div className="text-[7pt] uppercase tracking-wider font-bold text-[#D90429] mt-0.5">
            Official Assessment Document
          </div>
        </div>
      </header>

      {/* =====================================================================
          B. RESEARCH INFORMATION
          ===================================================================== */}
      <section className="space-y-3 break-inside-avoid">
        <div className="p-4 rounded-lg bg-slate-50 border-l-4 border-l-[#D90429] border border-slate-200">
          <div className="text-[8pt] uppercase font-bold tracking-wider text-slate-500">
            Research Investigation Objective
          </div>
          <h2 className="text-sm font-bold text-slate-900 mt-1 leading-snug">
            {session.research_goal}
          </h2>
        </div>

        <div className="grid grid-cols-4 gap-2 text-[8pt]">
          <div className="p-2.5 rounded bg-slate-50 border border-slate-200">
            <span className="text-slate-500 block font-semibold uppercase text-[7pt]">Session ID</span>
            <span className="font-mono text-slate-800 text-[8pt] truncate block" title={session.id}>
              {session.id ? session.id.slice(0, 18) + '...' : 'N/A'}
            </span>
          </div>

          <div className="p-2.5 rounded bg-slate-50 border border-slate-200">
            <span className="text-slate-500 block font-semibold uppercase text-[7pt]">Sources Analyzed</span>
            <span className="font-bold text-slate-800 text-[10pt] block">
              {sources.length} source{sources.length === 1 ? '' : 's'}
            </span>
          </div>

          <div className="p-2.5 rounded bg-slate-50 border border-slate-200">
            <span className="text-slate-500 block font-semibold uppercase text-[7pt]">Identified Gaps</span>
            <span className="font-bold text-slate-800 text-[10pt] block">
              {findingsList.length} gap{findingsList.length === 1 ? '' : 's'}
            </span>
          </div>

          <div className="p-2.5 rounded bg-slate-50 border border-slate-200">
            <span className="text-slate-500 block font-semibold uppercase text-[7pt]">Verification Status</span>
            <span className="font-bold text-slate-800 text-[10pt] block">
              {vStats.percentage}% verified
            </span>
          </div>
        </div>
      </section>

      {/* =====================================================================
          C. EXECUTIVE SUMMARY
          ===================================================================== */}
      <section className="space-y-2 break-inside-avoid">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-1 flex items-center justify-between">
          <span>1. Executive Summary & Investigation Scope</span>
        </h3>
        <p className="text-[9pt] text-slate-800 leading-relaxed text-justify">
          {session.summary && session.summary.trim()
            ? session.summary.trim()
            : conclusion.supportedText}
        </p>
      </section>

      {/* =====================================================================
          D. KEY CATEGORIZED FINDINGS
          ===================================================================== */}
      <section className="space-y-3">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-1 break-after-avoid">
          <span>2. Key Information Gap Findings</span>
        </h3>

        {findingsList.length === 0 ? (
          <div className="p-3 bg-slate-50 border border-slate-200 text-slate-600 italic text-[9pt] text-center rounded">
            No findings identified in this analysis. The analyzed sources did not present detected omissions, contradictions, or unverified claims.
          </div>
        ) : (
          <div className="space-y-3">
            {/* Missing Information */}
            {groupedFindings.missing.length > 0 && (
              <div className="space-y-2 break-inside-avoid">
                <div className="flex items-center gap-2 border-b border-amber-300 pb-0.5">
                  <span className="px-1.5 py-0.5 rounded text-[7pt] font-bold uppercase bg-amber-100 text-amber-900 border border-amber-300">
                    Missing Information ({groupedFindings.missing.length})
                  </span>
                  <span className="text-[8pt] text-slate-500 italic">Critical parameters or data omitted</span>
                </div>
                {groupedFindings.missing.map((f) => (
                  <FindingPrintCard key={f.id} finding={f} sourcesMap={sourcesMap} />
                ))}
              </div>
            )}

            {/* Outdated Information */}
            {groupedFindings.outdated.length > 0 && (
              <div className="space-y-2 break-inside-avoid">
                <div className="flex items-center gap-2 border-b border-slate-300 pb-0.5">
                  <span className="px-1.5 py-0.5 rounded text-[7pt] font-bold uppercase bg-slate-200 text-slate-900 border border-slate-300">
                    Outdated Information ({groupedFindings.outdated.length})
                  </span>
                  <span className="text-[8pt] text-slate-500 italic">Superseded timelines or obsolete benchmarks</span>
                </div>
                {groupedFindings.outdated.map((f) => (
                  <FindingPrintCard key={f.id} finding={f} sourcesMap={sourcesMap} />
                ))}
              </div>
            )}

            {/* Conflicting Information */}
            {groupedFindings.conflicting.length > 0 && (
              <div className="space-y-2 break-inside-avoid">
                <div className="flex items-center gap-2 border-b border-red-300 pb-0.5">
                  <span className="px-1.5 py-0.5 rounded text-[7pt] font-bold uppercase bg-red-100 text-red-900 border border-red-300">
                    Conflicting Information ({groupedFindings.conflicting.length})
                  </span>
                  <span className="text-[8pt] text-slate-500 italic">Direct empirical discrepancies between sources</span>
                </div>
                {groupedFindings.conflicting.map((f) => (
                  <FindingPrintCard key={f.id} finding={f} sourcesMap={sourcesMap} />
                ))}
              </div>
            )}

            {/* Unverified Information */}
            {groupedFindings.unverified.length > 0 && (
              <div className="space-y-2 break-inside-avoid">
                <div className="flex items-center gap-2 border-b border-purple-300 pb-0.5">
                  <span className="px-1.5 py-0.5 rounded text-[7pt] font-bold uppercase bg-purple-100 text-purple-900 border border-purple-300">
                    Unverified Information ({groupedFindings.unverified.length})
                  </span>
                  <span className="text-[8pt] text-slate-500 italic">Unsubstantiated claims lacking primary evidence</span>
                </div>
                {groupedFindings.unverified.map((f) => (
                  <FindingPrintCard key={f.id} finding={f} sourcesMap={sourcesMap} />
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      {/* =====================================================================
          E. SUPPORTING EVIDENCE
          ===================================================================== */}
      {allEvidence.length > 0 && (
        <section className="space-y-2 break-inside-avoid">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-1">
            <span>3. Supporting Evidence Citations</span>
          </h3>
          <div className="space-y-2">
            {allEvidence.map((ev, idx) => {
              const matchedSource =
                sourcesMap.get(String(ev.source_id)) ||
                sourcesMap.get(String(ev.source_code))

              return (
                <div
                  key={ev.id || `evidence-${idx}`}
                  className="p-2.5 rounded bg-slate-50 border border-slate-200 text-[8pt] space-y-1"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-slate-900">
                      [{ev.source_code || `S${idx + 1}`}] {matchedSource?.title || 'Referenced Source'}
                    </span>
                    <span className="text-[7pt] uppercase font-semibold text-slate-500">
                      Linked to: {ev.findingTitle}
                    </span>
                  </div>

                  <blockquote className="italic text-slate-700 border-l-2 border-slate-400 pl-2 my-1">
                    &ldquo;{ev.evidence_text}&rdquo;
                  </blockquote>

                  {matchedSource?.url && (
                    <div className="text-[7pt] text-slate-500 truncate">
                      Source URL: {matchedSource.url}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* =====================================================================
          F. UNRESOLVED RESEARCH QUESTIONS
          ===================================================================== */}
      <section className="space-y-2 break-inside-avoid">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-1">
          <span>4. Unresolved Research Questions</span>
        </h3>
        {unresolvedList.length === 0 ? (
          <div className="p-3 bg-slate-50 border border-slate-200 text-slate-600 italic text-[9pt] text-center rounded">
            No unresolved research questions identified.
          </div>
        ) : (
          <div className="space-y-1.5">
            <p className="text-[8pt] text-slate-600 mb-1">
              The following broader analytical inquiries could not be definitively answered from the supplied reference material:
            </p>
            {unresolvedList.map((q, idx) => {
              const taskText = typeof q === 'string' ? q : q.task
              return (
                <div
                  key={q.id || `unresolved-${idx}`}
                  className="p-2 rounded bg-slate-50 border border-slate-200 flex items-start gap-2 text-[8pt]"
                >
                  <span className="font-bold text-purple-900 shrink-0 font-mono">
                    Q{idx + 1}.
                  </span>
                  <span className="text-slate-800 font-medium">
                    {taskText}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* =====================================================================
          G. VERIFICATION PROGRESS
          ===================================================================== */}
      <section className="space-y-2 break-inside-avoid">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-1">
          <span>5. Verification Checklist & Corroboration Status</span>
        </h3>

        <div className="flex items-center justify-between text-[8pt] p-2.5 rounded bg-slate-50 border border-slate-200">
          <div>
            <strong>Checklist Completion:</strong> {vStats.percentage}% ({vStats.completed} completed of {vStats.total} total tasks)
          </div>
          <div>
            <strong>Pending Actions:</strong> {vStats.pending} task{vStats.pending === 1 ? '' : 's'} remaining
          </div>
        </div>

        {checklistTasks.length > 0 && (
          <div className="space-y-1.5">
            {checklistTasks.map((t, idx) => {
              const isDone = t.status === 'completed'
              const parentFinding = findingsMap.get(t.finding_id)

              return (
                <div
                  key={t.id || `task-${idx}`}
                  className="flex items-start justify-between gap-3 p-2 rounded border border-slate-200 text-[8pt] bg-white"
                >
                  <div className="flex items-start gap-2">
                    <span className={`font-mono text-[9pt] font-bold ${isDone ? 'text-emerald-700' : 'text-slate-400'}`}>
                      {isDone ? '[✓]' : '[ ]'}
                    </span>
                    <div>
                      <span className={`font-medium ${isDone ? 'line-through text-slate-500' : 'text-slate-900'}`}>
                        {t.task}
                      </span>
                      {parentFinding && (
                        <span className="text-[7pt] text-slate-500 block">
                          Related Finding: {parentFinding.title}
                        </span>
                      )}
                    </div>
                  </div>

                  <span className={`text-[7pt] uppercase font-bold px-1.5 py-0.5 rounded ${
                    isDone ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-700'
                  }`}>
                    {isDone ? 'Verified' : 'Pending'}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* =====================================================================
          H. FINAL CONCLUSION & ANALYTICAL VERDICT
          ===================================================================== */}
      <section className="space-y-3 break-inside-avoid">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-1">
          <span>6. Final Analytical Conclusion & Assessment Verdict</span>
        </h3>

        {/* Four Core Synthesis Dimensions */}
        <div className="space-y-2 text-[8pt] text-slate-800 leading-relaxed text-justify">
          <div>
            <strong className="text-slate-900 block font-bold text-[8.5pt]">
              A. Scope of Currently Supported Information:
            </strong>
            <p>{conclusion.supportedText}</p>
          </div>

          <div>
            <strong className="text-slate-900 block font-bold text-[8.5pt]">
              B. Critical Information Gaps & Empirical Dark Spots:
            </strong>
            <p>{conclusion.gapsText}</p>
          </div>

          <div>
            <strong className="text-slate-900 block font-bold text-[8.5pt]">
              C. Verification Status & Ground-Truth Dependencies:
            </strong>
            <p>{conclusion.verificationText}</p>
          </div>

          <div>
            <strong className="text-slate-900 block font-bold text-[8.5pt]">
              D. Actionable Corroboration Next Steps:
            </strong>
            <ul className="list-disc list-inside space-y-0.5 mt-0.5">
              {conclusion.actionableSteps.map((step, idx) => (
                <li key={idx}>{step}</li>
              ))}
            </ul>
          </div>
        </div>

        {/* ClarityX Official Verdict Callout */}
        <div className="p-4 rounded-lg bg-slate-100 border-2 border-slate-900 space-y-1.5 mt-3">
          <div className="text-[7pt] uppercase tracking-widest font-bold text-[#D90429]">
            ClarityX Analytical Synthesis Verdict
          </div>
          <div className="text-xs font-black text-slate-900 uppercase">
            {conclusion.verdictTitle}
          </div>
          <p className="text-[8.5pt] text-slate-800 leading-relaxed text-justify font-medium">
            {conclusion.verdictSummary}
          </p>
          <p className="text-[7pt] text-slate-500 italic pt-1 border-t border-slate-300">
            * Assessment derived strictly from evaluated evidence references. Never assume unverified claims are correct.
          </p>
        </div>
      </section>

      {/* =====================================================================
          I. PROFESSIONAL FOOTER
          ===================================================================== */}
      <footer className="border-t-2 border-slate-900 pt-3 flex items-center justify-between text-[7pt] text-slate-500 break-inside-avoid">
        <div>
          <div className="font-bold text-slate-800">
            Powered by ClarityX • AI-Assisted Information Gap Detection
          </div>
          <div className="italic text-slate-600 mt-0.5">
            &ldquo;Don&apos;t just tell users what you found. Tell them what you haven&apos;t found.&rdquo;
          </div>
        </div>

        <div className="text-right">
          <div>Generated on: {generationDate}</div>
          <div>Page 1 of Evaluation • ClarityX Research Engine v0.1</div>
        </div>
      </footer>
    </div>
  )
}

/**
 * Finding Card component for printable reports.
 */
function FindingPrintCard({ finding, sourcesMap }) {
  const severityColors = {
    high: 'bg-red-100 text-red-900 border-red-300',
    medium: 'bg-amber-100 text-amber-900 border-amber-300',
    low: 'bg-slate-100 text-slate-800 border-slate-300',
  }
  const severity = (finding.severity || 'medium').toLowerCase()
  const sevStyle = severityColors[severity] || severityColors.medium

  return (
    <div className="p-2.5 rounded bg-slate-50 border border-slate-200 space-y-1 text-[8pt] break-inside-avoid">
      <div className="flex items-start justify-between gap-2">
        <h4 className="font-bold text-slate-900 text-[8.5pt]">
          {finding.title}
        </h4>
        <span className={`px-1.5 py-0.5 rounded text-[6.5pt] font-bold uppercase border ${sevStyle}`}>
          {severity} Severity
        </span>
      </div>

      <p className="text-slate-700 text-justify">
        {finding.description}
      </p>

      {finding.recommended_action && (
        <div className="text-[7.5pt] text-slate-600 bg-white p-1.5 rounded border border-slate-200">
          <strong>Recommended Action:</strong> {finding.recommended_action}
        </div>
      )}

      {Array.isArray(finding.evidence_references) && finding.evidence_references.length > 0 && (
        <div className="text-[7pt] text-slate-500 pt-0.5">
          <strong>Attributed Sources:</strong>{' '}
          {finding.evidence_references.map((ev, idx) => {
            const matched =
              sourcesMap.get(String(ev.source_id)) ||
              sourcesMap.get(String(ev.source_code))
            return (
              <span key={ev.id || idx} className="mr-2">
                [{ev.source_code || `S${idx + 1}`}] {matched?.title ? `"${matched.title}"` : ''}
              </span>
            )
          })}
        </div>
      )}
    </div>
  )
}

