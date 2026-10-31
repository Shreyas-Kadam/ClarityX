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
        // If unauthenticated or backend error
        setErrorMsg(err.message || 'Unable to fetch research history from backend.')
        // Provide local sample items for visual review
        setSessions([
          {
            id: 'demo-session-01',
            research_goal: 'Autonomous driving regulatory standards and safety gaps across EU & US',
            status: 'completed',
            summary: 'Identified 3 conflicting statements and 2 unverified claims.',
            created_at: new Date(Date.now() - 3600000 * 3).toISOString(),
            is_demo: true,
          },
          {
            id: 'demo-session-02',
            research_goal: 'Quantum dot solar cell efficiency reports and commercial longevity claims',
            status: 'processing',
            summary: 'In progress: cross-verifying benchmark data against peer-reviewed journals.',
            created_at: new Date(Date.now() - 3600000 * 12).toISOString(),
            is_demo: true,
          },
          {
            id: 'demo-session-03',
            research_goal: 'Semiconductor supply chain geographic bottlenecks for advanced sub-3nm nodes',
            status: 'pending',
            summary: '',
            created_at: new Date(Date.now() - 3600000 * 36).toISOString(),
            is_demo: true,
          },
        ])
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
    if (!window.confirm('Are you sure you want to delete this research session?')) {
      return
    }

    setIsDeleting(id)
    try {
      await deleteResearch(id)
      setSessions((prev) => prev.filter((s) => s.id !== id))
    } catch {
      // If demo or failed, remove locally
      setSessions((prev) => prev.filter((s) => s.id !== id))
    } finally {
      setIsDeleting(null)
    }
  }

  const filteredSessions = sessions.filter((s) => {
    if (searchQuery.trim()) {
      return s.research_goal.toLowerCase().includes(searchQuery.toLowerCase())
    }
    return true
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
            Browse and inspect prior research reports and gap analyses.
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

      {errorMsg && (
        <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 text-sm flex items-start gap-3">
          <AlertCircle className="size-5 shrink-0 text-amber-700 mt-0.5" />
          <div className="flex-1">
            <strong>Backend Connection Notice:</strong> {errorMsg}
            <span className="block text-xs text-amber-700 mt-0.5">
              Displaying local preview items. Once an active Supabase user session token is saved in Settings, queries will read directly from live database.
            </span>
          </div>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        {/* Status Filter Tabs */}
        <div className="inline-flex p-1 rounded-2xl neu-inset gap-1">
          {['all', 'completed', 'processing', 'pending', 'failed'].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold capitalize transition-all cursor-pointer ${
                statusFilter === st
                  ? 'bg-gradient-to-r from-[#D90429] to-[#EF233C] text-white shadow-xs'
                  : 'text-[#8D99AE] hover:text-[#2B2D42]'
              }`}
            >
              {st}
            </button>
          ))}
        </div>

        {/* Search Input */}
        <div className="w-full sm:w-72">
          <NeuInput
            placeholder="Search by research goal..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            icon={Search}
          />
        </div>
      </div>

      {/* Session List */}
      {loading ? (
        <div className="p-12 rounded-3xl neu-raised text-center text-[#8D99AE] space-y-3">
          <RefreshCw className="size-6 animate-spin mx-auto text-[#D90429]" />
          <p className="text-sm font-medium">Fetching research records from database...</p>
        </div>
      ) : filteredSessions.length === 0 ? (
        <div className="p-12 rounded-3xl neu-raised text-center space-y-4">
          <div className="size-14 rounded-2xl neu-inset mx-auto flex items-center justify-center text-[#8D99AE]">
            <FileSearch className="size-7" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-[#2B2D42]">
              No research sessions found
            </h3>
            <p className="text-xs text-[#8D99AE] max-w-sm mx-auto mt-1">
              {searchQuery || statusFilter !== 'all'
                ? 'No sessions match your current search or status filter.'
                : 'You have not initialized any research investigations yet.'}
            </p>
          </div>
          <Link to="/new">
            <NeuButton variant="cta" size="sm" icon={Plus}>
              Create First Investigation
            </NeuButton>
          </Link>
        </div>
      ) : (
        <div className="space-y-3.5">
          {filteredSessions.map((session) => (
            <GlassCard
              key={session.id}
              hover={true}
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5"
            >
              <div className="space-y-2 flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={session.status} />
                  {session.is_demo && (
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-[#8D99AE]/15 text-[#8D99AE]">
                      Demo Preview
                    </span>
                  )}
                  <span className="text-xs text-[#8D99AE]">
                    Created on{' '}
                    {new Date(session.created_at).toLocaleDateString(undefined, {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                </div>

                <h3 className="text-base font-bold text-[#2B2D42] truncate">
                  {session.research_goal}
                </h3>

                {session.summary && (
                  <p className="text-xs text-[#8D99AE] line-clamp-2">
                    {session.summary}
                  </p>
                )}
              </div>

              <div className="flex items-center gap-2.5 shrink-0 self-end sm:self-center">
                <Link to={`/research/${session.id}`}>
                  <NeuButton variant="default" size="sm" icon={ExternalLink}>
                    View Report
                  </NeuButton>
                </Link>

                <NeuButton
                  variant="destructive"
                  size="sm"
                  onClick={(e) => handleDelete(session.id, e)}
                  disabled={isDeleting === session.id}
                  icon={Trash2}
                  aria-label="Delete research session"
                />
              </div>
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  )
}
