import {
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  ListChecks,
  Compass,
  Printer,
  ArrowRight,
} from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { generateResearchConclusion } from '@/lib/conclusionGenerator'

/**
 * ResearchConclusionCard Component
 *
 * Renders an objective, evidence-grounded research conclusion on screen
 * within the research investigation details view.
 *
 * Synthesizes:
 * 1. Definitive Analytical Verdict
 * 2. Scope of Supported Evidence
 * 3. Critical Information Gaps
 * 4. Verification & Uncertainty Status
 * 5. Actionable Next Steps
 *
 * Adheres strictly to the ClarityX Core Principle:
 * "Don't just tell users what you found. Tell them what you haven't found."
 *
 * @param {Object} props
 * @param {Object} props.session - Normalized research session data
 * @param {Array} props.sources - Array of source previews
 * @param {Function} [props.onNavigateTab] - Optional callback to switch tabs (e.g. 'findings', 'verification')
 */
export function ResearchConclusionCard({ session, sources = [], onNavigateTab }) {
  if (!session) return null

  const findingsList = Array.isArray(session.findings) ? session.findings : []
  const verificationList = Array.isArray(session.verification_items)
    ? session.verification_items
    : []
  const unresolvedList = Array.isArray(session.unresolved_questions)
    ? session.unresolved_questions
    : verificationList.filter((item) => !item.finding_id)
  const checklistTasks = verificationList.filter((item) => Boolean(item.finding_id))

  const conclusion = generateResearchConclusion({
    session,
    sources,
    findings: findingsList,
    verificationItems: checklistTasks.length > 0 ? checklistTasks : verificationList,
    unresolvedQuestions: unresolvedList,
  })

  const isHighRisk = conclusion.highSeverityCount > 0 || conclusion.verdictTitle.includes('INCONCLUSIVE')
  const isPartiallySubstantiated = conclusion.verdictTitle.includes('PARTIALLY')

  // Theme configuration based on analytical verdict
  const verdictTheme = isHighRisk
    ? {
        border: 'border-l-4 border-l-[#D90429]',
        badgeBg: 'bg-[#EF233C]/10 text-[#D90429] border border-[#EF233C]/30',
        cardBg: 'bg-gradient-to-br from-rose-50/40 to-white/70',
        icon: ShieldAlert,
        iconColor: 'text-[#D90429]',
      }
    : isPartiallySubstantiated
      ? {
          border: 'border-l-4 border-l-amber-500',
          badgeBg: 'bg-amber-500/10 text-amber-700 border border-amber-500/30',
          cardBg: 'bg-gradient-to-br from-amber-50/40 to-white/70',
          icon: AlertTriangle,
          iconColor: 'text-amber-600',
        }
      : {
          border: 'border-l-4 border-l-emerald-500',
          badgeBg: 'bg-emerald-500/10 text-emerald-700 border border-emerald-500/30',
          cardBg: 'bg-gradient-to-br from-emerald-50/40 to-white/70',
          icon: CheckCircle2,
          iconColor: 'text-emerald-600',
        }

  const VerdictIcon = verdictTheme.icon

  return (
    <GlassCard className={`p-6 sm:p-8 space-y-6 ${verdictTheme.border} ${verdictTheme.cardBg}`}>
      {/* Top Section: Analytical Verdict Banner */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-[#D90429] animate-pulse" />
            <span className="text-xs font-bold uppercase tracking-wider text-[#8D99AE]">
              ClarityX Analytical Conclusion & Verdict
            </span>
          </div>

          <div className="flex items-center gap-2">
            <NeuButton
              variant="ghost"
              size="sm"
              onClick={() => window.print()}
              icon={Printer}
              className="text-xs"
              title="Print official publication-grade conclusion report or save as PDF"
            >
              Print Report
            </NeuButton>
          </div>
        </div>

        <div className={`p-4 rounded-xl ${verdictTheme.badgeBg} flex items-start gap-3`}>
          <div className="p-1 rounded-lg bg-white/80 shrink-0">
            <VerdictIcon className={`size-5 ${verdictTheme.iconColor}`} />
          </div>
          <div className="space-y-1">
            <h4 className="text-xs sm:text-sm font-extrabold tracking-wide uppercase">
              {conclusion.verdictTitle}
            </h4>
            <p className="text-xs leading-relaxed opacity-90 font-medium">
              {conclusion.verdictSummary}
            </p>
          </div>
        </div>
      </div>

      {/* 4-Quadrant Analytical Breakdown Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Quadrant 1: Scope of Supported Evidence */}
        <div className="p-4 rounded-xl bg-white/80 border border-slate-200/60 shadow-xs space-y-2">
          <div className="flex items-center gap-2 text-xs font-bold text-[#2B2D42]">
            <CheckCircle2 className="size-4 text-emerald-600 shrink-0" />
            <span>Scope of Supported Evidence</span>
          </div>
          <p className="text-xs text-slate-700 leading-relaxed">
            {conclusion.supportedText}
          </p>
        </div>

        {/* Quadrant 2: Critical Information Gaps */}
        <div className="p-4 rounded-xl bg-white/80 border border-slate-200/60 shadow-xs space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs font-bold text-[#2B2D42]">
              <ShieldAlert className="size-4 text-[#D90429] shrink-0" />
              <span>Critical Information Gaps</span>
            </div>
            {onNavigateTab && (
              <button
                type="button"
                onClick={() => onNavigateTab('findings')}
                className="text-[11px] font-semibold text-[#D90429] hover:underline flex items-center gap-1 cursor-pointer"
              >
                View all ({conclusion.totalFindings})
                <ArrowRight className="size-3" />
              </button>
            )}
          </div>
          <p className="text-xs text-slate-700 leading-relaxed">
            {conclusion.gapsText}
          </p>
          {conclusion.gapHighlights?.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {conclusion.gapHighlights.map((hl, idx) => (
                <span
                  key={idx}
                  className="px-2 py-0.5 rounded-md bg-slate-100 text-[10px] font-medium text-slate-700"
                >
                  {hl}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Quadrant 3: Verification & Uncertainty Status */}
        <div className="p-4 rounded-xl bg-white/80 border border-slate-200/60 shadow-xs space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs font-bold text-[#2B2D42]">
              <ListChecks className="size-4 text-blue-600 shrink-0" />
              <span>Verification & Uncertainty Status</span>
            </div>
            {onNavigateTab && (
              <button
                type="button"
                onClick={() => onNavigateTab('verification')}
                className="text-[11px] font-semibold text-blue-600 hover:underline flex items-center gap-1 cursor-pointer"
              >
                Checklist ({conclusion.verificationStats.completed}/{conclusion.verificationStats.total})
                <ArrowRight className="size-3" />
              </button>
            )}
          </div>
          <p className="text-xs text-slate-700 leading-relaxed">
            {conclusion.verificationText}
          </p>
          {conclusion.verificationStats.total > 0 && (
            <div className="space-y-1 pt-1">
              <div className="flex justify-between text-[10px] text-slate-500 font-medium">
                <span>Checklist Completion</span>
                <span>{conclusion.verificationStats.percentage}%</span>
              </div>
              <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-600 rounded-full transition-all duration-300"
                  style={{ width: `${conclusion.verificationStats.percentage}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Quadrant 4: Actionable Next Steps */}
        <div className="p-4 rounded-xl bg-white/80 border border-slate-200/60 shadow-xs space-y-2">
          <div className="flex items-center gap-2 text-xs font-bold text-[#2B2D42]">
            <Compass className="size-4 text-purple-600 shrink-0" />
            <span>Actionable Next Steps</span>
          </div>
          <ul className="space-y-1.5 text-xs text-slate-700">
            {conclusion.actionableSteps.map((step, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <span className="size-1.5 rounded-full bg-purple-500 mt-1.5 shrink-0" />
                <span className="leading-snug">{step}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Bottom Footer: ClarityX Tenet */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-200/60 text-[11px] text-[#8D99AE]">
        <div className="flex items-center gap-1.5 italic font-medium">
          <span>&ldquo;Don&apos;t just tell users what you found. Tell them what you haven&apos;t found.&rdquo;</span>
        </div>
        <div className="text-[10px] font-mono text-slate-400">
          ClarityX Analytical Engine &bull; {sources.length} sources &bull; {conclusion.totalFindings} gaps identified
        </div>
      </div>
    </GlassCard>
  )
}
