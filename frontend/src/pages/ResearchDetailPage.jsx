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
  Plus,
  RefreshCw,
  X,
  Globe,
} from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { StatusBadge } from '@/components/common/StatusBadge'
import { getResearchById, deleteResearch, analyzeResearch } from '@/services/researchService'
import { getSources, deleteSource } from '@/services/sourceService'
import { SourceCard } from '@/components/sources/SourceCard'
import { AddSourceForm } from '@/components/sources/AddSourceForm'

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
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadingSources, setLoadingSources] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [activeTab, setActiveTab] = useState('summary')
  const [isDeleting, setIsDeleting] = useState(false)
  const [showAddSource, setShowAddSource] = useState(false)
  const [isDeletingSourceId, setIsDeletingSourceId] = useState(null)
  const [sourceFeedback, setSourceFeedback] = useState({ error: '', success: '' })
  const [analysisFeedback, setAnalysisFeedback] = useState({ error: '', success: '' })

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
          setSources(normalized.sources || [])
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
        setSources([])
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
    if (isAnalyzing || isDeleting) return
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

  const handleRefreshSources = async () => {
    const researchId = session?.id || id
    if (!researchId || isAnalyzing) return

    setLoadingSources(true)
    try {
      const response = await getSources(researchId)
      const list = response?.data?.sources || []
      setSources(list)
      setSession((prev) => (prev ? { ...prev, sources: list } : prev))
    } catch (err) {
      setSourceFeedback((prev) => ({
        ...prev,
        error: err.message || 'Failed to refresh sources.',
      }))
    } finally {
      setLoadingSources(false)
    }
  }

  const handleSourceAdded = (createdSource) => {
    const code = createdSource?.source_code ? `[${createdSource.source_code}] ` : ''
    const title = createdSource?.title || 'New source'
    setSourceFeedback({
      error: '',
      success: `Source ${code}"${title}" successfully attached and extracted!`,
    })
    setShowAddSource(false)
    handleRefreshSources()
  }

  const handleDeleteSource = async (sourceId) => {
    const researchId = session?.id || id
    if (!researchId || isDeletingSourceId || isAnalyzing) return

    setIsDeletingSourceId(sourceId)
    setSourceFeedback({ error: '', success: '' })
    try {
      await deleteSource(researchId, sourceId)
      setSourceFeedback({
        error: '',
        success: 'Source successfully removed from research session.',
      })
      await handleRefreshSources()
    } catch (err) {
      setSourceFeedback({
        error: err.message || 'Failed to delete source.',
        success: '',
      })
    } finally {
      setIsDeletingSourceId(null)
    }
  }

  // Derived source eligibility checks
  const usableSourcesCount = sources.filter(
    (s) => s.extraction_status !== 'failed' && Boolean(s.content_preview?.trim())
  ).length
  const hasUsableSources = usableSourcesCount > 0

  const handleRunAnalysis = async () => {
    // 1. Prevent duplicate submissions
    if (isAnalyzing) return
    // 2. Prevent analysis if session is being deleted
    if (isDeleting) return
    // 3. Check that at least one usable source exists
    if (!hasUsableSources) {
      setAnalysisFeedback({
        error: 'At least one valid source with readable extracted content is required before running AI analysis.',
        success: '',
      })
      return
    }

    const researchId = session?.id || id
    if (!researchId) return

    // 4. Set analyzing state and clear previous feedback
    setIsAnalyzing(true)
    setAnalysisFeedback({ error: '', success: '' })

    try {
      // 5. Call analyzeResearch
      const response = await analyzeResearch(researchId)

      // 6. Read complete report from response.data
      if (response?.data) {
        // 7. Normalize report ID
        const normalized = {
          ...response.data,
          id: response.data.research_id || response.data.id || researchId,
        }

        // 8. Update session
        setSession(normalized)

        // 9. Update source list using returned report's sources
        if (Array.isArray(normalized.sources)) {
          setSources(normalized.sources)
        }

        // 10. Display success message with finding and verification item counts
        const fCount = normalized.findings?.length || 0
        const vCount = normalized.verification_items?.length || 0
        setAnalysisFeedback({
          error: '',
          success: `AI information gap analysis completed successfully! Discovered ${fCount} categorized gap finding${fCount === 1 ? '' : 's'} and generated ${vCount} verification checklist item${vCount === 1 ? '' : 's'}.`,
        })
      } else {
        setAnalysisFeedback({
          error: 'Analysis completed but returned an empty report structure.',
          success: '',
        })
      }
    } catch (err) {
      // 11. Catch API errors and display normalized err.message
      setAnalysisFeedback({
        error: err.message || 'AI analysis failed to complete. Please check service configuration.',
        success: '',
      })
    } finally {
      // 12. Always reset isAnalyzing
      setIsAnalyzing(false)
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
  const sourcesCount = sources.length
  const findingsCount = session.findings?.length || 0
  const verificationCount = session.verification_items?.length || 0
  const unresolvedCount = session.unresolved_questions?.length || 0
  const isCompleted = session.status === 'completed'

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

        <div className="flex flex-wrap items-center gap-2">
          {/* Primary CTA: Run / Re-run AI Gap Analysis */}
          <NeuButton
            variant="cta"
            size="sm"
            onClick={handleRunAnalysis}
            disabled={isAnalyzing || isDeleting || !hasUsableSources}
            icon={Sparkles}
            title={
              !hasUsableSources
                ? 'Add at least one usable source with readable text to enable analysis'
                : isCompleted
                  ? 'Re-evaluate research sources with AI gap detection'
                  : 'Run AI information gap analysis'
            }
          >
            {isAnalyzing ? (
              <span className="flex items-center gap-1.5">
                <span className="size-3.5 border-2 border-white border-t-transparent rounded-full animate-spin shrink-0" />
                Analyzing Sources...
              </span>
            ) : isCompleted ? (
              'Re-run Gap Analysis'
            ) : (
              'Run Gap Analysis'
            )}
          </NeuButton>

          {/* Delete Session Button */}
          <NeuButton
            variant="destructive"
            size="sm"
            onClick={handleDelete}
            disabled={isDeleting || isAnalyzing}
            icon={Trash2}
          >
            {isDeleting ? 'Deleting...' : 'Delete Session'}
          </NeuButton>
        </div>
      </div>

      {/* Explanatory notice when analysis is disabled due to missing usable sources */}
      {!hasUsableSources && !isAnalyzing && (
        <div className="p-3.5 rounded-xl bg-amber-50/90 border border-amber-200 text-amber-800 text-xs flex flex-wrap items-center justify-between gap-2.5">
          <div className="flex items-center gap-2">
            <AlertCircle className="size-4 shrink-0 text-amber-600" />
            <span>
              {sources.length === 0
                ? 'AI analysis is currently disabled because no sources are attached. Ingest at least one reference source in the Source Material tab to enable gap analysis.'
                : 'AI analysis is currently disabled because all attached sources failed extraction or lack readable text. Attach a source with readable content to enable analysis.'}
            </span>
          </div>
          {activeTab !== 'sources' && (
            <button
              type="button"
              onClick={() => setActiveTab('sources')}
              className="font-bold text-[#D90429] hover:underline cursor-pointer text-xs"
            >
              Go to Source Material &rarr;
            </button>
          )}
        </div>
      )}

      {/* Active Analysis Progress Banner */}
      {isAnalyzing && (
        <div className="p-4 rounded-2xl neu-inset bg-amber-50/95 border border-amber-300 text-amber-950 text-xs space-y-2 animate-pulse">
          <div className="flex items-center gap-2.5 font-bold text-sm text-[#2B2D42]">
            <div className="size-4 border-2 border-[#D90429] border-t-transparent rounded-full animate-spin shrink-0" />
            AI Information Gap Analysis in Progress
          </div>
          <p className="text-xs leading-relaxed text-[#2B2D42]">
            AI Information Gap Analysis in progress. Cross-referencing your source material and detecting missing, outdated, conflicting, and unverified information. This may take up to 35 seconds.
          </p>
        </div>
      )}

      {/* Analysis Feedback Banners */}
      {analysisFeedback.success && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <CheckCircle className="size-4 text-emerald-600 shrink-0" />
            <span>{analysisFeedback.success}</span>
          </div>
          <button
            type="button"
            onClick={() => setAnalysisFeedback((p) => ({ ...p, success: '' }))}
            className="text-emerald-700 hover:text-emerald-900 cursor-pointer"
            title="Dismiss notification"
          >
            <X className="size-3.5" />
          </button>
        </div>
      )}

      {analysisFeedback.error && (
        <div className="p-3.5 rounded-xl bg-[#EF233C]/10 border border-[#EF233C]/30 text-[#D90429] text-xs flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <AlertCircle className="size-4 text-[#D90429] shrink-0" />
            <span>{analysisFeedback.error}</span>
          </div>
          <button
            type="button"
            onClick={() => setAnalysisFeedback((p) => ({ ...p, error: '' }))}
            className="text-[#D90429] hover:text-[#2B2D42] cursor-pointer"
            title="Dismiss notification"
          >
            <X className="size-3.5" />
          </button>
        </div>
      )}

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
          onClick={() => setActiveTab('sources')}
          className={`px-4 py-2.5 text-xs font-bold transition-all border-b-2 cursor-pointer flex items-center gap-1.5 ${
            activeTab === 'sources'
              ? 'border-[#D90429] text-[#D90429]'
              : 'border-transparent text-[#8D99AE] hover:text-[#2B2D42]'
          }`}
        >
          Source Material
          <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded bg-slate-200 text-[#2B2D42]">
            {sourcesCount}
          </span>
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
          <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded bg-slate-200 text-[#2B2D42]">
            {findingsCount}
          </span>
          <span className="text-[10px] uppercase font-semibold px-1.5 py-0.2 rounded bg-amber-100 text-amber-800">
            Phase VI
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

      {/* Sources Tab - Active Source Ingestion Management */}
      {activeTab === 'sources' && (
        <div className="space-y-4">
          {/* Source Management Header */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="space-y-0.5">
              <h3 className="text-base font-bold text-[#2B2D42] flex items-center gap-2">
                <span>Source Material</span>
                <span className="px-2 py-0.5 rounded-full bg-[#2B2D42] text-[#EDF2F4] text-xs font-mono">
                  {sources.length} / 5
                </span>
              </h3>
              <p className="text-xs text-[#8D99AE]">
                Authoritative reference sources and evidence material used for cross-source gap analysis.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <NeuButton
                variant="default"
                size="sm"
                onClick={handleRefreshSources}
                disabled={loadingSources || isAnalyzing}
                icon={RefreshCw}
                title="Refresh source list"
              >
                {loadingSources ? 'Refreshing...' : 'Refresh'}
              </NeuButton>

              {sources.length < 5 && (
                <NeuButton
                  variant="cta"
                  size="sm"
                  onClick={() => {
                    setShowAddSource((prev) => !prev)
                    setSourceFeedback({ error: '', success: '' })
                  }}
                  disabled={isAnalyzing}
                  icon={showAddSource ? X : Plus}
                >
                  {showAddSource ? 'Cancel' : 'Add Source'}
                </NeuButton>
              )}
            </div>
          </div>

          {/* Contextual Ready for AI Analysis Banner */}
          {hasUsableSources && !isAnalyzing && (
            <div className="p-4 rounded-xl neu-inset bg-white/40 border border-white/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h4 className="text-xs font-bold text-[#2B2D42] flex items-center gap-1.5">
                  <Sparkles className="size-3.5 text-[#D90429]" />
                  Sources Ready for AI Evaluation
                </h4>
                <p className="text-[11px] text-[#8D99AE]">
                  {usableSourcesCount} valid source{usableSourcesCount === 1 ? '' : 's'} available to evaluate against your research goal.
                </p>
              </div>
              <NeuButton
                variant="cta"
                size="sm"
                onClick={handleRunAnalysis}
                disabled={isAnalyzing || isDeleting}
                icon={Sparkles}
              >
                {isCompleted ? 'Re-run Gap Analysis' : 'Run Gap Analysis'}
              </NeuButton>
            </div>
          )}

          {/* Source Limit Notice */}
          {sources.length >= 5 && !showAddSource && (
            <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-center gap-2">
              <AlertCircle className="size-4 shrink-0 text-amber-600" />
              <span>
                <strong>Source capacity reached (5/5).</strong> To attach a new source, delete an existing source first.
              </span>
            </div>
          )}

          {/* Feedback Messages */}
          {sourceFeedback.success && (
            <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle className="size-4 text-emerald-600 shrink-0" />
                <span>{sourceFeedback.success}</span>
              </div>
              <button
                type="button"
                onClick={() => setSourceFeedback((p) => ({ ...p, success: '' }))}
                className="text-emerald-700 hover:text-emerald-900 cursor-pointer"
                title="Dismiss message"
              >
                <X className="size-3.5" />
              </button>
            </div>
          )}

          {sourceFeedback.error && (
            <div className="p-3.5 rounded-xl bg-[#EF233C]/10 border border-[#EF233C]/30 text-[#D90429] text-xs flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertCircle className="size-4 text-[#D90429] shrink-0" />
                <span>{sourceFeedback.error}</span>
              </div>
              <button
                type="button"
                onClick={() => setSourceFeedback((p) => ({ ...p, error: '' }))}
                className="text-[#D90429] hover:text-[#2B2D42] cursor-pointer"
                title="Dismiss message"
              >
                <X className="size-3.5" />
              </button>
            </div>
          )}

          {/* Add Source Form Card */}
          {showAddSource && sources.length < 5 && (
            <AddSourceForm
              researchId={session.id}
              currentSourceCount={sources.length}
              onSuccess={handleSourceAdded}
              onCancel={() => setShowAddSource(false)}
              disabled={isAnalyzing}
            />
          )}

          {/* Source List or Empty State */}
          {sources.length === 0 ? (
            <GlassCard className="p-10 text-center space-y-4">
              <div className="size-14 rounded-2xl bg-white/70 border border-[#8D99AE]/20 text-[#8D99AE] flex items-center justify-center mx-auto">
                <Globe className="size-7 text-[#D90429]" />
              </div>
              <div className="max-w-md mx-auto space-y-1">
                <h4 className="font-heading font-bold text-base text-[#2B2D42]">
                  No Sources Attached Yet
                </h4>
                <p className="text-xs text-[#8D99AE] leading-relaxed">
                  Attach up to 5 sources (website articles, raw text excerpts, or PDF/DOCX documents) to enable AI information gap detection.
                </p>
              </div>
              {!showAddSource && (
                <div className="pt-2">
                  <NeuButton
                    variant="cta"
                    size="sm"
                    icon={Plus}
                    onClick={() => {
                      setShowAddSource(true)
                      setSourceFeedback({ error: '', success: '' })
                    }}
                    disabled={isAnalyzing}
                  >
                    Add First Source
                  </NeuButton>
                </div>
              )}
            </GlassCard>
          ) : (
            <div className="space-y-3.5">
              {sources.map((source) => (
                <SourceCard
                  key={source.id}
                  source={source}
                  onDelete={handleDeleteSource}
                  isDeleting={isDeletingSourceId === source.id}
                  disabled={isAnalyzing}
                />
              ))}
            </div>
          )}
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
    </div>
  )
}
