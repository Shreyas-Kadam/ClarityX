import { useState } from 'react'
import {
  User,
  Palette,
  Server,
  Info,
  ExternalLink,
  Sparkles,
  LogOut,
  RefreshCw,
  Copy,
  Check,
} from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { NeuInput } from '@/components/common/NeuInput'
import { useAuth } from '@/context/useAuth'

export function SettingsPage() {
  const { user, profile, logout, refreshProfile, profileLoading } = useAuth()
  const [copied, setCopied] = useState(false)
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

  const colorPalette = [
    {
      name: 'Primary Dark',
      hex: '#2B2D42',
      bgClass: 'bg-[#2B2D42]',
      textClass: 'text-white',
      usage: 'Sidebar, dark headings, contrast text, primary dark surfaces',
    },
    {
      name: 'Secondary / Neutral',
      hex: '#8D99AE',
      bgClass: 'bg-[#8D99AE]',
      textClass: 'text-[#2B2D42]',
      usage: 'Subtext, subtle borders, soft shadows, inactive states',
    },
    {
      name: 'Light / Background',
      hex: '#EDF2F4',
      bgClass: 'bg-[#EDF2F4]',
      textClass: 'text-[#2B2D42]',
      border: true,
      usage: 'Core canvas background, neumorphic base extruded cards & inputs',
    },
    {
      name: 'Accent / Highlight',
      hex: '#EF233C',
      bgClass: 'bg-[#EF233C]',
      textClass: 'text-white',
      usage: 'Warning indicators, focus rings, tag badges, light gradients',
    },
    {
      name: 'Accent Dark / CTA',
      hex: '#D90429',
      bgClass: 'bg-[#D90429]',
      textClass: 'text-white',
      usage: 'Primary buttons, active indicators, high-emphasis interactive CTAs',
    },
  ]

  const userId = profile?.id || user?.id || ''
  const fullName = profile?.full_name || user?.user_metadata?.full_name || ''
  const email = profile?.email || user?.email || ''

  const handleCopyId = () => {
    if (userId) {
      navigator.clipboard.writeText(userId)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="space-y-8 max-w-5xl mx-auto pb-12">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold font-heading text-[#2B2D42] tracking-tight">
          Platform Settings
        </h1>
        <p className="text-sm text-[#8D99AE] mt-1">
          Review authenticated account details, the UI design system tokens, and backend configuration.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (2 cols): Account & Design System */}
        <div className="lg:col-span-2 space-y-6">
          {/* User Account Card */}
          <GlassCard className="p-6">
            <div className="flex items-center justify-between pb-4 border-b border-[#8D99AE]/15">
              <div className="flex items-center gap-3">
                <div className="size-10 rounded-xl bg-[#2B2D42] flex items-center justify-center text-white neu-dark-raised">
                  <User className="size-5 text-[#EDF2F4]" />
                </div>
                <div>
                  <h2 className="font-heading font-semibold text-lg text-[#2B2D42]">
                    User Account
                  </h2>
                  <p className="text-xs text-[#8D99AE]">
                    Authenticated Supabase Session & Profile
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <NeuButton
                  variant="ghost"
                  size="sm"
                  onClick={refreshProfile}
                  disabled={profileLoading}
                  icon={RefreshCw}
                  title="Reload profile from backend"
                >
                  Sync
                </NeuButton>
                <NeuButton
                  variant="destructive"
                  size="sm"
                  onClick={() => logout()}
                  icon={LogOut}
                >
                  Sign Out
                </NeuButton>
              </div>
            </div>

            <div className="mt-6 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[#8D99AE] uppercase tracking-wider mb-1.5">
                    Full Name
                  </label>
                  <NeuInput
                    type="text"
                    readOnly
                    value={fullName || 'Not specified'}
                    className="text-sm font-medium text-[#2B2D42]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[#8D99AE] uppercase tracking-wider mb-1.5">
                    Email Address
                  </label>
                  <NeuInput
                    type="email"
                    readOnly
                    value={email || 'Not available'}
                    className="text-sm font-medium text-[#2B2D42]"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#8D99AE] uppercase tracking-wider mb-1.5">
                  User ID (UUID)
                </label>
                <div className="flex items-center gap-2">
                  <NeuInput
                    type="text"
                    readOnly
                    value={userId || '—'}
                    className="text-xs font-mono text-[#2B2D42]"
                  />
                  <NeuButton
                    variant="ghost"
                    size="sm"
                    onClick={handleCopyId}
                    title="Copy User ID"
                    icon={copied ? Check : Copy}
                  >
                    {copied ? 'Copied' : 'Copy'}
                  </NeuButton>
                </div>
              </div>

              {profile?.created_at && (
                <div className="text-[11px] text-[#8D99AE]">
                  Member since: {new Date(profile.created_at).toLocaleString()}
                </div>
              )}
            </div>
          </GlassCard>

          {/* Design System & Color Palette Card */}
          <GlassCard className="p-6">
            <div className="flex items-center gap-3 pb-4 border-b border-[#8D99AE]/15">
              <div className="size-10 rounded-xl bg-gradient-to-br from-[#EF233C] to-[#D90429] flex items-center justify-center text-white shadow-md shadow-[#D90429]/20">
                <Palette className="size-5" />
              </div>
              <div>
                <h2 className="font-heading font-semibold text-lg text-[#2B2D42]">
                  UI Design System
                </h2>
                <p className="text-xs text-[#8D99AE]">
                  Precision Glassmorphism + Neumorphism 5-Color Spec
                </p>
              </div>
            </div>

            <div className="mt-6 space-y-4">
              <p className="text-xs text-[#8D99AE] leading-relaxed">
                ClarityX blends modern frosted translucent glass layers with tactile neumorphic surfaces (extruded and inset shadows) strictly calibrated around the designated palette.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 pt-2">
                {colorPalette.map((col) => (
                  <div
                    key={col.hex}
                    className="p-3 rounded-xl neu-raised flex flex-col justify-between space-y-3"
                  >
                    <div
                      className={`h-12 w-full rounded-lg ${col.bgClass} ${
                        col.border ? 'border border-[#8D99AE]/30' : ''
                      } flex items-center justify-center font-mono text-xs font-bold ${col.textClass}`}
                    >
                      {col.hex}
                    </div>
                    <div>
                      <div className="text-xs font-bold text-[#2B2D42] truncate">
                        {col.name}
                      </div>
                      <div className="text-[10px] text-[#8D99AE] mt-0.5 line-clamp-2">
                        {col.usage}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Design Technique Tokens */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4">
                <div className="p-4 rounded-xl glass-panel space-y-2">
                  <span className="text-xs font-bold text-[#2B2D42] uppercase tracking-wider flex items-center gap-1.5">
                    <Sparkles className="size-3.5 text-[#EF233C]" />
                    Glassmorphic Surface
                  </span>
                  <p className="text-xs text-[#8D99AE]">
                    Backdrop blur (14px) with subtle high-key white translucent borders and diffuse ambient elevation.
                  </p>
                </div>
                <div className="p-4 rounded-xl neu-raised space-y-2">
                  <span className="text-xs font-bold text-[#2B2D42] uppercase tracking-wider flex items-center gap-1.5">
                    <div className="size-2 rounded-full bg-[#D90429]" />
                    Neumorphic Tactile Surface
                  </span>
                  <p className="text-xs text-[#8D99AE]">
                    Dual-directional soft drop shadows calibrated against the #EDF2F4 base with inset active press-down reactions.
                  </p>
                </div>
              </div>
            </div>
          </GlassCard>
        </div>

        {/* Right Column (1 col): System & Service Info */}
        <div className="space-y-6">
          {/* API Backend Card */}
          <GlassCard className="p-6">
            <div className="flex items-center gap-3 pb-4 border-b border-[#8D99AE]/15">
              <div className="size-10 rounded-xl bg-[#8D99AE]/20 flex items-center justify-center text-[#2B2D42]">
                <Server className="size-5 text-[#2B2D42]" />
              </div>
              <div>
                <h3 className="font-heading font-semibold text-base text-[#2B2D42]">
                  Backend API
                </h3>
                <p className="text-xs text-[#8D99AE]">FastAPI Microservice</p>
              </div>
            </div>

            <div className="mt-5 space-y-4">
              <div>
                <span className="block text-[11px] font-semibold text-[#8D99AE] uppercase tracking-wider mb-1">
                  API Base URL
                </span>
                <div className="px-3 py-2 rounded-xl neu-inset text-xs font-mono text-[#2B2D42] break-all">
                  {apiBaseUrl}
                </div>
              </div>

              <div>
                <span className="block text-[11px] font-semibold text-[#8D99AE] uppercase tracking-wider mb-1">
                  Authentication Method
                </span>
                <div className="text-xs font-medium text-[#2B2D42]">
                  Supabase Auth JWT (Bearer Header)
                </div>
              </div>

              <div className="pt-2">
                <a
                  href={`${apiBaseUrl}/docs`}
                  target="_blank"
                  rel="noreferrer"
                  className="w-full inline-flex"
                >
                  <NeuButton variant="secondary" size="sm" className="w-full justify-center">
                    <ExternalLink className="size-3.5 mr-1.5" />
                    Open Swagger Docs
                  </NeuButton>
                </a>
              </div>
            </div>
          </GlassCard>

          {/* Session Overview Card */}
          <GlassCard className="p-6 space-y-3">
            <h3 className="font-heading font-semibold text-base text-[#2B2D42] flex items-center gap-2">
              <Info className="size-4 text-[#8D99AE]" />
              Session Information
            </h3>
            <div className="space-y-2 text-xs text-[#8D99AE]">
              <div className="flex justify-between py-1 border-b border-[#8D99AE]/10">
                <span>Auth Provider</span>
                <span className="font-semibold text-[#2B2D42]">Supabase Auth</span>
              </div>
              <div className="flex justify-between py-1 border-b border-[#8D99AE]/10">
                <span>Persistence</span>
                <span className="font-semibold text-[#2B2D42]">PostgreSQL (RLS)</span>
              </div>
              <div className="flex justify-between py-1">
                <span>Access Scope</span>
                <span className="font-semibold text-[#2B2D42]">User Sessions Only</span>
              </div>
            </div>
          </GlassCard>

          {/* Platform Version Card */}
          <GlassCard className="p-5 text-center">
            <div className="text-xs font-semibold text-[#8D99AE] uppercase tracking-wider">
              ClarityX Architecture
            </div>
            <div className="font-heading font-bold text-lg text-[#2B2D42] mt-1">
              Phase IV: Frontend Foundation
            </div>
            <div className="text-xs text-[#8D99AE] mt-1">
              Next: Phase V – Source Extraction & Search
            </div>
          </GlassCard>
        </div>
      </div>
    </div>
  )
}
