import { cn } from '@/lib/utils'

/**
 * NeuButton Component
 *
 * Tactile neumorphic button providing gentle depth, subtle dual-direction
 * shadows, and smooth hover/active pressed states.
 */
export function NeuButton({
  children,
  className,
  variant = 'default',
  size = 'default',
  disabled = false,
  type = 'button',
  icon: Icon,
  ...props
}) {
  const variantStyles = {
    // Primary Call-To-Action in #D90429
    cta: 'neu-btn-cta font-semibold',
    // Default soft raised neumorphic button on #EDF2F4
    default:
      'neu-interactive text-[#2B2D42] border border-white/60 font-medium',
    // Dark neumorphic button on #2B2D42
    dark: 'neu-dark-interactive text-[#EDF2F4] border border-[#8D99AE]/20 font-medium',
    // Secondary subtle
    secondary:
      'bg-white/50 backdrop-blur-sm border border-white/70 text-[#2B2D42] hover:bg-white/80 active:translate-y-px',
    // Destructive
    destructive:
      'bg-white text-[#D90429] border border-[#EF233C]/30 hover:bg-[#EF233C]/10',
    // Ghost
    ghost:
      'bg-transparent text-[#8D99AE] hover:text-[#2B2D42] hover:bg-white/40',
  }

  const sizeStyles = {
    sm: 'h-8 px-3 text-xs rounded-xl gap-1.5',
    default: 'h-10 px-4 text-sm rounded-xl gap-2',
    lg: 'h-12 px-6 text-base rounded-2xl gap-2.5',
    icon: 'size-10 rounded-xl justify-center',
  }

  return (
    <button
      type={type}
      disabled={disabled}
      className={cn(
        'inline-flex items-center justify-center font-sans select-none cursor-pointer disabled:opacity-45 disabled:pointer-events-none disabled:cursor-not-allowed',
        variantStyles[variant] || variantStyles.default,
        sizeStyles[size] || sizeStyles.default,
        className
      )}
      {...props}
    >
      {Icon && <Icon className="size-4 shrink-0" />}
      {children}
    </button>
  )
}

