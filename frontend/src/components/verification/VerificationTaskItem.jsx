import { Check, Clock, RefreshCw } from 'lucide-react'
import { formatTimestamp } from '@/lib/formatters'
import { FindingCategoryBadge } from '@/components/findings'
import { cn } from '@/lib/utils'

/**
 * VerificationTaskItem Component
 *
 * Displays a single actionable verification checklist task with:
 * - Interactive status toggle (pending <-> completed)
 * - Task description with completion strikethrough styling
 * - Associated parent finding category and title pill (when available)
 * - Completion timestamp (when completed)
 * - Loading indicator and disabled state while update request is in flight
 *
 * @param {Object} props
 * @param {Object} props.task - VerificationItemResponse object
 * @param {Object} [props.finding] - Parent FindingResponse object (if resolved)
 * @param {Function} props.onToggle - Callback (taskId, currentStatus) => void
 * @param {boolean} [props.isUpdating=false] - Whether this task is currently updating
 * @param {string} [props.className]
 */
export function VerificationTaskItem({
  task,
  finding,
  onToggle,
  isUpdating = false,
  className,
}) {
  if (!task) return null

  const isCompleted = task.status === 'completed'
  const completedFormatted = formatTimestamp(task.completed_at)

  const handleToggle = () => {
    if (isUpdating || !onToggle) return
    onToggle(task.id, task.status)
  }

  return (
    <div
      className={cn(
        'p-3.5 rounded-xl border border-[#8D99AE]/15 bg-white/70 shadow-xs flex items-start gap-3 transition-all text-left',
        isCompleted && 'bg-slate-50/70 border-slate-200/60',
        className
      )}
    >
      {/* Checkbox Toggle Button */}
      <button
        type="button"
        onClick={handleToggle}
        disabled={isUpdating}
        role="checkbox"
        aria-checked={isCompleted}
        aria-label={
          isCompleted
            ? `Mark task "${task.task}" as pending`
            : `Mark task "${task.task}" as completed`
        }
        className={cn(
          'size-5 rounded-md flex items-center justify-center border transition-all cursor-pointer shrink-0 mt-0.5',
          isCompleted
            ? 'bg-emerald-600 border-emerald-600 text-white shadow-xs'
            : 'bg-white border-[#8D99AE]/40 hover:border-[#2B2D42] text-transparent',
          isUpdating && 'opacity-60 cursor-not-allowed'
        )}
        title={
          isUpdating
            ? 'Updating status...'
            : isCompleted
            ? 'Click to reopen task (mark pending)'
            : 'Click to mark task as completed'
        }
      >
        {isUpdating ? (
          <RefreshCw className="size-3 animate-spin text-emerald-700" />
        ) : isCompleted ? (
          <Check className="size-3.5 stroke-[3]" />
        ) : null}
      </button>

      {/* Task Content */}
      <div className="flex-1 min-w-0 space-y-1.5">
        <p
          className={cn(
            'text-xs text-[#2B2D42] leading-relaxed break-words font-medium',
            isCompleted && 'line-through text-[#8D99AE]'
          )}
        >
          {task.task}
        </p>

        {/* Metadata Footer: Finding Association & Timestamp */}
        <div className="flex flex-wrap items-center gap-2 pt-0.5">
          {/* Associated Finding Pill */}
          {finding && (
            <div className="inline-flex items-center gap-1.5 max-w-full">
              {finding.category && (
                <FindingCategoryBadge
                  category={finding.category}
                  className="text-[10px] py-0 px-2"
                />
              )}
              {finding.title && (
                <span
                  className="text-[11px] text-[#8D99AE] truncate max-w-[200px] sm:max-w-[320px]"
                  title={`Linked Finding: ${finding.title}`}
                >
                  {finding.title}
                </span>
              )}
            </div>
          )}

          {/* Completion Timestamp */}
          {isCompleted && completedFormatted && (
            <span
              className="inline-flex items-center gap-1 text-[10px] text-emerald-700 font-medium"
              title={`Completed at ${completedFormatted}`}
            >
              <Clock className="size-2.5 shrink-0" />
              Completed {completedFormatted}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

