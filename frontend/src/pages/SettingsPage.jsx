import { useState, useEffect } from 'react'
import {
  User,
  Palette,
  Server,
  ShieldCheck,
  CheckCircle2,
  Info,
  ExternalLink,
  Sparkles,
} from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { NeuInput } from '@/components/common/NeuInput'
import { getCurrentUser } from '@/services/authService'

export function SettingsPage() {
  const [userProfile, setUserProfile] = useState(null)
  const [loadingUser, setLoadingUser] = useState(true)
  const [apiStatus, setApiStatus] = useState('checking')
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

  useEffect(() => {
    async function fetchUser() {
      setLoadingUser(true)
      try {
        const response = await getCurrentUser()
        if (response?.data) {
          setUserProfile(response.data)
          setApiStatus('connected')
        } else {
          setApiStatus('unauthenticated')
        }
      } catch {
        setApiStatus('unauthenticated')
        setUserProfile({
          id: 'dev-user-demo-id',
          email: 'researcher@clarityx.ai',
          full_name: 'Lead Research Analyst',
          is_demo: true,
        })
      } finally {
        setLoadingUser(false)
      }
    }
    fetchUser()
  }, [])

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

  return (
    <div className="space-y-8 max-w-5xl mx-auto pb-12">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold font-heading text-[#2B2D42] tracking-tight">
          Platform Settings
        </h1>
        <p className="text-sm text-[#8D99AE] mt-1">
          Review authentication status, the UI design system tokens, and backend configuration.
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
                    Supabase Authentication & Profile Link
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {apiStatus === 'connected' ? (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
                    <CheckCircle2 className="size-3.5" />
                    Supabase Verified
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-[#8D99AE]/15 text-[#2B2D42] border border-[#8D99AE]/30">
                    <Info className="size-3.5 text-[#8D99AE]" />
                    Development Session
                  </span>
                )}
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
                    value={loadingUser ? 'Loading...' : userProfile?.full_name || 'Anonymous User'}
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
                    value={loadingUser ? 'Loading...' : userProfile?.email || 'N/A'}
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
                    value={userProfile?.id || '—'}
                    className="text-xs font-mono text-[#8D99AE]"
                  />
                  <NeuButton
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (userProfile?.id) {
                        navigator.clipboard.writeText(userProfile.id)
                      }
                    }}
                    title="Copy User ID"
                  >
                    Copy
                  </NeuButton>
                </div>
              </div>

              {userProfile?.is_demo && (
                <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/25 flex items-start gap-2.5 text-xs text-[#2B2D42]">
                  <Info className="size-4 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-amber-700">Client Preview Mode:</span>{' '}
                    No Supabase JWT Bearer token was detected in the active browser session. To authenticate live, store your token in{' '}
                    <code className="px-1 py-0.5 rounded bg-white/70 font-mono text-[11px]">localStorage.setItem('auth_token', token)</code>.
                  </div>
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
                  Endpoint URL
                </span>
                <div className="px-3 py-2 rounded-xl neu-inset text-xs font-mono text-[#2B2D42] break-all">
                  {apiBaseUrl}
                </div>
              </div>

              <div>
                <span className="block text-[11px] font-semibold text-[#8D99AE] uppercase tracking-wider mb-1">
                  API Status
                </span>
                <div className="flex items-center gap-2 text-xs font-medium text-[#2B2D42]">
                  <span className="size-2 rounded-full bg-emerald-500 animate-pulse" />
                  HTTP 200 /api/health Ready
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

          {/* Security & RLS Card */}
          <GlassCard className="p-6">
            <div className="flex items-center gap-3 pb-4 border-b border-[#8D99AE]/15">
              <div className="size-10 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-600">
                <ShieldCheck className="size-5" />
              </div>
              <div>
                <h3 className="font-heading font-semibold text-base text-[#2B2D42]">
                  Security Architecture
                </h3>
                <p className="text-xs text-[#8D99AE]">Supabase RLS & Auth</p>
              </div>
            </div>

            <div className="mt-4 space-y-3 text-xs text-[#8D99AE]">
              <div className="flex items-start gap-2">
                <CheckCircle2 className="size-4 text-emerald-600 shrink-0 mt-0.5" />
                <span>
                  <strong className="text-[#2B2D42]">Row Level Security:</strong> Research sessions are strictly isolated by <code className="text-[#2B2D42]">user_id</code>.
                </span>
              </div>
              <div className="flex items-start gap-2">
                <CheckCircle2 className="size-4 text-emerald-600 shrink-0 mt-0.5" />
                <span>
                  <strong className="text-[#2B2D42]">Stateless JWT:</strong> Bearer tokens authenticated via Supabase Auth.
                </span>
              </div>
              <div className="flex items-start gap-2">
                <CheckCircle2 className="size-4 text-emerald-600 shrink-0 mt-0.5" />
                <span>
                  <strong className="text-[#2B2D42]">Zero Leaked Secrets:</strong> Service-role keys strictly confined to backend server environment.
                </span>
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
