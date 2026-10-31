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
  Search,
  AlertTriangle,
} from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { StatusBadge } from '@/components/common/StatusBadge'
import { getResearchSessions } from '@/services/researchService'

export function DashboardPage() {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [isLiveBackend, setIsLiveBackend] = useState(false)

  useEffect(() => {
    async function loadData() {
      try {
        const response = await getResearchSessions({ limit: 5 })
        if (response?.data?.research_sessions) {
          setSessions(response.data.research_sessions)
          setIsLiveBackend(true)
        }
      } catch {
        // Fallback to sample visual development data if backend has no active session yet
        setIsLiveBackend(false)
        setSessions([
          {
            id: 'sample-1',
            research_goal: 'Autonomous driving regulatory standards and safety gaps across EU & US',
            status: 'completed',
            summary: 'Analysis completed. Identified 3 conflicting statements on sensor redundancy and 2 unverified claims.',
            created_at: new Date(Date.now() - 3600000 * 2).toISOString(),
            is_sample: true,
          },
          {
            id: 'sample-2',
            research_goal: 'Quantum dot solar cell efficiency reports and commercial longevity claims',
            status: 'processing',
            summary: 'Extracting source specifications and validating experimental benchmarks.',
            created_at: new Date(Date.now() - 3600000 * 8).toISOString(),
            is_sample: true,
          },
          {
            id: 'sample-3',
            research_goal: 'Semiconductor supply chain geographic bottlenecks for advanced nodes (sub-3nm)',
            status: 'pending',
            summary: 'Awaiting source ingestion and cross-reference verification.',
            created_at: new Date(Date.now() - 3600000 * 24).toISOString(),
            is_sample: true,
          },
        ])
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [])

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Hero / Welcome Banner combining Glassmorphism + Neumorphism */}
      <div className="relative overflow-hidden rounded-3xl p-6 sm:p-10 neu-raised border border-white/60">
        <div className="absolute top-0 right-0 -mt-12 -mr-12 w-96 h-96 bg-gradient-to-br from-[#EF233C]/10 via-[#D90429]/5 to-transparent rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-2xl space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-white/70 border border-white/80 shadow-xs text-[#D90429]">
            <Sparkles className="size-3.5 text-[#EF233C]" />
            Digital Dark Spot Detection
          </div>

          <h2 className="text-2xl sm:text-4xl font-extrabold text-[#2B2D42] tracking-tight leading-tight">
            Don't just discover what exists.
            <br />
            <span className="text-[#D90429]">Expose what's missing.</span>
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

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
        <GlassCard className="flex items-center gap-4">
          <div className="size-12 rounded-2xl neu-inset flex items-center justify-center text-[#2B2D42]">
            <Layers className="size-6 text-[#2B2D42]" />
          </div>
          <div>
            <div className="text-2xl font-bold text-[#2B2D42]">
              {sessions.length}
            </div>
            <div className="text-xs font-medium text-[#8D99AE]">
              Research Sessions
            </div>
          </div>
        </GlassCard>

        <GlassCard className="flex items-center gap-4">
          <div className="size-12 rounded-2xl neu-inset flex items-center justify-center text-emerald-600">
            <CheckCircle2 className="size-6 text-emerald-600" />
          </div>
          <div>
            <div className="text-2xl font-bold text-[#2B2D42]">
              {sessions.filter((s) => s.status === 'completed').length}
            </div>
            <div className="text-xs font-medium text-[#8D99AE]">
              Verified Reports
            </div>
          </div>
        </GlassCard>

        <GlassCard className="flex items-center gap-4">
          <div className="size-12 rounded-2xl neu-inset flex items-center justify-center text-amber-600">
            <Clock className="size-6 text-amber-600" />
          </div>
          <div>
            <div className="text-2xl font-bold text-[#2B2D42]">
              {sessions.filter((s) => s.status === 'pending' || s.status === 'processing').length}
            </div>
            <div className="text-xs font-medium text-[#8D99AE]">
              In Progress
            </div>
          </div>
        </GlassCard>

        <GlassCard className="flex items-center gap-4">
          <div className="size-12 rounded-2xl neu-inset flex items-center justify-center text-[#D90429]">
            <AlertTriangle className="size-6 text-[#D90429]" />
          </div>
          <div>
            <div className="text-2xl font-bold text-[#D90429]">
              4 Categories
            </div>
            <div className="text-xs font-medium text-[#8D99AE]">
              Gap Classifications
            </div>
          </div>
        </GlassCard>
      </div>

      {/* Recent Investigations */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-[#2B2D42] tracking-tight">
              Recent Investigations
            </h3>
            <p className="text-xs text-[#8D99AE]">
              {isLiveBackend ? 'Connected to live database records' : 'Visual development preview (live database synced on session creation)'}
            </p>
          </div>
          <Link
            to="/history"
            className="text-xs font-semibold text-[#D90429] hover:underline flex items-center gap-1"
          >
            All Sessions <ArrowRight className="size-3.5" />
          </Link>
        </div>

        {loading ? (
          <div className="p-8 rounded-2xl neu-raised text-center text-sm text-[#8D99AE]">
            Loading research investigations...
          </div>
        ) : sessions.length === 0 ? (
          <div className="p-10 rounded-2xl neu-raised text-center space-y-4">
            <div className="size-12 rounded-2xl neu-inset mx-auto flex items-center justify-center text-[#8D99AE]">
              <Search className="size-6" />
            </div>
            <div>
              <h4 className="text-base font-bold text-[#2B2D42]">No research sessions yet</h4>
              <p className="text-xs text-[#8D99AE] max-w-sm mx-auto mt-1">
                Start your first investigation to detect missing information, conflicting claims, and verification checklists.
              </p>
            </div>
            <Link to="/new">
              <NeuButton variant="cta" size="sm" icon={Compass}>
                Create Research Session
              </NeuButton>
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {sessions.map((session) => (
              <GlassCard
                key={session.id}
                hover={true}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5"
              >
                <div className="space-y-1.5 flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge status={session.status} />
                    {session.is_sample && (
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-[#8D99AE]/15 text-[#8D99AE]">
                        Sample Preview
                      </span>
                    )}
                    <span className="text-xs text-[#8D99AE]">
                      {new Date(session.created_at).toLocaleDateString(undefined, {
                        month: 'short',
                        day: 'numeric',
                        year: 'numeric',
                      })}
                    </span>
                  </div>
                  <h4 className="text-sm sm:text-base font-bold text-[#2B2D42] truncate">
                    {session.research_goal}
                  </h4>
                  {session.summary && (
                    <p className="text-xs text-[#8D99AE] line-clamp-1">
                      {session.summary}
                    </p>
                  )}
                </div>

                <div className="shrink-0 flex items-center gap-2">
                  <Link to={`/research/${session.id}`}>
                    <NeuButton variant="default" size="sm">
                      Inspect Report
                    </NeuButton>
                  </Link>
                </div>
              </GlassCard>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

