import { useState, useMemo } from 'react'
import { ListChecks, CheckCircle2, Clock, Filter, AlertCircle, X } from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { VerificationProgress } from './VerificationProgress'
import { VerificationTaskItem } from './VerificationTaskItem'
import { UnresolvedQuestionsList } from './UnresolvedQuestionsList'
import { cn } from '@/lib/utils'

/**
 * VerificationChecklist Component
 *
 * Full verification checklist interface supporting:
 * - Progress tracking bar & completion percentage
 * - Client-side status filters (All, Pending, Completed)
 * - Interactive checklist task list with linked findings
 * - Read-only unresolved research questions section
 * - Differentiated empty states and inline error feedback
 *
 * @param {Object} props
 * @param {Array} props.tasks - Array of VerificationItemResponse objects
 * @param {Array} [props.unresolvedQuestions=[]] - Array of UnresolvedQuestionResponse objects
 * @param {Array} [props.findings=[]] - Array of FindingResponse objects for parent finding resolution
 * @param {Function} props.onToggleTask - Callback (taskId, currentStatus) => void
 * @param {Set|Object} [props.updatingTaskIds] - Set of task IDs currently being updated
 * @param {Object} [props.feedback] - Feedback object { error: string, success: string }
 * @param {Function} [props.onDismissFeedback] - Callback () => void to dismiss error feedback
 * @param {string} [props.className]
 */
export function VerificationChecklist({
  tasks = [],
  unresolvedQuestions = [],
  findings = [],
  onToggleTask,
  updatingTaskIds = new Set(),
  feedback = { error: '', success: '' },
  onDismissFeedback,
  className,
}) {
  const [filter, setFilter] = useState('all')
  const [dismissedError, setDismissedError] = useState(null)

  const currentError = feedback?.error || ''
  const isDismissed = Boolean(currentError && dismissedError === currentError)

  const handleDismissError = () => {
    setDismissedError(currentError)
    if (typeof onDismissFeedback === 'function') {
      onDismissFeedback()
    }
  }

  const safeTasks = Array.isArray(tasks) ? tasks : []
  const totalTasks = safeTasks.length
  const completedTasks = safeTasks.filter((t) => t.status === 'completed').length
  const pendingTasks = safeTasks.filter((t) => t.status !== 'completed').length

  // Build findings lookup map for efficient O(1) resolution
  const findingsById = useMemo(() => {
    return new Map((findings || []).map((f) => [f.id, f]))
  }, [findings])

  // Filter tasks based on selected filter
  const filteredTasks = useMemo(() => {
    const list = Array.isArray(tasks) ? tasks : []
    if (filter === 'pending') {
      return list.filter((t) => t.status !== 'completed')
    }
    if (filter === 'completed') {
      return list.filter((t) => t.status === 'completed')
    }
    return list
  }, [tasks, filter])

  const filterOptions = [
    { id: 'all', label: 'All Tasks', count: totalTasks, icon: ListChecks },
    { id: 'pending', label: 'Pending', count: pendingTasks, icon: Clock },
    { id: 'completed', label: 'Completed', count: completedTasks, icon: CheckCircle2 },
  ]

  return (
    <div className={cn('space-y-5 text-left', className)}>
      {/* Inline Feedback Banner (e.g. on status update error) */}
      {currentError && !isDismissed && (
        <div className="p-3.5 rounded-xl bg-[#EF233C]/10 border border-[#EF233C]/20 text-[#D90429] text-xs flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <AlertCircle className="size-4 shrink-0" />
            <span className="break-words">{currentError}</span>
          </div>
          <button
            type="button"
            onClick={handleDismissError}
            className="text-[#D90429] hover:text-[#2B2D42] cursor-pointer shrink-0 p-0.5 rounded transition-colors"
            aria-label="Dismiss error message"
            title="Dismiss error message"
          >
            <X className="size-3.5" />
          </button>
        </div>
      )}

      {/* Progress Card */}
      {totalTasks > 0 && (
        <VerificationProgress total={totalTasks} completed={completedTasks} />
      )}

      {/* Filter Tabs & Task Counter */}
      {totalTasks > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <div className="flex flex-wrap items-center gap-2">
            {filterOptions.map((opt) => {
              const Icon = opt.icon
              const isSelected = filter === opt.id

              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setFilter(opt.id)}
                  className={cn(
                    'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer border',
                    isSelected
                      ? 'bg-[#2B2D42] text-[#EDF2F4] border-[#2B2D42] shadow-neu-pressed'
                      : 'bg-white/80 text-[#8D99AE] border-white/60 hover:text-[#2B2D42] hover:bg-white shadow-xs'
                  )}
                  title={`Filter by ${opt.label} (${opt.count})`}
                >
                  <Icon className="size-3.5 shrink-0" />
                  <span>{opt.label}</span>
                  <span
                    className={cn(
                      'ml-0.5 px-1.5 py-0.2 rounded-md text-[10px] font-mono font-bold',
                      isSelected
                        ? 'bg-white/20 text-[#EDF2F4]'
                        : 'bg-slate-100 text-[#2B2D42]'
                    )}
                  >
                    {opt.count}
                  </span>
                </button>
              )
            })}
          </div>

          <span className="text-xs text-[#8D99AE] font-medium">
            Showing {filteredTasks.length} of {totalTasks} task{totalTasks === 1 ? '' : 's'}
          </span>
        </div>
      )}

      {/* Checklist Tasks List */}
      {totalTasks > 0 ? (
        filteredTasks.length > 0 ? (
          <div className="space-y-2.5">
            {filteredTasks.map((task, idx) => {
              const parentFinding = task.finding_id
                ? findingsById.get(task.finding_id)
                : null
              const isUpdating =
                updatingTaskIds instanceof Set
                  ? updatingTaskIds.has(task.id)
                  : Boolean(updatingTaskIds?.[task.id])

              return (
                <VerificationTaskItem
                  key={task.id || `task-${idx}`}
                  task={task}
                  finding={parentFinding}
                  onToggle={onToggleTask}
                  isUpdating={isUpdating}
                />
              )
            })}
          </div>
        ) : (
          /* Filter Empty State */
          <GlassCard className="p-8 text-center space-y-3">
            <div className="size-10 rounded-xl bg-slate-100 text-[#8D99AE] flex items-center justify-center mx-auto border border-slate-200">
              <Filter className="size-5" />
            </div>
            <div className="max-w-md mx-auto space-y-1">
              <h4 className="font-heading font-bold text-sm text-[#2B2D42]">
                No {filter} verification tasks
              </h4>
              <p className="text-xs text-[#8D99AE]">
                {filter === 'completed'
                  ? 'No tasks have been marked as completed yet.'
                  : filter === 'pending'
                  ? 'All verification tasks are currently completed!'
                  : 'No tasks match the active filter.'}
              </p>
            </div>
            <div className="pt-1">
              <NeuButton
                variant="secondary"
                size="sm"
                onClick={() => setFilter('all')}
              >
                View All Tasks ({totalTasks})
              </NeuButton>
            </div>
          </GlassCard>
        )
      ) : (
        /* Zero Tasks Empty State */
        <GlassCard className="p-8 text-center space-y-4">
          <div className="size-12 rounded-xl bg-emerald-500/10 text-emerald-600 flex items-center justify-center mx-auto border border-emerald-500/20">
            <CheckCircle2 className="size-6" />
          </div>
          <div className="max-w-md mx-auto space-y-1.5">
            <h3 className="font-heading font-bold text-base text-[#2B2D42]">
              No Verification Tasks Generated
            </h3>
            <p className="text-xs text-[#8D99AE] leading-relaxed">
              The AI analysis did not identify any actionable follow-up checklist tasks for this investigation.
            </p>
          </div>
        </GlassCard>
      )}

      {/* Unresolved Questions Section (Separate Read-Only Section) */}
      <UnresolvedQuestionsList questions={unresolvedQuestions} />
    </div>
  )
}
