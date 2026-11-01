import { useState } from 'react'
import { ChevronDown, ChevronUp, Sparkles, Quote } from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { formatConfidence } from '@/lib/formatters'
import { FindingCategoryBadge } from './FindingCategoryBadge'
import { FindingSeverityBadge } from './FindingSeverityBadge'
import { EvidenceQuote } from './EvidenceQuote'
import { cn } from '@/lib/utils'

/**
 * FindingCard Component
 *
 * Displays an individual information gap finding card including:
 * - Category and severity badges
 * - Confidence score percentage (when available)
 * - Finding title and detailed analytical description
 * - Recommended action callout (when non-empty)
 * - Attached evidence reference citations with expand/collapse support
 * - Safe missing evidence empty state
 *
 * @param {Object} props
 * @param {Object} props.finding - FindingResponse object
 * @param {Array} [props.sources=[]] - Ingested sources array for citation resolution
 * @param {string} [props.className]
 */
export function FindingCard({ finding, sources = [], className }) {
  const [isEvidenceExpanded, setIsEvidenceExpanded] = useState(true)

  if (!finding) return null

  const evidenceList = Array.isArray(finding.evidence_references) ? finding.evidence_references : []
  const evidenceCount = evidenceList.length
  const formattedConfidence = formatConfidence(finding.confidence)
  const hasAction = Boolean(finding.recommended_action && finding.recommended_action.trim().length > 0)

  // Map sources by ID and source_code for quick lookup
  const sourcesById = new Map((sources || []).map((s) => [s.id, s]))
  const sourcesByCode = new Map((sources || []).map((s) => [s.source_code, s]))

  return (
    <GlassCard className={cn('p-5 space-y-4 text-left transition-all', className)}>
      {/* Header: Badges & Confidence */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 pb-1 border-b border-[#8D99AE]/15">
        <div className="flex flex-wrap items-center gap-2">
          <FindingCategoryBadge category={finding.category} />
          <FindingSeverityBadge severity={finding.severity} />

          {formattedConfidence && (
            <span
              className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200"
              title="Model self-reported confidence score"
            >
              <Sparkles className="size-3 text-amber-500" />
              <span>{formattedConfidence} confidence</span>
            </span>
          )}
        </div>

        {/* Evidence Count Pill */}
        <span className="text-[11px] font-semibold text-[#8D99AE] flex items-center gap-1">
          <Quote className="size-3" />
          {evidenceCount} citation{evidenceCount === 1 ? '' : 's'}
        </span>
      </div>

      {/* Title & Description */}
      <div className="space-y-1.5">
        <h4 className="text-base font-bold text-[#2B2D42] leading-snug">
          {finding.title || 'Untitled Information Gap'}
        </h4>
        <p className="text-xs text-[#2B2D42]/90 leading-relaxed whitespace-pre-wrap">
          {finding.description || 'No detailed explanation provided for this finding.'}
        </p>
      </div>

      {/* Recommended Action (Only shown when meaningful text exists) */}
      {hasAction && (
        <div className="p-3.5 rounded-xl neu-inset bg-white/40 space-y-1 border border-[#8D99AE]/10">
          <div className="text-[11px] font-bold uppercase tracking-wider text-[#8D99AE] flex items-center gap-1.5">
            <Sparkles className="size-3 text-[#D90429]" />
            Recommended Action
          </div>
          <p className="text-xs text-[#2B2D42] leading-relaxed">
            {finding.recommended_action.trim()}
          </p>
        </div>
      )}

      {/* Evidence References Section */}
      <div className="space-y-2 pt-1 border-t border-[#8D99AE]/15">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-bold uppercase tracking-wider text-[#8D99AE]">
            Supporting & Contextual Evidence
          </span>

          {evidenceCount > 0 && (
            <button
              type="button"
              onClick={() => setIsEvidenceExpanded(!isEvidenceExpanded)}
              className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#8D99AE] hover:text-[#2B2D42] transition-colors cursor-pointer"
              title={isEvidenceExpanded ? 'Collapse evidence quotes' : 'Expand evidence quotes'}
            >
              {isEvidenceExpanded ? (
                <>
                  <span>Hide Citations</span>
                  <ChevronUp className="size-3.5" />
                </>
              ) : (
                <>
                  <span>Show Citations ({evidenceCount})</span>
                  <ChevronDown className="size-3.5" />
                </>
              )}
            </button>
          )}
        </div>

        {evidenceCount > 0 ? (
          isEvidenceExpanded && (
            <div className="space-y-2 pt-1">
              {evidenceList.map((ev, index) => {
                const resolvedSource =
                  sourcesById.get(ev.source_id) || sourcesByCode.get(ev.source_code)
                const key = ev.id || `${finding.id}-ev-${index}`
                return <EvidenceQuote key={key} evidence={ev} source={resolvedSource} />
              })}
            </div>
          )
        ) : (
          <div className="p-3 rounded-xl bg-slate-50/70 border border-slate-200/60 text-xs text-[#8D99AE] italic leading-relaxed">
            No direct evidence excerpts cited. This may indicate information absent from the available sources.
          </div>
        )}
      </div>
    </GlassCard>
  )
}
