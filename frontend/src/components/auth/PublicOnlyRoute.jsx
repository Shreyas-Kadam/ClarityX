import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Sparkles, Loader2 } from 'lucide-react'
import { useAuth } from '@/context/useAuth'

export function PublicOnlyRoute() {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="min-h-screen w-full bg-[#EDF2F4] flex flex-col items-center justify-center p-4">
        <div className="flex flex-col items-center gap-4 p-8 rounded-2xl glass-panel neu-raised max-w-sm w-full text-center">
          <div className="size-12 rounded-xl bg-gradient-to-br from-[#EF233C] to-[#D90429] flex items-center justify-center shadow-lg shadow-[#D90429]/30 animate-pulse">
            <Sparkles className="size-6 text-white" />
          </div>
          <div>
            <h3 className="font-heading font-bold text-lg text-[#2B2D42]">
              ClarityX
            </h3>
            <p className="text-xs text-[#8D99AE] mt-0.5">
              Restoring session...
            </p>
          </div>
          <Loader2 className="size-5 text-[#EF233C] animate-spin mt-2" />
        </div>
      </div>
    )
  }

  if (isAuthenticated) {
    const fromPath = location.state?.from?.pathname || '/'
    return <Navigate to={fromPath} replace />
  }

  return <Outlet />
}
