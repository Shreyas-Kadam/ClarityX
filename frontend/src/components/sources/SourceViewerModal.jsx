import { useState, useEffect, useRef, useCallback } from 'react'
import {
  X,
  Globe,
  FileText,
  File,
  ExternalLink,
  Copy,
  Check,
  RefreshCw,
  AlertCircle,
  Quote,
  ArrowDown,
  ArrowUp,
  Calendar,
  Clock,
  Layers,
} from 'lucide-react'
import { NeuButton } from '@/components/common/NeuButton'
import { SourceStatusBadge } from './SourceStatusBadge'
import { getSourceById } from '@/services/sourceService'
import { splitTextWithHighlights } from '@/lib/evidenceMatcher'
import {
  getCachedSource,
  setCachedSource,
  getInFlightRequest,
  setInFlightRequest,
  deleteInFlightRequest,
} from '@/lib/sourceCache'
import { cn } from '@/lib/utils'

/**
 * Formats timestamps cleanly without throwing or displaying Invalid Date.
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

/**
 * SourceViewerModal Component
 *
 * Full-screen accessible modal providing complete extracted content inspection,
 * metadata verification, and bidirectional evidence navigation with verbatim quotation highlighting.
 *
 * @param {Object} props
 * @param {boolean} props.isOpen - Whether the modal is visible
 * @param {Function} props.onClose - Callback when modal is closed
 * @param {string} props.researchId - Active research session UUID
 * @param {string} props.sourceId - Target source UUID to load
 * @param {string|null} [props.targetQuotation=null] - Optional verbatim quote to locate and highlight
 * @param {Object|null} [props.initialPreview=null] - Optional lightweight preview object for immediate header rendering
 */
export function SourceViewerModal({
  isOpen,
  onClose,
  researchId,
  sourceId,
  targetQuotation = null,
  initialPreview = null,
}) {
  const initialCached = getCachedSource(researchId, sourceId)
  const [sourceData, setSourceData] = useState(() => initialCached)
  const [loading, setLoading] = useState(() => !initialCached)
  const [error, setError] = useState('')
  const [copiedUrl, setCopiedUrl] = useState(false)
  const [copiedContent, setCopiedContent] = useState(false)
  const [activeMatchIndex, setActiveMatchIndex] = useState(0)

  const modalRef = useRef(null)
  const contentAreaRef = useRef(null)
  const previouslyFocusedElementRef = useRef(null)

  // Fetch full source content when not already in memory cache
  useEffect(() => {
    let ignore = false

    if (!isOpen || !researchId || !sourceId) {
      return
    }

    const currentCached = getCachedSource(researchId, sourceId)
    if (currentCached) {
      return
    }

    let promise = getInFlightRequest(researchId, sourceId)
    if (!promise) {
      promise = getSourceById(researchId, sourceId)
      setInFlightRequest(researchId, sourceId, promise)
    }

    promise
      .then((response) => {
        deleteInFlightRequest(researchId, sourceId)
        if (!ignore) {
          if (response?.data) {
            setCachedSource(researchId, sourceId, response.data)
            setSourceData(response.data)
          } else {
            setError('Received empty source data from server.')
          }
          setLoading(false)
        }
      })
      .catch((err) => {
        deleteInFlightRequest(researchId, sourceId)
        if (!ignore) {
          if (err.status === 404) {
            setError('The requested source was not found or has been removed from this investigation.')
          } else {
            setError(err.message || 'Unable to retrieve full source content from backend.')
          }
          setSourceData(null)
          setLoading(false)
        }
      })

    return () => {
      ignore = true
    }
  }, [isOpen, researchId, sourceId])

  // Explicit retry handler triggered by user action
  const handleRetry = useCallback(async () => {
    if (!researchId || !sourceId) return

    setLoading(true)
    setError('')
    try {
      const promise = getSourceById(researchId, sourceId)
      setInFlightRequest(researchId, sourceId, promise)
      const response = await promise
      deleteInFlightRequest(researchId, sourceId)

      if (response?.data) {
        setCachedSource(researchId, sourceId, response.data)
        setSourceData(response.data)
      } else {
        throw new Error('Received empty source data from server.')
      }
    } catch (err) {
      deleteInFlightRequest(researchId, sourceId)
      if (err.status === 404) {
        setError('The requested source was not found or has been removed from this investigation.')
      } else {
        setError(err.message || 'Unable to retrieve full source content from backend.')
      }
      setSourceData(null)
    } finally {
      setLoading(false)
    }
  }, [researchId, sourceId])

  // Lifecycle: open/close handling, focus capture, and scroll lock
  useEffect(() => {
    if (!isOpen) return

    // Capture previous active element for accessibility focus restoration
    previouslyFocusedElementRef.current = document.activeElement

    // Prevent background page scrolling while modal is open
    const originalOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    // Focus modal container
    if (modalRef.current) {
      modalRef.current.focus()
    }

    return () => {
      document.body.style.overflow = originalOverflow
      if (previouslyFocusedElementRef.current && typeof previouslyFocusedElementRef.current.focus === 'function') {
        previouslyFocusedElementRef.current.focus()
      }
    }
  }, [isOpen])

  // Keyboard navigation: Escape key closes modal; Tab key is trapped inside dialog
  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return
      }

      if (e.key === 'Tab') {
        if (!modalRef.current) return
        const focusable = modalRef.current.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        )
        if (focusable.length === 0) return

        const firstElement = focusable[0]
        const lastElement = focusable[focusable.length - 1]

        if (e.shiftKey) {
          if (document.activeElement === firstElement || document.activeElement === modalRef.current) {
            e.preventDefault()
            lastElement.focus()
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault()
            firstElement.focus()
          }
        }
      }
    },
    [onClose]
  )

  // Resolve source details (fallback to initialPreview while loading)
  const activeSource = sourceData || initialPreview
  const fullContent = sourceData?.extracted_content || ''

  // Process text highlighting for evidence quotations
  const { segments, totalMatches } = splitTextWithHighlights(
    fullContent,
    targetQuotation,
    activeMatchIndex
  )

  // Auto-scroll to active match when source or match changes
  useEffect(() => {
    if (!isOpen || totalMatches === 0) return

    const timer = setTimeout(() => {
      const matchElem = document.getElementById(`evidence-match-${activeMatchIndex}`)
      if (matchElem) {
        matchElem.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }, 120)

    return () => clearTimeout(timer)
  }, [isOpen, totalMatches, activeMatchIndex, fullContent])

  const handleCopyUrl = async () => {
    if (!activeSource?.url) return
    try {
      await navigator.clipboard.writeText(activeSource.url)
      setCopiedUrl(true)
      setTimeout(() => setCopiedUrl(false), 2000)
    } catch {
      // Ignore clipboard write failures
    }
  }

  const handleCopyFullText = async () => {
    if (!fullContent) return
    try {
      await navigator.clipboard.writeText(fullContent)
      setCopiedContent(true)
      setTimeout(() => setCopiedContent(false), 2000)
    } catch {
      // Ignore clipboard write failures
    }
  }

  const scrollToNextMatch = () => {
    if (totalMatches <= 1) return
    setActiveMatchIndex((prev) => (prev + 1) % totalMatches)
  }

  const scrollToPrevMatch = () => {
    if (totalMatches <= 1) return
    setActiveMatchIndex((prev) => (prev - 1 + totalMatches) % totalMatches)
  }

  if (!isOpen) return null

  // Type configuration
  const typeConfig = {
    website: { label: 'Website', icon: Globe },
    pasted_text: { label: 'Pasted Text', icon: FileText },
    document: { label: 'Document', icon: File },
  }
  const currentType = typeConfig[activeSource?.source_type] || {
    label: activeSource?.source_type || 'Source',
    icon: File,
  }
  const TypeIcon = currentType.icon

  // Calculate live word and character metrics
  const charCount = fullContent ? fullContent.length : (activeSource?.character_count || 0)
  const wordCount = fullContent
    ? fullContent.trim().split(/\s+/).filter(Boolean).length
    : (activeSource?.word_count || 0)

  const publishedFormatted = formatTimestamp(activeSource?.published_at)
  const accessedFormatted = formatTimestamp(activeSource?.accessed_at || activeSource?.created_at)

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="source-viewer-title"
      aria-describedby="source-viewer-desc"
      onKeyDown={handleKeyDown}
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-150"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        ref={modalRef}
        tabIndex={-1}
        className="w-full max-w-4xl max-h-[92vh] flex flex-col bg-white rounded-2xl shadow-2xl border border-slate-200 outline-none overflow-hidden"
      >
        {/* =====================================================================
            1. HEADER: Source Code, Title, Badges, and Close Action
            ===================================================================== */}
        <header className="px-5 py-4 border-b border-slate-200 bg-slate-50/80 flex items-start justify-between gap-3 shrink-0">
          <div className="space-y-1.5 min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              {activeSource?.source_code && (
                <span className="px-2 py-0.5 rounded-lg bg-[#2B2D42] text-[#EDF2F4] text-xs font-mono font-bold tracking-wide">
                  {activeSource.source_code}
                </span>
              )}
              <span className="inline-flex items-center gap-1 text-xs font-semibold text-[#8D99AE]">
                <TypeIcon className="size-3.5" />
                {currentType.label}
              </span>
              {activeSource?.extraction_status && (
                <SourceStatusBadge status={activeSource.extraction_status} />
              )}
            </div>

            <h3
              id="source-viewer-title"
              className="text-lg sm:text-xl font-bold text-[#2B2D42] truncate"
              title={activeSource?.title || 'Source Inspection'}
            >
              {activeSource?.title || 'Untitled Source'}
            </h3>

            {/* URL Display with External Link and Copy Action */}
            {activeSource?.url && (
              <div className="flex items-center gap-2 pt-0.5 text-xs text-[#8D99AE]">
                <a
                  href={activeSource.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[#2B2D42] hover:text-[#D90429] underline underline-offset-2 truncate max-w-[420px]"
                  title={activeSource.url}
                >
                  <span className="truncate">{activeSource.url}</span>
                  <ExternalLink className="size-3 shrink-0" />
                </a>
                <button
                  type="button"
                  onClick={handleCopyUrl}
                  className="inline-flex items-center gap-1 text-[11px] text-[#8D99AE] hover:text-[#2B2D42] px-1.5 py-0.5 rounded bg-white border border-slate-200 transition-colors"
                  title="Copy source URL"
                >
                  {copiedUrl ? (
                    <>
                      <Check className="size-3 text-emerald-600" />
                      <span className="text-emerald-700 font-medium">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="size-3" />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={onClose}
              className="size-8 rounded-lg flex items-center justify-center text-slate-500 hover:text-slate-800 hover:bg-slate-200/60 transition-colors cursor-pointer"
              aria-label="Close source viewer"
              title="Close (Esc)"
            >
              <X className="size-5" />
            </button>
          </div>
        </header>

        {/* =====================================================================
            2. METADATA STRIP: Counts, Timestamps, and Content Actions
            ===================================================================== */}
        <div
          id="source-viewer-desc"
          className="px-5 py-2.5 bg-slate-100/70 border-b border-slate-200 text-xs text-[#8D99AE] flex flex-wrap items-center justify-between gap-3 shrink-0"
        >
          <div className="flex flex-wrap items-center gap-4">
            <span className="flex items-center gap-1" title="Word count">
              <FileText className="size-3.5 text-[#8D99AE]" />
              <strong className="text-[#2B2D42] font-semibold">{wordCount.toLocaleString()}</strong> words
            </span>

            <span className="flex items-center gap-1" title="Character count">
              <Layers className="size-3.5 text-[#8D99AE]" />
              <strong className="text-[#2B2D42] font-semibold">{charCount.toLocaleString()}</strong> characters
            </span>

            {activeSource?.page_count && (
              <span className="flex items-center gap-1" title="Document page count">
                <File className="size-3.5 text-[#8D99AE]" />
                <strong className="text-[#2B2D42] font-semibold">{activeSource.page_count}</strong> pages
              </span>
            )}

            {publishedFormatted && (
              <span className="flex items-center gap-1" title="Publication Date">
                <Calendar className="size-3.5 text-[#8D99AE]" />
                Published: {publishedFormatted}
              </span>
            )}

            {accessedFormatted && (
              <span className="flex items-center gap-1" title="Access Date">
                <Clock className="size-3.5 text-[#8D99AE]" />
                Accessed: {accessedFormatted}
              </span>
            )}
          </div>

          {fullContent && !loading && !error && (
            <button
              type="button"
              onClick={handleCopyFullText}
              className="inline-flex items-center gap-1 text-xs text-[#2B2D42] hover:text-[#D90429] font-medium px-2 py-1 rounded bg-white border border-slate-200 shadow-2xs transition-colors"
              title="Copy complete extracted text to clipboard"
            >
              {copiedContent ? (
                <>
                  <Check className="size-3.5 text-emerald-600" />
                  <span className="text-emerald-700">Copied Full Text</span>
                </>
              ) : (
                <>
                  <Copy className="size-3.5 text-slate-600" />
                  <span>Copy Full Text</span>
                </>
              )}
            </button>
          )}
        </div>

        {/* =====================================================================
            3. EVIDENCE QUOTATION NAVIGATION BANNER (When targetQuotation is present)
            ===================================================================== */}
        {targetQuotation && !loading && !error && (
          <div className="px-5 py-3 border-b border-slate-200 bg-amber-50/80 shrink-0 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wider bg-amber-200/80 text-amber-900 flex items-center gap-1">
                  <Quote className="size-3" />
                  Evidence Citation
                </span>

                {totalMatches > 0 ? (
                  <span className="text-xs font-semibold text-amber-900">
                    Quotation located in source ({activeMatchIndex + 1} of {totalMatches} {totalMatches === 1 ? 'match' : 'matches'})
                  </span>
                ) : (
                  <span className="text-xs font-bold text-rose-700 flex items-center gap-1">
                    <AlertCircle className="size-3.5 shrink-0" />
                    Exact evidence quotation could not be located in this source.
                  </span>
                )}
              </div>

              {totalMatches > 1 && (
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={scrollToPrevMatch}
                    className="p-1 rounded bg-white border border-amber-300 text-amber-900 hover:bg-amber-100 transition-colors cursor-pointer"
                    title="Previous match"
                    aria-label="Previous match"
                  >
                    <ArrowUp className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={scrollToNextMatch}
                    className="p-1 rounded bg-white border border-amber-300 text-amber-900 hover:bg-amber-100 transition-colors cursor-pointer"
                    title="Next match"
                    aria-label="Next match"
                  >
                    <ArrowDown className="size-3.5" />
                  </button>
                </div>
              )}
            </div>

            {/* Target quote reference preview */}
            <blockquote className="text-xs font-mono text-slate-800 bg-white/80 p-2.5 rounded-lg border border-amber-200/70 italic line-clamp-3">
              &ldquo;{targetQuotation}&rdquo;
            </blockquote>
          </div>
        )}

        {/* =====================================================================
            4. MAIN CONTENT AREA: Scrollable Extracted Text / Loading / Error
            ===================================================================== */}
        <div
          ref={contentAreaRef}
          tabIndex={0}
          className="flex-1 overflow-y-auto p-5 sm:p-6 bg-white space-y-4 font-mono text-xs sm:text-[13px] leading-relaxed text-[#2B2D42] select-text focus:outline-hidden"
          aria-label="Extracted source content"
        >
          {loading && (
            <div className="py-16 text-center space-y-3">
              <div className="size-7 border-3 border-[#D90429] border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-sm font-semibold text-[#2B2D42]">Loading full extracted source content...</p>
              <p className="text-xs text-[#8D99AE]">Retrieving raw text from database</p>
            </div>
          )}

          {!loading && error && (
            <div className="py-12 px-6 rounded-xl bg-rose-50 border border-rose-200 text-center space-y-3 max-w-lg mx-auto">
              <AlertCircle className="size-8 text-rose-600 mx-auto" />
              <h4 className="text-base font-bold text-rose-900">Failed to Load Source</h4>
              <p className="text-xs text-rose-700 leading-relaxed">{error}</p>
              <div className="pt-2">
                <NeuButton
                  variant="default"
                  size="sm"
                  onClick={handleRetry}
                  icon={RefreshCw}
                >
                  Retry Fetch
                </NeuButton>
              </div>
            </div>
          )}

          {!loading && !error && !fullContent && (
            <div className="py-16 text-center space-y-2 text-[#8D99AE] italic">
              <FileText className="size-8 mx-auto opacity-40" />
              <p>No extracted text available for this source record.</p>
            </div>
          )}

          {!loading && !error && fullContent && (
            <div className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-slate-900">
              {segments.map((segment, idx) => {
                if (segment.isHighlight) {
                  return (
                    <mark
                      key={idx}
                      id={`evidence-match-${segment.matchIndex}`}
                      className={cn(
                        'px-1 py-0.5 rounded font-medium transition-all duration-150',
                        segment.isActive
                          ? 'bg-amber-300 text-amber-950 ring-2 ring-amber-500 shadow-xs'
                          : 'bg-amber-100 text-amber-900'
                      )}
                    >
                      {segment.text}
                    </mark>
                  )
                }
                return <span key={idx}>{segment.text}</span>
              })}
            </div>
          )}
        </div>

        {/* =====================================================================
            5. FOOTER: Close Action
            ===================================================================== */}
        <footer className="px-5 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between shrink-0">
          <div className="text-[11px] text-[#8D99AE]">
            Press <kbd className="px-1.5 py-0.5 bg-white border border-slate-300 rounded text-[10px] font-mono">Esc</kbd> to close
          </div>
          <NeuButton variant="default" size="sm" onClick={onClose}>
            Close Viewer
          </NeuButton>
        </footer>
      </div>
    </div>
  )
}
