import { CheckCircle2, AlertTriangle, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * SourceStatusBadge Component
 *
 * Displays visual badges for source extraction states:
 * 'success', 'partial', 'failed'.
 *
 * @param {Object} props
 * @param {string} props.status - 'success' | 'partial' | 'failed'
 * @param {string} [props.className]
 */
export function SourceStatusBadge({ status, className }) {
  const normalized = (status || 'success').toLowerCase()

  const config = {
    success: {
      label: 'Extracted',
      icon: CheckCircle2,
      style: 'bg-emerald-50 text-emerald-700 border-emerald-200/80',
    },
    partial: {
      label: 'Partial Extraction',
      icon: AlertTriangle,
      style: 'bg-amber-50 text-amber-700 border-amber-200/80',
    },
    failed: {
      label: 'Extraction Failed',
      icon: AlertCircle,
      style: 'bg-[#EF233C]/10 text-[#D90429] border-[#EF233C]/20',
    },
  }

  const current = config[normalized] || config.success
  const Icon = current.icon

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border shadow-xs',
        current.style,
        className
      )}
    >
      <Icon className="size-3.5 shrink-0" />
      {current.label}
    </span>
  )
}

