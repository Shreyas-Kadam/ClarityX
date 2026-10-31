import { cn } from '@/lib/utils'

/**
 * NeuInput Component
 *
 * Soft inset neumorphic input and textarea controls with smooth dual inner shadows
 * and clear focus states.
 */
export function NeuInput({
  className,
  error = false,
  icon: Icon,
  ...props
}) {
  return (
    <div className="relative w-full">
      {Icon && (
        <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8D99AE] pointer-events-none">
          <Icon className="size-4" />
        </div>
      )}
      <input
        className={cn(
          'w-full h-11 rounded-xl px-4 text-sm text-[#2B2D42] placeholder-[#8D99AE] transition-all outline-none',
          'neu-inset neu-inset-focus',
          Icon && 'pl-10',
          error && 'border border-[#EF233C] ring-2 ring-[#EF233C]/20',
          className
        )}
        {...props}
      />
    </div>
  )
}

export function NeuTextarea({
  className,
  error = false,
  rows = 4,
  ...props
}) {
  return (
    <textarea
      rows={rows}
      className={cn(
        'w-full rounded-2xl p-4 text-sm text-[#2B2D42] placeholder-[#8D99AE] transition-all outline-none resize-y',
        'neu-inset neu-inset-focus',
        error && 'border border-[#EF233C] ring-2 ring-[#EF233C]/20',
        className
      )}
      {...props}
    />
  )
}

