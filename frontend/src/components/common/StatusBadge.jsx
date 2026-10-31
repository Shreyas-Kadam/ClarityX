import { CheckCircle2, Clock, AlertCircle, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * StatusBadge Component
 *
 * Visual status pill supporting ClarityX research lifecycle states:
 * 'completed', 'processing', 'pending', 'failed'.
 */
export function StatusBadge({ status, className }) {
  const normalized = (status || 'pending').toLowerCase()

  const config = {
    completed: {
      label: 'Completed',
      icon: CheckCircle2,
      style: 'bg-emerald-50 text-emerald-700 border-emerald-200/80',
    },
    processing: {
      label: 'Processing',
      icon: RefreshCw,
      style: 'bg-amber-50 text-amber-700 border-amber-200/80 animate-pulse',
    },
    pending: {
      label: 'Pending',
      icon: Clock,
      style: 'bg-slate-100 text-[#8D99AE] border-slate-200',
    },
    failed: {
      label: 'Failed',
      icon: AlertCircle,
      style: 'bg-[#EF233C]/10 text-[#D90429] border-[#EF233C]/20',
    },
  }

  const current = config[normalized] || config.pending
  const Icon = current.icon

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border shadow-xs',
        current.style,
        className
      )}
    >
      <Icon className="size-3.5 shrink-0" />
      {current.label}
    </span>
  )
}

