import { HelpCircle, Clock, AlertTriangle, ShieldAlert } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * FindingCategoryBadge Component
 *
 * Displays a styled category pill for the four ClarityX information gap categories:
 * 'missing', 'outdated', 'conflicting', 'unverified'.
 *
 * @param {Object} props
 * @param {string} props.category - 'missing' | 'outdated' | 'conflicting' | 'unverified'
 * @param {string} [props.className]
 */
export function FindingCategoryBadge({ category, className }) {
  const normalized = (category || '').toLowerCase().trim()

  const config = {
    missing: {
      label: 'Missing',
      icon: HelpCircle,
      style: 'bg-purple-50 text-purple-700 border-purple-200/80',
    },
    outdated: {
      label: 'Outdated',
      icon: Clock,
      style: 'bg-amber-50 text-amber-700 border-amber-200/80',
    },
    conflicting: {
      label: 'Conflicting',
      icon: AlertTriangle,
      style: 'bg-rose-50 text-rose-700 border-rose-200/80',
    },
    unverified: {
      label: 'Unverified',
      icon: ShieldAlert,
      style: 'bg-blue-50 text-blue-700 border-blue-200/80',
    },
  }

  const current = config[normalized] || {
    label: category ? category.charAt(0).toUpperCase() + category.slice(1) : 'Information Gap',
    icon: HelpCircle,
    style: 'bg-slate-100 text-slate-700 border-slate-200',
  }
  const Icon = current.icon

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border shadow-xs',
        current.style,
        className
      )}
      title={`Category: ${current.label}`}
    >
      <Icon className="size-3.5 shrink-0" />
      {current.label}
    </span>
  )
}

