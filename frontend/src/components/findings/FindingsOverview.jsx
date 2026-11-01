import { Layers, HelpCircle, Clock, AlertTriangle, ShieldAlert } from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { cn } from '@/lib/utils'

/**
 * FindingsOverview Component
 *
 * Displays high-level metrics for information gaps detected in the session:
 * - Total gap count
 * - Breakdown by category (Missing, Outdated, Conflicting, Unverified)
 * - Severity distribution (High, Medium, Low)
 *
 * @param {Object} props
 * @param {Array} props.findings - Array of FindingResponse objects
 * @param {string} [props.className]
 */
export function FindingsOverview({ findings = [], className }) {
  const safeFindings = Array.isArray(findings) ? findings : []

  // Category counts
  const missingCount = safeFindings.filter((f) => (f.category || '').toLowerCase() === 'missing').length
  const outdatedCount = safeFindings.filter((f) => (f.category || '').toLowerCase() === 'outdated').length
  const conflictingCount = safeFindings.filter((f) => (f.category || '').toLowerCase() === 'conflicting').length
  const unverifiedCount = safeFindings.filter((f) => (f.category || '').toLowerCase() === 'unverified').length

  // Severity counts
  const highSeverityCount = safeFindings.filter((f) => (f.severity || '').toLowerCase() === 'high').length
  const mediumSeverityCount = safeFindings.filter((f) => (f.severity || '').toLowerCase() === 'medium').length
  const lowSeverityCount = safeFindings.filter((f) => (f.severity || '').toLowerCase() === 'low').length

  const totalCount = safeFindings.length

  return (
    <GlassCard className={cn('p-5 space-y-4 text-left', className)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Total Count Header */}
        <div className="flex items-center gap-2.5">
          <div className="size-9 rounded-xl bg-[#2B2D42] text-[#EDF2F4] flex items-center justify-center shadow-xs">
            <Layers className="size-4.5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-[#2B2D42] leading-tight">
              Information Gap Metrics
            </h3>
            <p className="text-[11px] text-[#8D99AE]">
              {totalCount} total gap{totalCount === 1 ? '' : 's'} identified across sources
            </p>
          </div>
        </div>

        {/* Severity Distribution Badges */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-[11px] font-semibold text-[#8D99AE] mr-1">Severity:</span>
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#EF233C]/10 text-[#D90429] border border-[#EF233C]/25"
            title={`${highSeverityCount} high severity gap${highSeverityCount === 1 ? '' : 's'}`}
          >
            <span className="size-1.5 rounded-full bg-[#D90429]" />
            High: {highSeverityCount}
          </span>
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200/80"
            title={`${mediumSeverityCount} medium severity gap${mediumSeverityCount === 1 ? '' : 's'}`}
          >
            <span className="size-1.5 rounded-full bg-amber-500" />
            Medium: {mediumSeverityCount}
          </span>
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200"
            title={`${lowSeverityCount} low severity gap${lowSeverityCount === 1 ? '' : 's'}`}
          >
            <span className="size-1.5 rounded-full bg-slate-400" />
            Low: {lowSeverityCount}
          </span>
        </div>
      </div>

      {/* Category Breakdown Metric Tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1 border-t border-[#8D99AE]/15">
        {/* Missing */}
        <div className="p-3 rounded-xl bg-purple-50/70 border border-purple-200/60 space-y-1">
          <div className="flex items-center gap-1.5 text-purple-700 text-[11px] font-bold">
            <HelpCircle className="size-3.5" />
            Missing
          </div>
          <div className="text-xl font-bold font-heading text-purple-900">
            {missingCount}
          </div>
        </div>

        {/* Outdated */}
        <div className="p-3 rounded-xl bg-amber-50/70 border border-amber-200/60 space-y-1">
          <div className="flex items-center gap-1.5 text-amber-700 text-[11px] font-bold">
            <Clock className="size-3.5" />
            Outdated
          </div>
          <div className="text-xl font-bold font-heading text-amber-900">
            {outdatedCount}
          </div>
        </div>

        {/* Conflicting */}
        <div className="p-3 rounded-xl bg-rose-50/70 border border-rose-200/60 space-y-1">
          <div className="flex items-center gap-1.5 text-rose-700 text-[11px] font-bold">
            <AlertTriangle className="size-3.5" />
            Conflicting
          </div>
          <div className="text-xl font-bold font-heading text-rose-900">
            {conflictingCount}
          </div>
        </div>

        {/* Unverified */}
        <div className="p-3 rounded-xl bg-blue-50/70 border border-blue-200/60 space-y-1">
          <div className="flex items-center gap-1.5 text-blue-700 text-[11px] font-bold">
            <ShieldAlert className="size-3.5" />
            Unverified
          </div>
          <div className="text-xl font-bold font-heading text-blue-900">
            {unverifiedCount}
          </div>
        </div>
      </div>
    </GlassCard>
  )
}

