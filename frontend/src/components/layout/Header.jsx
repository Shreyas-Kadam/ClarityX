import { Menu, Plus, Activity } from 'lucide-react'
import { Link } from 'react-router-dom'
import { NeuButton } from '@/components/common/NeuButton'

export function Header({ onMenuClick, title }) {
  return (
    <header className="sticky top-0 z-20 w-full h-16 border-b border-[#8D99AE]/20 glass-panel flex items-center justify-between px-4 sm:px-8">
      {/* Left: Mobile trigger & Page Title */}
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="lg:hidden p-2 rounded-xl neu-interactive text-[#2B2D42]"
          aria-label="Open navigation menu"
        >
          <Menu className="size-5" />
        </button>

        <div>
          <h2 className="text-base sm:text-lg font-bold text-[#2B2D42] tracking-tight">
            {title || 'Information Gap Detection'}
          </h2>
        </div>
      </div>

      {/* Right: Status Pill & New Research CTA */}
      <div className="flex items-center gap-3">
        <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium text-[#2B2D42] bg-white/70 border border-white/80 shadow-xs">
          <Activity className="size-3.5 text-[#EF233C]" />
          <span>Backend: <strong className="text-emerald-700 font-semibold">Active</strong></span>
        </div>

        <Link to="/new">
          <NeuButton variant="cta" size="sm" icon={Plus}>
            <span className="hidden sm:inline">New Research</span>
            <span className="sm:hidden">New</span>
          </NeuButton>
        </Link>
      </div>
    </header>
  )
}
