import { Layers, HelpCircle, Clock, AlertTriangle, ShieldAlert } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * FindingsFilter Component
 *
 * Client-side category filter bar for information gap findings.
 * Renders filter pills for All, Missing, Outdated, Conflicting, and Unverified
 * with live count indicators.
 *
 * @param {Object} props
 * @param {string} props.selectedCategory - 'all' | 'missing' | 'outdated' | 'conflicting' | 'unverified'
 * @param {Function} props.onSelectCategory - Callback receiving selected category string
 * @param {Object} [props.counts] - Map of category keys to counts
 * @param {string} [props.className]
 */
export function FindingsFilter({
  selectedCategory = 'all',
  onSelectCategory,
  counts = { all: 0, missing: 0, outdated: 0, conflicting: 0, unverified: 0 },
  className,
}) {
  const options = [
    { id: 'all', label: 'All', icon: Layers },
    { id: 'missing', label: 'Missing', icon: HelpCircle },
    { id: 'outdated', label: 'Outdated', icon: Clock },
    { id: 'conflicting', label: 'Conflicting', icon: AlertTriangle },
    { id: 'unverified', label: 'Unverified', icon: ShieldAlert },
  ]

  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      {options.map((opt) => {
        const Icon = opt.icon
        const isSelected = selectedCategory === opt.id
        const count = counts[opt.id] ?? 0

        return (
          <button
            key={opt.id}
            type="button"
            onClick={() => onSelectCategory && onSelectCategory(opt.id)}
            className={cn(
              'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer border',
              isSelected
                ? 'bg-[#2B2D42] text-[#EDF2F4] border-[#2B2D42] shadow-neu-pressed'
                : 'bg-white/80 text-[#8D99AE] border-white/60 hover:text-[#2B2D42] hover:bg-white shadow-xs'
            )}
            title={`Filter by ${opt.label} gaps (${count})`}
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
              {count}
            </span>
          </button>
        )
      })}
    </div>
  )
}

