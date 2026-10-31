import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  FileSearch,
  Plus,
  RefreshCw,
  Trash2,
  ExternalLink,
  AlertCircle,
  Search,
  Clock,
} from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { StatusBadge } from '@/components/common/StatusBadge'
import { NeuInput } from '@/components/common/NeuInput'
import { getResearchSessions, deleteResearch } from '@/services/researchService'

export function ResearchHistoryPage() {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [errorMsg, setErrorMsg] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [isDeleting, setIsDeleting] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const handleRefresh = () => {
    setLoading(true)
    setRefreshKey((prev) => prev + 1)
  }

  useEffect(() => {
    let isCancelled = false

    async function fetchHistory() {
      try {
        setErrorMsg('')
        const filter = statusFilter === 'all' ? null : statusFilter
        const response = await getResearchSessions({ limit: 50, status: filter })
        if (isCancelled) return

        if (response?.data?.research_sessions) {
          setSessions(response.data.research_sessions)
        } else {
          setSessions([])
        }
      } catch (err) {
        if (isCancelled) return
        setErrorMsg(err.message || 'Unable to fetch research history from backend.')
        setSessions([])
      } finally {
        if (!isCancelled) {
          setLoading(false)
        }
      }
    }

    fetchHistory()

    return () => {
      isCancelled = true
    }
  }, [statusFilter, refreshKey])

  const handleDelete = async (id, e) => {
    e.preventDefault()
    e.stopPropagation()
    if (!window.confirm('Are you sure you want to permanently delete this research session?')) {
      return
    }

    setIsDeleting(id)
    try {
      await deleteResearch(id)
      setSessions((prev) => prev.filter((s) => s.id !== id))
    } catch (err) {
      alert(`Failed to delete session: ${err.message}`)
    } finally {
      setIsDeleting(null)
    }
  }

  const filteredSessions = sessions.filter((s) => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) return true
    const goalMatch = s.research_goal?.toLowerCase().includes(query)
    const summaryMatch = s.summary?.toLowerCase().includes(query)
    return goalMatch || summaryMatch
  })

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-extrabold text-[#2B2D42] tracking-tight">
            Research Investigation History
          </h2>
          <p className="text-sm text-[#8D99AE]">
            Browse, inspect, and manage your stored research reports.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <NeuButton
            variant="default"
            size="sm"
            onClick={handleRefresh}
            disabled={loading}
            icon={RefreshCw}
          >
            Refresh
          </NeuButton>
          <Link to="/new">
            <NeuButton variant="cta" size="sm" icon={Plus}>
              New Investigation
            </NeuButton>
          </Link>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <GlassCard className="p-4 space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          {/* Search Box */}
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-[#8D99AE] pointer-events-none" />
            <NeuInput
              type="text"
              placeholder="Search by topic, keyword, or hypothesis..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 text-sm"
            />
          </div>

          {/* Status Filter Buttons */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0">
            {['all', 'completed', 'processing', 'pending', 'failed'].map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => {
                  setStatusFilter(st)
                  setLoading(true)
                }}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold capitalize transition-all ${
                  statusFilter === st
                    ? 'neu-btn-cta shadow-sm'
                    : 'neu-interactive text-[#8D99AE] hover:text-[#2B2D42]'
                }`}
              >
                {st}
              </button>
            ))}
          </div>
        </div>
      </GlassCard>

      {/* Error State */}
      {errorMsg && (
        <GlassCard className="p-6 border-l-4 border-l-[#EF233C]">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <AlertCircle className="size-5 text-[#EF233C] shrink-0 mt-0.5" />
              <div>
                <h4 className="font-semibold text-sm text-[#2B2D42]">
                  Error loading history
                </h4>
                <p className="text-xs text-[#8D99AE] mt-1">{errorMsg}</p>
              </div>
            </div>
            <NeuButton variant="secondary" size="sm" onClick={handleRefresh}>
              Retry
            </NeuButton>
          </div>
        </GlassCard>
      )}

      {/* Loading State */}
      {loading && (
        <GlassCard className="p-12 text-center space-y-3">
          <div className="size-8 rounded-full border-2 border-[#EF233C] border-t-transparent animate-spin mx-auto" />
          <p className="text-xs font-medium text-[#8D99AE]">
            Fetching investigations from database...
          </p>
        </GlassCard>
      )}

      {/* Empty State */}
      {!loading && !errorMsg && filteredSessions.length === 0 && (
        <GlassCard className="p-12 text-center space-y-4">
          <div className="size-16 rounded-2xl bg-[#8D99AE]/10 text-[#8D99AE] flex items-center justify-center mx-auto border border-[#8D99AE]/20">
            <FileSearch className="size-8" />
          </div>
          <div className="max-w-md mx-auto space-y-1">
            <h3 className="font-heading font-bold text-base text-[#2B2D42]">
              {searchQuery || statusFilter !== 'all'
                ? 'No matching investigations found'
                : 'No research sessions yet'}
            </h3>
            <p className="text-xs text-[#8D99AE]">
              {searchQuery || statusFilter !== 'all'
                ? 'Try broadening your search criteria or resetting the status filter.'
                : 'Formulate your first research question to detect dark spots.'}
            </p>
          </div>
          <div className="pt-2">
            <Link to="/new">
              <NeuButton variant="cta" size="default" icon={Plus}>
                Create New Research Session
              </NeuButton>
            </Link>
          </div>
        </GlassCard>
      )}

      {/* Sessions Grid / Table */}
      {!loading && !errorMsg && filteredSessions.length > 0 && (
        <div className="space-y-3">
          {filteredSessions.map((session) => (
            <GlassCard
              key={session.id}
              className="p-5 transition-all duration-200 hover:shadow-md"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="space-y-2 flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <StatusBadge status={session.status} />
                    <span className="text-[11px] text-[#8D99AE] font-mono flex items-center gap-1">
                      <Clock className="size-3" />
                      {new Date(session.created_at).toLocaleString()}
                    </span>
                    <span className="text-[10px] text-[#8D99AE] font-mono px-2 py-0.5 rounded bg-white/60">
                      ID: {session.id.slice(0, 8)}...
                    </span>
                  </div>

                  <h3 className="font-heading font-semibold text-base text-[#2B2D42] line-clamp-2">
                    {session.research_goal}
                  </h3>

                  {session.summary ? (
                    <p className="text-xs text-[#8D99AE] line-clamp-2">
                      {session.summary}
                    </p>
                  ) : (
                    <p className="text-xs text-[#8D99AE] italic">
                      No summary available yet.
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                  <Link to={`/research/${session.id}`}>
                    <NeuButton variant="secondary" size="sm" icon={ExternalLink}>
                      Details
                    </NeuButton>
                  </Link>

                  <NeuButton
                    variant="ghost"
                    size="sm"
                    onClick={(e) => handleDelete(session.id, e)}
                    disabled={isDeleting === session.id}
                    title="Delete research session"
                    className="text-[#8D99AE] hover:text-[#D90429]"
                  >
                    <Trash2 className="size-4" />
                  </NeuButton>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  )
}
