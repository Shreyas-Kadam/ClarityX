import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  PlusCircle,
  History,
  Settings,
  Sparkles,
  ShieldCheck,
  X,
  ExternalLink,
} from 'lucide-react'
import { cn } from '@/lib/utils'

export function Sidebar({ onClose, isMobile = false }) {
  const navItems = [
    {
      to: '/',
      label: 'Dashboard',
      icon: LayoutDashboard,
      end: true,
    },
    {
      to: '/new',
      label: 'New Research',
      icon: PlusCircle,
    },
    {
      to: '/history',
      label: 'Research History',
      icon: History,
    },
    {
      to: '/settings',
      label: 'Settings',
      icon: Settings,
    },
  ]

  return (
    <aside
      className={cn(
        'flex flex-col h-full w-64 bg-[#2B2D42] text-[#EDF2F4] border-r border-[#8D99AE]/20 select-none z-30',
        'glass-panel-dark'
      )}
    >
      {/* Brand Header */}
      <div className="flex items-center justify-between px-6 py-6 border-b border-[#8D99AE]/15">
        <div className="flex items-center gap-3">
          <div className="size-10 rounded-xl bg-gradient-to-br from-[#EF233C] to-[#D90429] flex items-center justify-center shadow-lg shadow-[#D90429]/30">
            <Sparkles className="size-5 text-white" />
          </div>
          <div>
            <h1 className="font-heading font-bold text-lg tracking-tight text-white flex items-center gap-1.5">
              ClarityX
              <span className="text-[10px] uppercase font-semibold tracking-wider px-1.5 py-0.5 rounded-md bg-[#EF233C]/20 text-[#EF233C] border border-[#EF233C]/30">
                v0.1
              </span>
            </h1>
            <p className="text-xs text-[#8D99AE] font-medium leading-none">
              Gap Detection Platform
            </p>
          </div>
        </div>

        {isMobile && (
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-[#8D99AE] hover:text-white hover:bg-white/10"
            aria-label="Close sidebar"
          >
            <X className="size-5" />
          </button>
        )}
      </div>

      {/* Philosophy Banner */}
      <div className="mx-4 my-4 p-3 rounded-xl bg-[#232537]/80 border border-[#8D99AE]/20 shadow-inner">
        <p className="text-[11px] leading-relaxed text-[#8D99AE]">
          <span className="text-[#EDF2F4] font-medium">Core Principle:</span> Don't just show what was found. Highlight what remains missing.
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 space-y-1.5 overflow-y-auto">
        <div className="px-3 pb-2 text-[11px] font-semibold tracking-wider text-[#8D99AE]/70 uppercase">
          Workspace
        </div>
        {navItems.map((item) => {
          const Icon = item.icon
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={isMobile ? onClose : undefined}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 group',
                  isActive
                    ? 'bg-gradient-to-r from-[#D90429] to-[#EF233C] text-white shadow-md shadow-[#D90429]/30'
                    : 'text-[#8D99AE] hover:text-white hover:bg-white/5 active:bg-white/10'
                )
              }
            >
              <Icon className="size-4 shrink-0 transition-transform group-hover:scale-110" />
              <span>{item.label}</span>
            </NavLink>
          )
        })}
      </nav>

      {/* Bottom Profile / Service Status */}
      <div className="p-4 border-t border-[#8D99AE]/15 space-y-3">
        <div className="p-3 rounded-xl bg-[#232537]/90 border border-[#8D99AE]/20 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="size-8 rounded-lg bg-[#2B2D42] border border-[#8D99AE]/30 flex items-center justify-center text-xs font-bold text-white shadow-sm">
              CX
            </div>
            <div className="overflow-hidden">
              <div className="text-xs font-semibold text-white truncate">
                Research Studio
              </div>
              <div className="text-[10px] text-[#8D99AE] flex items-center gap-1">
                <span className="size-1.5 rounded-full bg-emerald-400"></span>
                FastAPI Connected
              </div>
            </div>
          </div>
          <ShieldCheck className="size-4 text-emerald-400 shrink-0" />
        </div>

        <a
          href="http://localhost:8000/docs"
          target="_blank"
          rel="noreferrer"
          className="flex items-center justify-center gap-1.5 w-full py-2 text-xs font-medium text-[#8D99AE] hover:text-white transition-colors"
        >
          <span>API Documentation</span>
          <ExternalLink className="size-3" />
        </a>
      </div>
    </aside>
  )
}

