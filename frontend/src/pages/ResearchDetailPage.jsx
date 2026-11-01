import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Clock,
  Sparkles,
  Lock,
  Trash2,
  AlertCircle,
  CheckCircle,
  FileText,
} from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { StatusBadge } from '@/components/common/StatusBadge'
import { getResearchById, deleteResearch } from '@/services/researchService'

/**
 * Safely formats an ISO timestamp or date string.
 * Returns null if the timestamp is missing, empty, or invalid, preventing "Invalid Date" output.
 *
 * @param {string|null|undefined} timestamp
 * @returns {string|null}
 */
function formatTimestamp(timestamp) {
  if (!timestamp) return null
  const date = new Date(timestamp)
  if (isNaN(date.getTime())) return null
  return date.toLocaleString()
}

export function ResearchDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [errorMsg, setErrorMsg] = useState('')
  const [activeTab, setActiveTab] = useState('summary')
  const [isDeleting, setIsDeleting] = useState(false)

  useEffect(() => {
    let isCancelled = false

    async function fetchSession() {
      try {
        setErrorMsg('')
        const response = await getResearchById(id)
        if (isCancelled) return

        if (response?.data) {
          // Normalize research ID: session list uses `id`, report data uses `research_id`
          const normalized = {
            ...response.data,
            id: response.data.research_id || response.data.id || id,
          }
          setSession(normalized)
        } else {
          setErrorMsg('Research session record was empty.')
        }
      } catch (err) {
        if (isCancelled) return
        if (err.status === 404) {
          setErrorMsg('The requested research session does not exist or you do not have permission to access it.')
        } else if (err.status === 400) {
          setErrorMsg('Invalid research session ID format.')
        } else {
          setErrorMsg(err.message || 'Unable to retrieve research record from backend.')
        }
        setSession(null)
      } finally {
        if (!isCancelled) {
          setLoading(false)
        }
      }
    }

    if (id) {
      fetchSession()
    }

    return () => {
      isCancelled = true
    }
  }, [id])

  const handleDelete = async () => {
    if (!window.confirm('Are you sure you want to permanently delete this research session?')) {
      return
    }

    setIsDeleting(true)
    try {
      await deleteResearch(session?.id || id)
      navigate('/history', { replace: true })
    } catch (err) {
      alert(`Failed to delete research session: ${err.message}`)
      setIsDeleting(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto p-12 text-center text-[#8D99AE] space-y-3">
        <div className="size-8 rounded-full border-2 border-[#D90429] border-t-transparent animate-spin mx-auto" />
        <p className="text-sm">Loading investigation details...</p>
      </div>
    )
  }

  if (errorMsg || !session) {
    return (
      <div className="max-w-2xl mx-auto p-8 space-y-6">
        <GlassCard className="p-8 text-center space-y-4 border-l-4 border-l-[#EF233C]">
          <div className="size-14 rounded-2xl bg-[#EF233C]/10 text-[#D90429] flex items-center justify-center mx-auto">
            <AlertCircle className="size-7" />
          </div>
          <div className="space-y-1">
            <h3 className="text-lg font-bold text-[#2B2D42]">
              Research Session Not Available
            </h3>
            <p className="text-xs text-[#8D99AE]">
              {errorMsg || 'The requested research session could not be found.'}
            </p>
          </div>
          <div className="pt-2">
            <Link to="/history">
              <NeuButton variant="default" size="sm" icon={ArrowLeft}>
                Back to Research History
              </NeuButton>
            </Link>
          </div>
        </GlassCard>
      </div>
    )
  }

  const createdFormatted = formatTimestamp(session.created_at)
  const updatedFormatted = formatTimestamp(session.updated_at)
  const sourcesCount = session.sources?.length || 0
  const findingsCount = session.findings?.length || 0
  const verificationCount = session.verification_items?.length || 0
  const unresolvedCount = session.unresolved_questions?.length || 0

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Top Navigation & Actions */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <Link
          to="/history"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#8D99AE] hover:text-[#2B2D42]"
        >
          <ArrowLeft className="size-4" />
          Back to History
        </Link>

        <div className="flex items-center gap-2">
          <NeuButton
            variant="destructive"
            size="sm"
            onClick={handleDelete}
            disabled={isDeleting}
            icon={Trash2}
          >
            {isDeleting ? 'Deleting...' : 'Delete Session'}
          </NeuButton>
        </div>
      </div>

      {/* Main Session Overview Header */}
      <GlassCard className="space-y-4 p-6 sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#8D99AE]/15 pb-4">
          <div className="flex flex-wrap items-center gap-2.5">
            <StatusBadge status={session.status} />
            <span className="text-xs text-[#8D99AE] font-mono">
              ID: {session.id}
            </span>
          </div>

          {(createdFormatted || updatedFormatted) && (
            <div className="flex items-center gap-3 text-xs text-[#8D99AE]">
              {createdFormatted && (
                <span className="flex items-center gap-1">
                  <Clock className="size-3.5 text-[#8D99AE]" />
                  Created: {createdFormatted}
                </span>
              )}
              {updatedFormatted && (
                <span>
                  Updated: {updatedFormatted}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-[#8D99AE]">
            Research Objective
          </span>
          <h2 className="text-xl sm:text-2xl font-bold text-[#2B2D42] leading-snug">
            {session.research_goal}
          </h2>
        </div>

        {/* Summary Card */}
        <div className="p-5 rounded-2xl neu-inset space-y-2">
          <div className="flex items-center gap-2 text-xs font-bold text-[#2B2D42]">
            <Sparkles className="size-4 text-[#D90429]" />
            Session Analytical Summary
          </div>
          <p className="text-sm text-[#2B2D42] leading-relaxed">
            {session.summary?.trim() ||
              'No analytical summary available. Ingest sources and run AI gap analysis to evaluate digital dark spots.'}
          </p>
        </div>
      </GlassCard>

      {/* Navigation Tabs for Analysis Sections */}
      <div className="flex border-b border-[#8D99AE]/20 gap-2">
        <button
          onClick={() => setActiveTab('summary')}
          className={`px-4 py-2.5 text-xs font-bold transition-all border-b-2 cursor-pointer ${
            activeTab === 'summary'
              ? 'border-[#D90429] text-[#D90429]'
              : 'border-transparent text-[#8D99AE] hover:text-[#2B2D42]'
          }`}
        >
          Overview & Status
        </button>
        <button
          onClick={() => setActiveTab('findings')}
          className={`px-4 py-2.5 text-xs font-bold transition-all border-b-2 cursor-pointer flex items-center gap-1.5 ${
            activeTab === 'findings'
              ? 'border-[#D90429] text-[#D90429]'
              : 'border-transparent text-[#8D99AE] hover:text-[#2B2D42]'
          }`}
        >
          Information Gaps
          <span className="text-[10px] uppercase font-semibold px-1.5 py-0.2 rounded bg-amber-100 text-amber-800">
            Phase VI
          </span>
        </button>
        <button
          onClick={() => setActiveTab('sources')}
          className={`px-4 py-2.5 text-xs font-bold transition-all border-b-2 cursor-pointer flex items-center gap-1.5 ${
            activeTab === 'sources'
              ? 'border-[#D90429] text-[#D90429]'
              : 'border-transparent text-[#8D99AE] hover:text-[#2B2D42]'
          }`}
        >
          Source Material
          <span className="text-[10px] uppercase font-semibold px-1.5 py-0.2 rounded bg-amber-100 text-amber-800">
            Phase V
          </span>
        </button>
      </div>

      {/* Tab Panels */}
      {activeTab === 'summary' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <GlassCard className="p-5 space-y-3">
            <h3 className="font-heading font-semibold text-sm text-[#2B2D42] flex items-center gap-2">
              <CheckCircle className="size-4 text-emerald-600" />
              Investigation Overview
            </h3>
            <div className="space-y-2 text-xs text-[#8D99AE]">
              <div className="flex justify-between py-1 border-b border-[#8D99AE]/10">
                <span>Current Status</span>
                <span className="font-semibold text-[#2B2D42] uppercase">{session.status}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-[#8D99AE]/10">
                <span>Session UUID</span>
                <span className="font-mono text-[11px] text-[#2B2D42]">{session.id}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-[#8D99AE]/10">
                <span>Ingested Sources</span>
                <span className="font-semibold text-[#2B2D42]">{sourcesCount}</span>
              </div>
              <div className="flex justify-between py-1">
                <span>Detected Information Gaps</span>
                <span className="font-semibold text-[#2B2D42]">{findingsCount}</span>
              </div>
            </div>
          </GlassCard>

          <GlassCard className="p-5 space-y-3">
            <h3 className="font-heading font-semibold text-sm text-[#2B2D42] flex items-center gap-2">
              <FileText className="size-4 text-[#D90429]" />
              Analysis Scope & Verification
            </h3>
            <div className="space-y-2 text-xs text-[#8D99AE]">
              <div className="flex justify-between py-1 border-b border-[#8D99AE]/10">
                <span>Verification Checklist Tasks</span>
                <span className="font-semibold text-[#2B2D42]">{verificationCount}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-[#8D99AE]/10">
                <span>Unresolved Research Questions</span>
                <span className="font-semibold text-[#2B2D42]">{unresolvedCount}</span>
              </div>
              <div className="pt-2 text-xs text-[#8D99AE] leading-relaxed">
                {session.status === 'completed' ? (
                  <span className="text-emerald-700 font-medium">
                    AI gap detection has been completed for this investigation. Review the Information Gaps tab for categorized findings and verified evidence quotes.
                  </span>
                ) : session.status === 'processing' ? (
                  <span className="text-amber-700 font-medium">
                    AI analysis is currently evaluating source material.
                  </span>
                ) : session.status === 'failed' ? (
                  <span className="text-[#D90429] font-medium">
                    Analysis could not be completed. Check source validity and retry.
                  </span>
                ) : (
                  <span>
                    Investigation initialized. Attach source material to expose missing facts, outdated claims, conflicting data, and unverified statements.
                  </span>
                )}
              </div>
            </div>
          </GlassCard>
        </div>
      )}

      {/* Findings Tab Placeholder (to be unlocked in Step 2.4) */}
      {activeTab === 'findings' && (
        <GlassCard className="p-8 text-center space-y-4">
          <div className="size-12 rounded-xl bg-amber-500/10 text-amber-600 flex items-center justify-center mx-auto border border-amber-500/20">
            <Lock className="size-6" />
          </div>
          <div className="max-w-md mx-auto space-y-1">
            <h3 className="font-heading font-bold text-base text-[#2B2D42]">
              Gap Detection Engine Scheduled for Phase VI
            </h3>
            <p className="text-xs text-[#8D99AE]">
              Categorized information gaps (Missing, Outdated, Conflicting, and Unverified) with evidence cross-references and verification task lists will be populated automatically when AI analysis runs in Phase VI.
            </p>
          </div>
        </GlassCard>
      )}

      {/* Sources Tab Placeholder (to be unlocked in Step 2.2) */}
      {activeTab === 'sources' && (
        <GlassCard className="p-8 text-center space-y-4">
          <div className="size-12 rounded-xl bg-amber-500/10 text-amber-600 flex items-center justify-center mx-auto border border-amber-500/20">
            <Lock className="size-6" />
          </div>
          <div className="max-w-md mx-auto space-y-1">
            <h3 className="font-heading font-bold text-base text-[#2B2D42]">
              Source Ingestion Pipeline Scheduled for Phase V
            </h3>
            <p className="text-xs text-[#8D99AE]">
              Multi-source extraction engine using Trafilatura and Jina Reader (with SSRF protection and DuckDuckGo discovery) will be integrated in Phase V.
            </p>
          </div>
        </GlassCard>
      )}
    </div>
  )
}
