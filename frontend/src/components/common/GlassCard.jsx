import { cn } from '@/lib/utils'

/**
 * GlassCard Component
 *
 * Combines translucent glassmorphic surfaces with delicate borders
 * and soft depth shadows.
 */
export function GlassCard({
  children,
  className,
  variant = 'default',
  hover = false,
  ...props
}) {
  const variantStyles = {
    default: 'glass-panel',
    subtle: 'glass-card',
    dark: 'glass-panel-dark text-[#EDF2F4]',
  }

  return (
    <div
      className={cn(
        'rounded-2xl p-6 transition-all duration-200',
        variantStyles[variant] || variantStyles.default,
        hover && 'hover:shadow-xl hover:-translate-y-0.5',
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}

