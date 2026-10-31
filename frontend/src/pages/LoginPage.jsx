import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { Sparkles, Mail, Lock, Eye, EyeOff, AlertCircle, Loader2, ArrowRight } from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { NeuInput } from '@/components/common/NeuInput'
import { useAuth } from '@/context/useAuth'

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { login } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  // Requested destination if redirected from a protected route
  const fromPath = location.state?.from?.pathname || '/'

  const validateForm = () => {
    const trimmedEmail = email.trim()
    if (!trimmedEmail) {
      setErrorMessage('Please enter your email address.')
      return false
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(trimmedEmail)) {
      setErrorMessage('Please enter a valid email address.')
      return false
    }
    if (!password) {
      setErrorMessage('Please enter your password.')
      return false
    }
    return true
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setErrorMessage('')

    if (!validateForm()) return
    if (submitting) return

    setSubmitting(true)
    try {
      const { data, error } = await login(email, password)

      if (error) {
        let msg = error.message
        if (msg.includes('Invalid login credentials')) {
          msg = 'Invalid email or password. Please verify your credentials and try again.'
        } else if (msg.includes('Email not confirmed')) {
          msg = 'Your email address has not been confirmed yet. Please verify your email inbox.'
        }
        setErrorMessage(msg)
        return
      }

      if (data?.session) {
        navigate(fromPath, { replace: true })
      }
    } catch (err) {
      setErrorMessage(err.message || 'Unable to complete sign in. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen w-full bg-[#EDF2F4] flex flex-col justify-center items-center p-4 sm:p-6">
      {/* Background ambient accents */}
      <div className="absolute top-1/4 left-1/4 size-72 rounded-full bg-[#EF233C]/5 blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 size-80 rounded-full bg-[#2B2D42]/5 blur-3xl pointer-events-none" />

      <div className="w-full max-w-md relative z-10 space-y-6">
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center size-14 rounded-2xl bg-gradient-to-br from-[#EF233C] to-[#D90429] shadow-xl shadow-[#D90429]/25 text-white mb-2">
            <Sparkles className="size-7" />
          </div>
          <h1 className="font-heading font-extrabold text-2xl sm:text-3xl text-[#2B2D42] tracking-tight">
            Sign In to ClarityX
          </h1>
          <p className="text-xs sm:text-sm text-[#8D99AE]">
            Digital Dark Spot — AI-Assisted Information Gap Detection
          </p>
        </div>

        {/* Login Card */}
        <GlassCard className="p-6 sm:p-8 neu-raised border border-white/80">
          <form onSubmit={handleSubmit} className="space-y-5" noValidate>
            {/* Error Banner */}
            {errorMessage && (
              <div
                className="p-3.5 rounded-xl bg-[#EF233C]/10 border border-[#EF233C]/30 flex items-start gap-2.5 text-xs text-[#D90429]"
                role="alert"
              >
                <AlertCircle className="size-4 shrink-0 mt-0.5" />
                <span className="font-medium leading-relaxed">{errorMessage}</span>
              </div>
            )}

            {/* Email Field */}
            <div className="space-y-1.5">
              <label
                htmlFor="login-email"
                className="block text-xs font-semibold uppercase tracking-wider text-[#2B2D42]"
              >
                Email Address
              </label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-[#8D99AE] pointer-events-none" />
                <NeuInput
                  id="login-email"
                  type="email"
                  autoComplete="email"
                  required
                  placeholder="analyst@domain.com"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value)
                    if (errorMessage) setErrorMessage('')
                  }}
                  className="pl-10 text-sm"
                  disabled={submitting}
                />
              </div>
            </div>

            {/* Password Field */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label
                  htmlFor="login-password"
                  className="block text-xs font-semibold uppercase tracking-wider text-[#2B2D42]"
                >
                  Password
                </label>
              </div>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-[#8D99AE] pointer-events-none" />
                <NeuInput
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value)
                    if (errorMessage) setErrorMessage('')
                  }}
                  className="pl-10 pr-10 text-sm"
                  disabled={submitting}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-[#8D99AE] hover:text-[#2B2D42] transition-colors p-1"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>

            {/* Submit Button */}
            <NeuButton
              type="submit"
              variant="cta"
              size="lg"
              className="w-full justify-center text-sm font-semibold mt-2"
              disabled={submitting}
            >
              {submitting ? (
                <>
                  <Loader2 className="size-4 mr-2 animate-spin" />
                  Authenticating...
                </>
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight className="size-4 ml-1.5" />
                </>
              )}
            </NeuButton>
          </form>

          {/* Footer Navigation */}
          <div className="mt-6 pt-5 border-t border-[#8D99AE]/15 text-center">
            <p className="text-xs text-[#8D99AE]">
              Don&apos;t have an account yet?{' '}
              <Link
                to="/register"
                state={{ from: location.state?.from }}
                className="font-bold text-[#D90429] hover:underline ml-1"
              >
                Create Account
              </Link>
            </p>
          </div>
        </GlassCard>

        {/* Security Badge */}
        <p className="text-[11px] text-center text-[#8D99AE] font-medium">
          Protected by Supabase Authentication & PostgreSQL Row Level Security
        </p>
      </div>
    </div>
  )
}
