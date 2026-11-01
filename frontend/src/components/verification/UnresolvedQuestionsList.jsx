import { HelpCircle } from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { cn } from '@/lib/utils'

/**
 * UnresolvedQuestionsList Component
 *
 * Displays broad open research questions identified by AI analysis
 * (stored with finding_id = NULL).
 * Strictly read-only: does NOT render checkboxes or interactive completion controls.
 *
 * @param {Object} props
 * @param {Array} props.questions - Array of UnresolvedQuestionResponse objects
 * @param {string} [props.className]
 */
export function UnresolvedQuestionsList({ questions = [], className }) {
  const safeQuestions = Array.isArray(questions) ? questions : []

  if (safeQuestions.length === 0) return null

  return (
    <GlassCard className={cn('p-5 space-y-3.5 text-left', className)}>
      <div className="flex items-start gap-2.5">
        <div className="size-8 rounded-lg bg-purple-50 text-purple-700 border border-purple-200/80 flex items-center justify-center shrink-0 mt-0.5">
          <HelpCircle className="size-4" />
        </div>
        <div className="space-y-0.5">
          <h4 className="text-sm font-bold text-[#2B2D42]">
            Unresolved Research Questions
          </h4>
          <p className="text-xs text-[#8D99AE] leading-relaxed">
            Broader exploratory inquiries identified during analysis that remain unanswered by the available source material.
          </p>
        </div>
      </div>

      <div className="space-y-2 pt-1">
        {safeQuestions.map((q, idx) => (
          <div
            key={q.id || `unresolved-q-${idx}`}
            className="p-3 rounded-xl neu-inset bg-white/40 border border-[#8D99AE]/10 flex items-start gap-2.5"
          >
            <span className="size-5 rounded-full bg-purple-100 text-purple-800 text-[11px] font-bold font-mono flex items-center justify-center shrink-0 mt-0.5">
              {idx + 1}
            </span>
            <p className="text-xs text-[#2B2D42] leading-relaxed font-medium">
              {q.task}
            </p>
          </div>
        ))}
      </div>
    </GlassCard>
  )
}

