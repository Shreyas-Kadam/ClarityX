import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import {
  Sparkles,
  User,
  Mail,
  Lock,
  Eye,
  EyeOff,
  AlertCircle,
  CheckCircle2,
  Loader2,
  ArrowRight,
} from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { NeuInput } from '@/components/common/NeuInput'
import { useAuth } from '@/context/useAuth'

export function RegisterPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { register } = useAuth()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [confirmationNeeded, setConfirmationNeeded] = useState(false)

  // Requested destination if redirected from a protected route
  const fromPath = location.state?.from?.pathname || '/'

  const validateForm = () => {
    const trimmedName = fullName.trim()
    if (!trimmedName) {
      setErrorMessage('Please enter your full name.')
      return false
    }

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
      setErrorMessage('Please enter a password.')
      return false
    }
    if (password.length < 6) {
      setErrorMessage('Password must be at least 6 characters long.')
      return false
    }

    if (password !== confirmPassword) {
      setErrorMessage('Passwords do not match.')
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
      const { data, error } = await register(email, password, fullName)

      if (error) {
        let msg = error.message
        if (msg.includes('User already registered')) {
          msg = 'An account with this email address already exists. Please log in instead.'
        }
        setErrorMessage(msg)
        return
      }

      // Supabase email-confirmation check:
      // If email confirmation is enabled, data.user is created but data.session is null.
      if (data?.user && !data?.session) {
        setConfirmationNeeded(true)
        return
      }

      // If email confirmation is disabled, user is immediately authenticated with active session
      if (data?.session) {
        navigate(fromPath, { replace: true })
      }
    } catch (err) {
      setErrorMessage(err.message || 'Unable to complete registration. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen w-full bg-[#EDF2F4] flex flex-col justify-center items-center p-4 sm:p-6">
      {/* Background ambient accents */}
      <div className="absolute top-1/4 right-1/4 size-72 rounded-full bg-[#EF233C]/5 blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 left-1/4 size-80 rounded-full bg-[#2B2D42]/5 blur-3xl pointer-events-none" />

      <div className="w-full max-w-md relative z-10 space-y-6">
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center size-14 rounded-2xl bg-gradient-to-br from-[#EF233C] to-[#D90429] shadow-xl shadow-[#D90429]/25 text-white mb-2">
            <Sparkles className="size-7" />
          </div>
          <h1 className="font-heading font-extrabold text-2xl sm:text-3xl text-[#2B2D42] tracking-tight">
            Create ClarityX Account
          </h1>
          <p className="text-xs sm:text-sm text-[#8D99AE]">
            Start detecting digital dark spots and information gaps
          </p>
        </div>

        {/* Registration Card / Email Confirmation View */}
        <GlassCard className="p-6 sm:p-8 neu-raised border border-white/80">
          {confirmationNeeded ? (
            <div className="space-y-5 text-center py-4">
              <div className="size-14 rounded-2xl bg-emerald-500/10 text-emerald-600 flex items-center justify-center mx-auto border border-emerald-500/20">
                <CheckCircle2 className="size-7" />
              </div>
              <div className="space-y-2">
                <h2 className="font-heading font-bold text-xl text-[#2B2D42]">
                  Check Your Email
                </h2>
                <p className="text-xs sm:text-sm text-[#8D99AE] leading-relaxed">
                  We have sent a verification link to <strong className="text-[#2B2D42] font-semibold">{email}</strong>.
                  Please click the link in your email to confirm your account before logging in.
                </p>
              </div>

              <div className="pt-4">
                <Link to="/login">
                  <NeuButton variant="cta" size="default" className="w-full justify-center">
                    Proceed to Sign In
                    <ArrowRight className="size-4 ml-1.5" />
                  </NeuButton>
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
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

              {/* Full Name Field */}
              <div className="space-y-1">
                <label
                  htmlFor="register-name"
                  className="block text-xs font-semibold uppercase tracking-wider text-[#2B2D42]"
                >
                  Full Name
                </label>
                <div className="relative">
                  <User className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-[#8D99AE] pointer-events-none" />
                  <NeuInput
                    id="register-name"
                    type="text"
                    autoComplete="name"
                    required
                    placeholder="Jane Doe"
                    value={fullName}
                    onChange={(e) => {
                      setFullName(e.target.value)
                      if (errorMessage) setErrorMessage('')
                    }}
                    className="pl-10 text-sm"
                    disabled={submitting}
                  />
                </div>
              </div>

              {/* Email Field */}
              <div className="space-y-1">
                <label
                  htmlFor="register-email"
                  className="block text-xs font-semibold uppercase tracking-wider text-[#2B2D42]"
                >
                  Email Address
                </label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-[#8D99AE] pointer-events-none" />
                  <NeuInput
                    id="register-email"
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
              <div className="space-y-1">
                <label
                  htmlFor="register-password"
                  className="block text-xs font-semibold uppercase tracking-wider text-[#2B2D42]"
                >
                  Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-[#8D99AE] pointer-events-none" />
                  <NeuInput
                    id="register-password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    required
                    placeholder="At least 6 characters"
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

              {/* Confirm Password Field */}
              <div className="space-y-1">
                <label
                  htmlFor="register-confirm-password"
                  className="block text-xs font-semibold uppercase tracking-wider text-[#2B2D42]"
                >
                  Confirm Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-[#8D99AE] pointer-events-none" />
                  <NeuInput
                    id="register-confirm-password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    required
                    placeholder="Repeat password"
                    value={confirmPassword}
                    onChange={(e) => {
                      setConfirmPassword(e.target.value)
                      if (errorMessage) setErrorMessage('')
                    }}
                    className="pl-10 text-sm"
                    disabled={submitting}
                  />
                </div>
              </div>

              {/* Submit Button */}
              <NeuButton
                type="submit"
                variant="cta"
                size="lg"
                className="w-full justify-center text-sm font-semibold mt-3"
                disabled={submitting}
              >
                {submitting ? (
                  <>
                    <Loader2 className="size-4 mr-2 animate-spin" />
                    Creating Account...
                  </>
                ) : (
                  <>
                    <span>Create Account</span>
                    <ArrowRight className="size-4 ml-1.5" />
                  </>
                )}
              </NeuButton>
            </form>
          )}

          {/* Footer Navigation */}
          {!confirmationNeeded && (
            <div className="mt-6 pt-5 border-t border-[#8D99AE]/15 text-center">
              <p className="text-xs text-[#8D99AE]">
                Already have an account?{' '}
                <Link
                  to="/login"
                  state={{ from: location.state?.from }}
                  className="font-bold text-[#D90429] hover:underline ml-1"
                >
                  Sign In
                </Link>
              </p>
            </div>
          )}
        </GlassCard>

        {/* Security Notice */}
        <p className="text-[11px] text-center text-[#8D99AE] font-medium">
          Protected by Supabase Authentication & PostgreSQL Row Level Security
        </p>
      </div>
    </div>
  )
}
