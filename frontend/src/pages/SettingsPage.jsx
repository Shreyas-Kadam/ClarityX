import { useState } from 'react'
import {
  User,
  LogOut,
  RefreshCw,
  Copy,
  Check,
} from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { NeuInput } from '@/components/common/NeuInput'
import { useAuth } from '@/context/useAuth'
import { formatTimestamp } from '@/lib/formatters'

export function SettingsPage() {
  const { user, profile, logout, refreshProfile, profileLoading } = useAuth()
  const [copied, setCopied] = useState(false)

  const userId = profile?.id || user?.id || ''
  const fullName = profile?.full_name || user?.user_metadata?.full_name || ''
  const email = profile?.email || user?.email || ''
  const memberSinceFormatted = formatTimestamp(profile?.created_at || user?.created_at)

  const handleCopyId = () => {
    if (userId) {
      navigator.clipboard.writeText(userId)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6 pb-12">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold font-heading text-[#2B2D42] tracking-tight">
          Account Settings
        </h1>
        <p className="text-sm text-[#8D99AE] mt-1">
          Manage your personal profile and account session.
        </p>
      </div>

      {/* User Account Card */}
      <GlassCard className="p-6 sm:p-8 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-5 border-b border-[#8D99AE]/15">
          <div className="flex items-center gap-3">
            <div className="size-11 rounded-xl bg-[#2B2D42] flex items-center justify-center text-white neu-dark-raised shrink-0">
              <User className="size-5 text-[#EDF2F4]" />
            </div>
            <div>
              <h2 className="font-heading font-semibold text-lg text-[#2B2D42]">
                User Profile
              </h2>
              <p className="text-xs text-[#8D99AE]">
                Active account credentials and session
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
              title="Reload profile details from backend"
            >
              {profileLoading ? 'Syncing...' : 'Sync Profile'}
            </NeuButton>
            <NeuButton
              variant="destructive"
              size="sm"
              onClick={() => logout()}
              icon={LogOut}
              title="Sign out of your account"
            >
              Sign Out
            </NeuButton>
          </div>
        </div>

        <div className="space-y-4">
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
                title="Copy User ID to clipboard"
                icon={copied ? Check : Copy}
              >
                {copied ? 'Copied' : 'Copy'}
              </NeuButton>
            </div>
          </div>

          {memberSinceFormatted && (
            <div className="text-xs text-[#8D99AE] pt-1 border-t border-[#8D99AE]/10">
              Member since: {memberSinceFormatted}
            </div>
          )}
        </div>
      </GlassCard>
    </div>
  )
}
