import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Compass,
  Globe,
  FileText,
  UploadCloud,
  AlertCircle,
  CheckCircle2,
  Loader2,
  Trash2,
  Plus,
  RotateCcw,
  ArrowRight,
  File,
} from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { NeuInput, NeuTextarea } from '@/components/common/NeuInput'
import { createResearch } from '@/services/researchService'
import {
  addWebsiteSource,
  addPastedTextSource,
  addDocumentSource,
} from '@/services/sourceService'
import { formatFileSize } from '@/lib/formatters'
import {
  MAX_SOURCES,
  MAX_DOCUMENT_SIZE,
  MAX_PASTED_TEXT_LENGTH,
  validateWebsiteSource,
  validatePastedTextSource,
  validateDocumentSource,
  executeSessionInitialization,
} from '@/lib/newResearchWorkflow'

export function NewResearchPage() {
  const navigate = useNavigate()
  const fileInputRef = useRef(null)

  // Research Goal State
  const [researchGoal, setResearchGoal] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

  // Preserved session ID on partial failure to avoid duplicate session creation on retry
  const [activeSessionId, setActiveSessionId] = useState(null)

  // Prepared in-memory sources list
  const [preparedSources, setPreparedSources] = useState([])

  // Source Type Tab: 'website' | 'pasted_text' | 'document'
  const [sourceTab, setSourceTab] = useState('website')

  // Source Input Form States
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [textTitle, setTextTitle] = useState('')
  const [textContent, setTextContent] = useState('')
  const [docTitle, setDocTitle] = useState('')
  const [docFile, setDocFile] = useState(null)
  const [sourceInputError, setSourceInputError] = useState('')

  const isAtCapacity = preparedSources.length >= MAX_SOURCES
  const hasFailedSources = preparedSources.some((s) => s.status === 'failed')

  // --- SOURCE PREPARATION HANDLERS ---

  const handleAddWebsite = (e) => {
    if (e) e.preventDefault()
    setSourceInputError('')

    const result = validateWebsiteSource(websiteUrl, preparedSources)
    if (!result.valid) {
      setSourceInputError(result.error)
      return
    }

    setPreparedSources((prev) => [...prev, result.source])
    setWebsiteUrl('')
  }

  const handleAddPastedText = (e) => {
    if (e) e.preventDefault()
    setSourceInputError('')

    const result = validatePastedTextSource(
      { text: textContent, title: textTitle },
      preparedSources
    )
    if (!result.valid) {
      setSourceInputError(result.error)
      return
    }

    setPreparedSources((prev) => [...prev, result.source])
    setTextContent('')
    setTextTitle('')
  }

  const handleFileChange = (e) => {
    setSourceInputError('')
    const file = e.target.files?.[0]
    if (!file) return

    const lowerName = file.name.toLowerCase()
    if (!lowerName.endsWith('.pdf') && !lowerName.endsWith('.docx')) {
      setSourceInputError('Unsupported file type. Only PDF and DOCX files are supported.')
      e.target.value = ''
      setDocFile(null)
      return
    }

    if (file.size > MAX_DOCUMENT_SIZE) {
      setSourceInputError(
        `Selected document (${formatFileSize(file.size)}) exceeds the maximum allowable limit of 10 MB.`
      )
      e.target.value = ''
      setDocFile(null)
      return
    }

    setDocFile(file)
  }

  const handleAddDocument = (e) => {
    if (e) e.preventDefault()
    setSourceInputError('')

    const result = validateDocumentSource(
      { file: docFile, title: docTitle },
      preparedSources
    )
    if (!result.valid) {
      setSourceInputError(result.error)
      return
    }

    setPreparedSources((prev) => [...prev, result.source])
    setDocFile(null)
    setDocTitle('')
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleRemoveSource = (id) => {
    if (isSubmitting) return
    setPreparedSources((prev) => prev.filter((s) => s.id !== id))
    setSourceInputError('')
  }

  // --- INITIALIZATION AND RETRY WORKFLOW ---

  const handleInitialize = async (e) => {
    if (e) e.preventDefault()
    setErrorMsg('')
    setSuccessMsg('')

    const trimmedGoal = researchGoal.trim()
    if (!trimmedGoal) {
      setErrorMsg('Please enter a specific research goal or question.')
      return
    }

    setIsSubmitting(true)

    try {
      const result = await executeSessionInitialization({
        researchGoal: trimmedGoal,
        preparedSources,
        activeSessionId,
        createResearchFn: createResearch,
        addWebsiteSourceFn: addWebsiteSource,
        addPastedTextSourceFn: addPastedTextSource,
        addDocumentSourceFn: addDocumentSource,
        onSourceStatusChange: (updated) => setPreparedSources(updated),
      })

      if (result.success) {
        setActiveSessionId(result.sessionId)
        const sourceNotice =
          preparedSources.length > 0
            ? ` with ${preparedSources.length} source(s)`
            : ''
        setSuccessMsg(`Research session initialized successfully${sourceNotice}! Redirecting to workspace...`)
        setTimeout(() => {
          navigate(`/research/${result.sessionId}`)
        }, 900)
      } else {
        // Partial or total upload failure
        setActiveSessionId(result.sessionId)
        setPreparedSources(result.updatedSources)
        setErrorMsg(
          `Research session created (${result.sessionId.slice(0, 8)}...), but ${result.failedCount} source(s) failed to extract. You can retry failed sources or proceed directly to the session workspace.`
        )
      }
    } catch (err) {
      if (err.status === 401) {
        setErrorMsg('Authentication token required to persist to live database.')
      } else {
        setErrorMsg(err.message || 'Unable to initialize research session. Please check backend connection.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header Info */}
      <div>
        <h2 className="text-2xl font-extrabold text-[#2B2D42] tracking-tight">
          Initialize Research Investigation
        </h2>
      </div>

      {/* Global Alerts */}
      {errorMsg && (
        <div className="p-4 rounded-2xl bg-[#EF233C]/10 border border-[#EF233C]/30 text-[#D90429] text-sm flex items-start gap-3">
          <AlertCircle className="size-5 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <strong>Session Notice:</strong>
            <p>{errorMsg}</p>
          </div>
        </div>
      )}

      {successMsg && (
        <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm flex items-center gap-3">
          <CheckCircle2 className="size-5 shrink-0 text-emerald-600" />
          <span>{successMsg}</span>
        </div>
      )}

      <form onSubmit={handleInitialize} className="space-y-6">
        {/* Step 1: Research Goal */}
        <GlassCard className="space-y-4">
          <div className="flex items-center justify-between">
            <label
              htmlFor="research_goal"
              className="text-sm font-bold text-[#2B2D42] flex items-center gap-2"
            >
              1. Research Objective & Central Hypothesis
              <span className="text-[#D90429]">*</span>
            </label>
            <span className="text-xs text-[#8D99AE]">
              {researchGoal.length} / 5000 characters
            </span>
          </div>

          <NeuTextarea
            id="research_goal"
            rows={4}
            value={researchGoal}
            onChange={(e) => setResearchGoal(e.target.value)}
            placeholder="e.g. Determine whether solid-state battery commercialization claims for 2027 are supported by verifiable manufacturing milestones or conflict with raw material supply realities."
            required
            disabled={isSubmitting || Boolean(activeSessionId)}
          />
        </GlassCard>

        {/* Step 2: Sources Ingestion Workspace */}
        <GlassCard className="space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div>
              <h3 className="text-sm font-bold text-[#2B2D42] flex items-center gap-2">
                2. Add Research Sources
                <span
                  className={`inline-flex items-center text-[10px] font-bold px-2 py-0.5 rounded-full border shadow-xs ${
                    isAtCapacity
                      ? 'bg-amber-100 text-amber-800 border-amber-300'
                      : 'bg-white text-[#2B2D42] border-[#8D99AE]/30'
                  }`}
                >
                  {preparedSources.length} / {MAX_SOURCES} sources
                </span>
              </h3>
            </div>

            {/* Source Tab Selector */}
            <div className="flex items-center gap-1.5 p-1 rounded-xl bg-[#2B2D42]/5 border border-[#8D99AE]/20">
              <button
                type="button"
                onClick={() => {
                  setSourceTab('website')
                  setSourceInputError('')
                }}
                disabled={isSubmitting}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  sourceTab === 'website'
                    ? 'bg-[#2B2D42] text-[#EDF2F4] shadow-xs'
                    : 'text-[#8D99AE] hover:text-[#2B2D42]'
                }`}
              >
                <Globe className="size-3.5" />
                Websites
              </button>

              <button
                type="button"
                onClick={() => {
                  setSourceTab('pasted_text')
                  setSourceInputError('')
                }}
                disabled={isSubmitting}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  sourceTab === 'pasted_text'
                    ? 'bg-[#2B2D42] text-[#EDF2F4] shadow-xs'
                    : 'text-[#8D99AE] hover:text-[#2B2D42]'
                }`}
              >
                <FileText className="size-3.5" />
                Pasted Text
              </button>

              <button
                type="button"
                onClick={() => {
                  setSourceTab('document')
                  setSourceInputError('')
                }}
                disabled={isSubmitting}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  sourceTab === 'document'
                    ? 'bg-[#2B2D42] text-[#EDF2F4] shadow-xs'
                    : 'text-[#8D99AE] hover:text-[#2B2D42]'
                }`}
              >
                <UploadCloud className="size-3.5" />
                Documents
              </button>
            </div>
          </div>

          {/* Source Input Error */}
          {sourceInputError && (
            <div className="p-3 rounded-xl bg-[#EF233C]/10 border border-[#EF233C]/30 text-[#D90429] text-xs flex items-center gap-2">
              <AlertCircle className="size-4 shrink-0" />
              <span>{sourceInputError}</span>
            </div>
          )}

          {/* Tab 1: Websites & URLs */}
          {sourceTab === 'website' && (
            <div className="p-4 rounded-xl bg-white/70 border border-[#8D99AE]/20 space-y-3">
              <div className="text-xs font-bold text-[#2B2D42] flex items-center gap-1.5">
                <Globe className="size-4 text-[#2B2D42]" />
                Target Web Page URL
              </div>
              <div className="flex flex-col sm:flex-row gap-2.5">
                <div className="flex-1">
                  <NeuInput
                    type="url"
                    value={websiteUrl}
                    onChange={(e) => {
                      setWebsiteUrl(e.target.value)
                      if (sourceInputError) setSourceInputError('')
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        handleAddWebsite()
                      }
                    }}
                    placeholder="https://example.com/article-or-report"
                    disabled={isSubmitting || isAtCapacity}
                  />
                </div>
                <NeuButton
                  type="button"
                  onClick={handleAddWebsite}
                  disabled={isSubmitting || isAtCapacity || !websiteUrl.trim()}
                  icon={Plus}
                  variant="secondary"
                  size="md"
                >
                  Add URL
                </NeuButton>
              </div>
            </div>
          )}

          {/* Tab 2: Pasted Text */}
          {sourceTab === 'pasted_text' && (
            <div className="p-4 rounded-xl bg-white/70 border border-[#8D99AE]/20 space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-xs font-bold text-[#2B2D42] flex items-center gap-1.5">
                  <FileText className="size-4 text-[#2B2D42]" />
                  Pasted Research Text
                </div>
                <span className="text-[11px] text-[#8D99AE]">
                  {textContent.length} / {MAX_PASTED_TEXT_LENGTH.toLocaleString()} chars
                </span>
              </div>

              <NeuInput
                type="text"
                value={textTitle}
                onChange={(e) => setTextTitle(e.target.value)}
                placeholder="Source Title / Label (optional, e.g. Q3 2026 Earnings Transcript Excerpt)"
                disabled={isSubmitting || isAtCapacity}
              />

              <NeuTextarea
                rows={3}
                value={textContent}
                onChange={(e) => {
                  setTextContent(e.target.value)
                  if (sourceInputError) setSourceInputError('')
                }}
                placeholder="Paste research excerpts, interview notes, or text snippets here..."
                disabled={isSubmitting || isAtCapacity}
              />

              <div className="flex items-center justify-end pt-1">
                <NeuButton
                  type="button"
                  onClick={handleAddPastedText}
                  disabled={isSubmitting || isAtCapacity || !textContent.trim()}
                  icon={Plus}
                  variant="secondary"
                  size="md"
                >
                  Add Pasted Text
                </NeuButton>
              </div>
            </div>
          )}

          {/* Tab 3: Documents & PDFs */}
          {sourceTab === 'document' && (
            <div className="p-4 rounded-xl bg-white/70 border border-[#8D99AE]/20 space-y-3">
              <div className="text-xs font-bold text-[#2B2D42] flex items-center gap-1.5">
                <UploadCloud className="size-4 text-[#2B2D42]" />
                Upload PDF or DOCX Document
              </div>

              <NeuInput
                type="text"
                value={docTitle}
                onChange={(e) => setDocTitle(e.target.value)}
                placeholder="Document Title (optional, defaults to filename)"
                disabled={isSubmitting || isAtCapacity}
              />

              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={handleFileChange}
                disabled={isSubmitting || isAtCapacity}
                className="hidden"
                id="research-doc-input"
              />

              <label
                htmlFor="research-doc-input"
                className={`p-4 rounded-xl border border-dashed border-[#8D99AE]/40 flex flex-col items-center justify-center text-center gap-2 cursor-pointer transition-colors ${
                  isAtCapacity || isSubmitting
                    ? 'opacity-60 cursor-not-allowed bg-slate-50'
                    : 'hover:bg-white/80 bg-white/40'
                }`}
              >
                <UploadCloud className="size-6 text-[#2B2D42]" />
                {docFile ? (
                  <div className="flex items-center gap-2 text-xs font-semibold text-[#2B2D42]">
                    <File className="size-4 text-emerald-600" />
                    <span>{docFile.name}</span>
                    <span className="text-[#8D99AE] font-normal">({formatFileSize(docFile.size)})</span>
                  </div>
                ) : (
                  <div>
                    <span className="text-xs font-semibold text-[#2B2D42]">
                      Click to select a PDF or DOCX file
                    </span>
                    <p className="text-[10px] text-[#8D99AE] mt-0.5">Maximum file size: 10 MB</p>
                  </div>
                )}
              </label>

              <div className="flex items-center justify-end pt-1">
                <NeuButton
                  type="button"
                  onClick={handleAddDocument}
                  disabled={isSubmitting || isAtCapacity || !docFile}
                  icon={Plus}
                  variant="secondary"
                  size="md"
                >
                  Add Document
                </NeuButton>
              </div>
            </div>
          )}

          {/* At Capacity Notice */}
          {isAtCapacity && (
            <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-center gap-2">
              <AlertCircle className="size-4 shrink-0 text-amber-600" />
              <span>
                Maximum 5 sources reached. Remove an existing source below if you need to add a different one.
              </span>
            </div>
          )}

          {/* Added Sources Preview List */}
          <div className="space-y-2.5 pt-2 border-t border-[#8D99AE]/15">
            <div className="flex items-center justify-between">
              <div className="text-xs font-bold text-[#2B2D42]">
                Prepared Sources ({preparedSources.length} / {MAX_SOURCES})
              </div>
            </div>

            {preparedSources.length === 0 ? (
              <div className="p-4 rounded-xl border border-dashed border-[#8D99AE]/30 text-center text-xs text-[#8D99AE]">
                No sources prepared yet. You can add up to 5 sources above for cross-verification, or initialize the session and add sources later.
              </div>
            ) : (
              <div className="space-y-2">
                {preparedSources.map((source, index) => {
                  const Icon =
                    source.type === 'website'
                      ? Globe
                      : source.type === 'pasted_text'
                      ? FileText
                      : UploadCloud

                  const typeLabel =
                    source.type === 'website'
                      ? 'Website'
                      : source.type === 'pasted_text'
                      ? 'Pasted Text'
                      : 'Document'

                  return (
                    <div
                      key={source.id || index}
                      className="p-3 rounded-xl neu-raised border border-[#8D99AE]/20 bg-white/60 flex items-start justify-between gap-3"
                    >
                      <div className="flex items-start gap-3 min-w-0">
                        <div className="p-2 rounded-lg bg-white text-[#2B2D42] shadow-xs shrink-0 mt-0.5">
                          <Icon className="size-4" />
                        </div>
                        <div className="space-y-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xs font-bold text-[#2B2D42] truncate">
                              {source.title}
                            </span>
                            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-[#2B2D42]/5 text-[#8D99AE] border border-[#8D99AE]/20">
                              {typeLabel}
                            </span>
                          </div>

                          <div className="text-[11px] text-[#8D99AE] truncate">
                            {source.type === 'website' && source.url}
                            {source.type === 'pasted_text' && `${source.charCount} characters`}
                            {source.type === 'document' &&
                              `${source.file?.name} • ${formatFileSize(source.fileSize)}`}
                          </div>

                          {source.error && (
                            <p className="text-[11px] text-[#D90429] font-medium">
                              Error: {source.error}
                            </p>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {/* Status Badge */}
                        {source.status === 'uploading' && (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
                            <Loader2 className="size-3 animate-spin text-amber-600" />
                            Ingesting...
                          </span>
                        )}
                        {source.status === 'success' && (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <CheckCircle2 className="size-3 text-emerald-600" />
                            Extracted
                          </span>
                        )}
                        {source.status === 'failed' && (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-[#EF233C]/10 text-[#D90429] border border-[#EF233C]/30">
                            <AlertCircle className="size-3 text-[#D90429]" />
                            Failed
                          </span>
                        )}
                        {source.status === 'pending' && (
                          <span className="inline-flex items-center text-[10px] font-medium px-2 py-0.5 rounded-md bg-[#2B2D42]/5 text-[#8D99AE] border border-[#8D99AE]/20">
                            Ready
                          </span>
                        )}

                        {/* Remove Action */}
                        <button
                          type="button"
                          onClick={() => handleRemoveSource(source.id)}
                          disabled={isSubmitting || source.status === 'success'}
                          title={
                            source.status === 'success'
                              ? 'Source already extracted'
                              : 'Remove prepared source'
                          }
                          className="p-1.5 rounded-lg text-[#8D99AE] hover:text-[#D90429] hover:bg-[#EF233C]/10 disabled:opacity-30 disabled:pointer-events-none transition-colors"
                        >
                          <Trash2 className="size-4" />
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </GlassCard>

        {/* Action Buttons */}
        <div className="flex items-center justify-between pt-2">
          <NeuButton
            variant="ghost"
            type="button"
            disabled={isSubmitting}
            onClick={() => navigate('/history')}
          >
            Cancel
          </NeuButton>

          <div className="flex items-center gap-3">
            {activeSessionId && hasFailedSources ? (
              <>
                <NeuButton
                  variant="secondary"
                  type="button"
                  disabled={isSubmitting}
                  onClick={() => navigate(`/research/${activeSessionId}`)}
                  icon={ArrowRight}
                >
                  Proceed to Session Workspace
                </NeuButton>

                <NeuButton
                  variant="cta"
                  type="submit"
                  disabled={isSubmitting}
                  icon={RotateCcw}
                >
                  {isSubmitting ? 'Retrying Ingestion...' : 'Retry Failed Sources'}
                </NeuButton>
              </>
            ) : (
              <NeuButton
                variant="cta"
                size="lg"
                type="submit"
                disabled={isSubmitting || !researchGoal.trim()}
                icon={Compass}
              >
                {isSubmitting
                  ? preparedSources.length > 0
                    ? 'Initializing Session & Sources...'
                    : 'Creating Session...'
                  : 'Initialize Research Session'}
              </NeuButton>
            )}
          </div>
        </div>
      </form>
    </div>
  )
}
