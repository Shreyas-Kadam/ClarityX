import { CheckCircle2 } from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { cn } from '@/lib/utils'

/**
 * VerificationProgress Component
 *
 * Displays task completion progress with a metric counter and a visual progress bar.
 * Safely handles zero-task scenarios without division-by-zero errors.
 *
 * @param {Object} props
 * @param {number} props.total - Total number of verification tasks
 * @param {number} props.completed - Number of completed tasks
 * @param {string} [props.className]
 */
export function VerificationProgress({ total = 0, completed = 0, className }) {
  const safeTotal = Math.max(0, Number(total) || 0)
  const safeCompleted = Math.max(0, Math.min(safeTotal, Number(completed) || 0))
  const percentage = safeTotal === 0 ? 0 : Math.round((safeCompleted / safeTotal) * 100)

  return (
    <GlassCard className={cn('p-4 space-y-3 text-left', className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <div className="size-8 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200/80 flex items-center justify-center shrink-0">
            <CheckCircle2 className="size-4" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-[#2B2D42]">
              Checklist Progress
            </h4>
            <p className="text-[11px] text-[#8D99AE]">
              {safeCompleted} of {safeTotal} task{safeTotal === 1 ? '' : 's'} completed
            </p>
          </div>
        </div>
        <div className="text-right">
          <span className="text-base font-heading font-bold text-[#2B2D42]">
            {percentage}%
          </span>
        </div>
      </div>

      {/* Progress Track */}
      <div className="h-2 w-full rounded-full bg-slate-200/70 overflow-hidden neu-inset">
        <div
          className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 transition-all duration-300"
          style={{ width: `${percentage}%` }}
        />
      </div>
    </GlassCard>
  )
}

