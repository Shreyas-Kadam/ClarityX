import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  Compass,
  ArrowRight,
  Sparkles,
  FileSearch,
  CheckCircle2,
  Clock,
  Layers,
  AlertCircle,
  RefreshCw,
  Plus,
} from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { StatusBadge } from '@/components/common/StatusBadge'
import { getResearchSessions } from '@/services/researchService'

export function DashboardPage() {
  const [sessions, setSessions] = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [errorMsg, setErrorMsg] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let isCancelled = false

    async function loadData() {
      try {
        setErrorMsg('')
        const response = await getResearchSessions({ limit: 5 })
        if (isCancelled) return

        if (response?.data?.research_sessions) {
          setSessions(response.data.research_sessions)
          setTotalCount(response.data.total ?? response.data.research_sessions.length)
        } else {
          setSessions([])
          setTotalCount(0)
        }
      } catch (err) {
        if (isCancelled) return
        setErrorMsg(err.message || 'Failed to retrieve research sessions from the backend.')
        setSessions([])
        setTotalCount(0)
      } finally {
        if (!isCancelled) {
          setLoading(false)
        }
      }
    }

    loadData()

    return () => {
      isCancelled = true
    }
  }, [refreshKey])

  const handleRetry = () => {
    setLoading(true)
    setRefreshKey((prev) => prev + 1)
  }

  const completedCount = sessions.filter((s) => s.status === 'completed').length
  const processingCount = sessions.filter((s) => s.status === 'processing').length
  const pendingCount = sessions.filter((s) => s.status === 'pending').length

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Hero / Welcome Banner */}
      <div className="relative overflow-hidden rounded-3xl p-6 sm:p-10 neu-raised border border-white/60">
        <div className="absolute top-0 right-0 -mt-12 -mr-12 w-96 h-96 bg-gradient-to-br from-[#EF233C]/10 via-[#D90429]/5 to-transparent rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-2xl space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-white/70 border border-white/80 shadow-xs text-[#D90429]">
            <Sparkles className="size-3.5 text-[#EF233C]" />
            Digital Dark Spot Detection
          </div>

          <h2 className="text-2xl sm:text-4xl font-extrabold text-[#2B2D42] tracking-tight leading-tight">
            Don&apos;t just discover what exists.
            <br />
            <span className="text-[#D90429]">Expose what&apos;s missing.</span>
          </h2>

          <p className="text-sm sm:text-base text-[#8D99AE] leading-relaxed">
            ClarityX analyses multi-source information to detect <strong className="text-[#2B2D42]">missing facts</strong>, <strong className="text-[#2B2D42]">outdated claims</strong>, <strong className="text-[#2B2D42]">conflicting data</strong>, and <strong className="text-[#2B2D42]">unverified statements</strong> across your research domain.
          </p>

          <div className="pt-2 flex flex-wrap items-center gap-3">
            <Link to="/new">
              <NeuButton variant="cta" size="lg" icon={Compass}>
                Start New Investigation
              </NeuButton>
            </Link>
            <Link to="/history">
              <NeuButton variant="default" size="lg" icon={FileSearch}>
                View History
              </NeuButton>
            </Link>
          </div>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <GlassCard className="p-5 flex items-center justify-between">
          <div className="space-y-1">
            <span className="text-xs font-semibold text-[#8D99AE] uppercase tracking-wider">
              Total Sessions
            </span>
            <div className="text-2xl sm:text-3xl font-extrabold text-[#2B2D42]">
              {loading ? '—' : totalCount}
            </div>
          </div>
          <div className="size-11 rounded-2xl bg-[#2B2D42] flex items-center justify-center text-white neu-dark-raised">
            <Layers className="size-5 text-[#EDF2F4]" />
          </div>
        </GlassCard>

        <GlassCard className="p-5 flex items-center justify-between">
          <div className="space-y-1">
            <span className="text-xs font-semibold text-[#8D99AE] uppercase tracking-wider">
              Completed
            </span>
            <div className="text-2xl sm:text-3xl font-extrabold text-emerald-600">
              {loading ? '—' : completedCount}
            </div>
          </div>
          <div className="size-11 rounded-2xl bg-emerald-500/10 flex items-center justify-center text-emerald-600 border border-emerald-500/20">
            <CheckCircle2 className="size-5" />
          </div>
        </GlassCard>

        <GlassCard className="p-5 flex items-center justify-between">
          <div className="space-y-1">
            <span className="text-xs font-semibold text-[#8D99AE] uppercase tracking-wider">
              Processing
            </span>
            <div className="text-2xl sm:text-3xl font-extrabold text-amber-600">
              {loading ? '—' : processingCount}
            </div>
          </div>
          <div className="size-11 rounded-2xl bg-amber-500/10 flex items-center justify-center text-amber-600 border border-amber-500/20">
            <Clock className="size-5" />
          </div>
        </GlassCard>

        <GlassCard className="p-5 flex items-center justify-between">
          <div className="space-y-1">
            <span className="text-xs font-semibold text-[#8D99AE] uppercase tracking-wider">
              Pending
            </span>
            <div className="text-2xl sm:text-3xl font-extrabold text-[#8D99AE]">
              {loading ? '—' : pendingCount}
            </div>
          </div>
          <div className="size-11 rounded-2xl bg-[#8D99AE]/15 flex items-center justify-center text-[#2B2D42]">
            <Clock className="size-5" />
          </div>
        </GlassCard>
      </div>

      {/* Recent Investigations Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-[#2B2D42] tracking-tight">
              Recent Investigations
            </h3>
            <p className="text-xs text-[#8D99AE]">
              Latest research sessions from your database
            </p>
          </div>

          <div className="flex items-center gap-2">
            <NeuButton
              variant="ghost"
              size="sm"
              onClick={handleRetry}
              disabled={loading}
              icon={RefreshCw}
            >
              Refresh
            </NeuButton>
            <Link to="/history">
              <NeuButton variant="default" size="sm" icon={ArrowRight}>
                View All
              </NeuButton>
            </Link>
          </div>
        </div>

        {/* Error State */}
        {errorMsg && (
          <GlassCard className="p-6 border-l-4 border-l-[#EF233C]">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="size-5 text-[#EF233C] shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-semibold text-sm text-[#2B2D42]">
                    Unable to load research sessions
                  </h4>
                  <p className="text-xs text-[#8D99AE] mt-1">{errorMsg}</p>
                </div>
              </div>
              <NeuButton variant="secondary" size="sm" onClick={handleRetry}>
                Retry
              </NeuButton>
            </div>
          </GlassCard>
        )}

        {/* Loading State */}
        {loading && (
          <GlassCard className="p-8 text-center space-y-3">
            <div className="size-8 rounded-full border-2 border-[#EF233C] border-t-transparent animate-spin mx-auto" />
            <p className="text-xs font-medium text-[#8D99AE]">
              Loading research sessions from database...
            </p>
          </GlassCard>
        )}

        {/* Empty State */}
        {!loading && !errorMsg && sessions.length === 0 && (
          <GlassCard className="p-12 text-center space-y-4">
            <div className="size-16 rounded-2xl bg-[#8D99AE]/10 text-[#8D99AE] flex items-center justify-center mx-auto border border-[#8D99AE]/20">
              <Layers className="size-8" />
            </div>
            <div className="max-w-md mx-auto space-y-1">
              <h4 className="font-heading font-bold text-base text-[#2B2D42]">
                No research sessions yet
              </h4>
              <p className="text-xs text-[#8D99AE]">
                You haven&apos;t started any research investigations yet. Formulate a research question to detect information gaps.
              </p>
            </div>
            <div className="pt-2">
              <Link to="/new">
                <NeuButton variant="cta" size="default" icon={Plus}>
                  Create First Investigation
                </NeuButton>
              </Link>
            </div>
          </GlassCard>
        )}

        {/* Sessions List */}
        {!loading && !errorMsg && sessions.length > 0 && (
          <div className="space-y-3">
            {sessions.map((session) => (
              <GlassCard
                key={session.id}
                className="p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="space-y-1.5 max-w-3xl">
                    <div className="flex items-center gap-2.5">
                      <StatusBadge status={session.status} />
                      <span className="text-[11px] text-[#8D99AE] font-mono">
                        {new Date(session.created_at).toLocaleString()}
                      </span>
                    </div>

                    <h4 className="font-heading font-semibold text-base text-[#2B2D42] line-clamp-2">
                      {session.research_goal}
                    </h4>

                    {session.summary && (
                      <p className="text-xs text-[#8D99AE] line-clamp-2">
                        {session.summary}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                    <Link to={`/research/${session.id}`}>
                      <NeuButton variant="secondary" size="sm" icon={ArrowRight}>
                        Open Details
                      </NeuButton>
                    </Link>
                  </div>
                </div>
              </GlassCard>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
