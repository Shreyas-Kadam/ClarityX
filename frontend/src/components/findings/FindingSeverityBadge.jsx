import { AlertCircle, AlertTriangle, Info } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * FindingSeverityBadge Component
 *
 * Displays a styled severity pill for ClarityX gap findings:
 * 'high', 'medium', 'low'.
 *
 * @param {Object} props
 * @param {string} props.severity - 'high' | 'medium' | 'low'
 * @param {string} [props.className]
 */
export function FindingSeverityBadge({ severity, className }) {
  const normalized = (severity || '').toLowerCase().trim()

  const config = {
    high: {
      label: 'High',
      icon: AlertCircle,
      style: 'bg-[#EF233C]/10 text-[#D90429] border-[#EF233C]/25 font-bold',
    },
    medium: {
      label: 'Medium',
      icon: AlertTriangle,
      style: 'bg-amber-50 text-amber-700 border-amber-200/80 font-semibold',
    },
    low: {
      label: 'Low',
      icon: Info,
      style: 'bg-slate-100 text-slate-600 border-slate-200 font-medium',
    },
  }

  const current = config[normalized] || {
    label: severity ? severity.charAt(0).toUpperCase() + severity.slice(1) : 'Medium',
    icon: Info,
    style: 'bg-slate-100 text-slate-600 border-slate-200 font-medium',
  }
  const Icon = current.icon

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border shadow-xs',
        current.style,
        className
      )}
      title={`Severity: ${current.label}`}
    >
      <Icon className="size-3 shrink-0" />
      {current.label}
    </span>
  )
}

