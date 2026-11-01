import { useState } from 'react'
import {
  Globe,
  FileText,
  UploadCloud,
  Plus,
  AlertCircle,
  X,
  File,
} from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { NeuInput, NeuTextarea } from '@/components/common/NeuInput'
import { isValidUrl, formatFileSize } from '@/lib/formatters'
import {
  addWebsiteSource,
  addPastedTextSource,
  addDocumentSource,
} from '@/services/sourceService'

const MAX_DOCUMENT_SIZE = 10 * 1024 * 1024 // 10 MB in bytes
const MAX_SOURCES_LIMIT = 5

/**
 * AddSourceForm Component
 *
 * Provides tabbed forms for ingesting website URLs, pasted text,
 * and PDF/DOCX documents into a research session.
 *
 * @param {Object} props
 * @param {string} props.researchId - Active research session UUID
 * @param {number} [props.currentSourceCount=0] - Number of existing sources
 * @param {Function} props.onSuccess - Callback invoked when a source is successfully added
 * @param {Function} [props.onCancel] - Optional callback to cancel/close the form
 */
export function AddSourceForm({
  researchId,
  currentSourceCount = 0,
  onSuccess,
  onCancel,
}) {
  const [sourceType, setSourceType] = useState('website') // 'website' | 'pasted_text' | 'document'
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  // Website Form State
  const [websiteUrl, setWebsiteUrl] = useState('')

  // Pasted Text Form State
  const [textTitle, setTextTitle] = useState('')
  const [textContent, setTextContent] = useState('')

  // Document Form State
  const [docTitle, setDocTitle] = useState('')
  const [docFile, setDocFile] = useState(null)

  const isAtCapacity = currentSourceCount >= MAX_SOURCES_LIMIT

  // Handle Website Source Submission
  const handleWebsiteSubmit = async (e) => {
    e.preventDefault()
    setErrorMsg('')

    const trimmed = websiteUrl.trim()
    if (!trimmed) {
      setErrorMsg('Please enter a target website URL.')
      return
    }

    if (!isValidUrl(trimmed)) {
      setErrorMsg('Please enter a valid HTTP or HTTPS URL (e.g. https://example.com/article).')
      return
    }

    setIsSubmitting(true)
    try {
      const response = await addWebsiteSource(researchId, { url: trimmed })
      setWebsiteUrl('')
      if (onSuccess) {
        onSuccess(response?.data)
      }
    } catch (err) {
      setErrorMsg(err.message || 'Failed to extract content from the website.')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Handle Pasted Text Submission
  const handleTextSubmit = async (e) => {
    e.preventDefault()
    setErrorMsg('')

    const trimmedText = textContent.trim()
    if (!trimmedText) {
      setErrorMsg('Pasted text content must not be empty or whitespace only.')
      return
    }

    if (trimmedText.length > 1048576) {
      setErrorMsg('Pasted text exceeds the maximum character limit (1,048,576 characters).')
      return
    }

    setIsSubmitting(true)
    try {
      const response = await addPastedTextSource(researchId, {
        text: trimmedText,
        title: textTitle.trim() || null,
      })
      setTextContent('')
      setTextTitle('')
      if (onSuccess) {
        onSuccess(response?.data)
      }
    } catch (err) {
      setErrorMsg(err.message || 'Failed to save pasted text source.')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Handle Document Selection
  const handleFileChange = (e) => {
    setErrorMsg('')
    const file = e.target.files?.[0]
    if (!file) return

    const lowerName = file.name.toLowerCase()
    const isPdf = lowerName.endsWith('.pdf')
    const isDocx = lowerName.endsWith('.docx')

    if (!isPdf && !isDocx) {
      setErrorMsg('Unsupported file type. Only PDF and DOCX files are supported.')
      e.target.value = ''
      setDocFile(null)
      return
    }

    if (file.size > MAX_DOCUMENT_SIZE) {
      setErrorMsg(`Selected document (${formatFileSize(file.size)}) exceeds the maximum allowable limit of 10 MB.`)
      e.target.value = ''
      setDocFile(null)
      return
    }

    setDocFile(file)
  }

  // Handle Document Submission
  const handleDocumentSubmit = async (e) => {
    e.preventDefault()
    setErrorMsg('')

    if (!docFile) {
      setErrorMsg('Please select a PDF or DOCX document to upload.')
      return
    }

    setIsSubmitting(true)
    try {
      const response = await addDocumentSource(researchId, {
        file: docFile,
        title: docTitle.trim() || null,
      })
      setDocFile(null)
      setDocTitle('')
      if (onSuccess) {
        onSuccess(response?.data)
      }
    } catch (err) {
      setErrorMsg(err.message || 'Failed to upload and extract document.')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isAtCapacity) {
    return (
      <GlassCard className="p-6 border-l-4 border-l-amber-500 space-y-2">
        <div className="flex items-center gap-2 text-sm font-bold text-[#2B2D42]">
          <AlertCircle className="size-4 text-amber-600" />
          Maximum Source Capacity Reached (5/5)
        </div>
        <p className="text-xs text-[#8D99AE] leading-relaxed">
          This research session has reached the maximum allowed limit of 5 sources. To ingest another source, please delete an existing one first.
        </p>
      </GlassCard>
    )
  }

  return (
    <GlassCard className="p-6 space-y-5 border-2 border-[#D90429]/20">
      {/* Header and Type Selection */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#8D99AE]/15 pb-4">
        <div className="space-y-0.5">
          <h3 className="text-base font-bold text-[#2B2D42] flex items-center gap-2">
            <Plus className="size-4 text-[#D90429]" />
            Ingest New Research Source
          </h3>
          <p className="text-xs text-[#8D99AE]">
            Add evidence material ({currentSourceCount}/5 sources used)
          </p>
        </div>

        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="p-1 rounded-lg text-[#8D99AE] hover:text-[#2B2D42] hover:bg-white/50 transition-colors"
            title="Cancel"
          >
            <X className="size-4" />
          </button>
        )}
      </div>

      {/* Source Type Selector */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => {
            setSourceType('website')
            setErrorMsg('')
          }}
          disabled={isSubmitting}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
            sourceType === 'website'
              ? 'bg-[#2B2D42] text-[#EDF2F4] shadow-sm'
              : 'neu-interactive text-[#8D99AE] hover:text-[#2B2D42]'
          }`}
        >
          <Globe className="size-3.5" />
          Website URL
        </button>

        <button
          type="button"
          onClick={() => {
            setSourceType('pasted_text')
            setErrorMsg('')
          }}
          disabled={isSubmitting}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
            sourceType === 'pasted_text'
              ? 'bg-[#2B2D42] text-[#EDF2F4] shadow-sm'
              : 'neu-interactive text-[#8D99AE] hover:text-[#2B2D42]'
          }`}
        >
          <FileText className="size-3.5" />
          Pasted Text
        </button>

        <button
          type="button"
          onClick={() => {
            setSourceType('document')
            setErrorMsg('')
          }}
          disabled={isSubmitting}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
            sourceType === 'document'
              ? 'bg-[#2B2D42] text-[#EDF2F4] shadow-sm'
              : 'neu-interactive text-[#8D99AE] hover:text-[#2B2D42]'
          }`}
        >
          <UploadCloud className="size-3.5" />
          Upload PDF / DOCX
        </button>
      </div>

      {/* Error Notice */}
      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-[#EF233C]/10 border border-[#EF233C]/30 text-[#D90429] text-xs flex items-start gap-2.5">
          <AlertCircle className="size-4 shrink-0 mt-0.5" />
          <div className="leading-relaxed">
            <strong>Error:</strong> {errorMsg}
          </div>
        </div>
      )}

      {/* Website URL Form */}
      {sourceType === 'website' && (
        <form onSubmit={handleWebsiteSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-[#2B2D42]">
              Target Website URL <span className="text-[#D90429]">*</span>
            </label>
            <NeuInput
              type="url"
              placeholder="https://example.com/research-article"
              value={websiteUrl}
              onChange={(e) => setWebsiteUrl(e.target.value)}
              disabled={isSubmitting}
              icon={Globe}
              required
            />
            <p className="text-[11px] text-[#8D99AE]">
              Trafilatura and Jina Reader will extract article body text, stripping boilerplate and ads.
            </p>
          </div>

          <div className="flex items-center justify-end gap-2 pt-2">
            {onCancel && (
              <NeuButton
                variant="ghost"
                size="sm"
                onClick={onCancel}
                disabled={isSubmitting}
              >
                Cancel
              </NeuButton>
            )}
            <NeuButton
              type="submit"
              variant="cta"
              size="sm"
              disabled={isSubmitting}
              icon={Globe}
            >
              {isSubmitting ? 'Extracting Website...' : 'Add Website Source'}
            </NeuButton>
          </div>
        </form>
      )}

      {/* Pasted Text Form */}
      {sourceType === 'pasted_text' && (
        <form onSubmit={handleTextSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-[#2B2D42]">
              Source Title <span className="text-[#8D99AE] font-normal">(Optional)</span>
            </label>
            <NeuInput
              type="text"
              placeholder="e.g. Expert Interview Transcript, Regulatory Notice"
              value={textTitle}
              onChange={(e) => setTextTitle(e.target.value)}
              disabled={isSubmitting}
              maxLength={255}
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold text-[#2B2D42]">
                Source Content Text <span className="text-[#D90429]">*</span>
              </label>
              <span className="text-[10px] text-[#8D99AE] font-mono">
                {textContent.length.toLocaleString()} / 1,048,576 chars
              </span>
            </div>
            <NeuTextarea
              placeholder="Paste text content, excerpts, transcripts, or notes here..."
              value={textContent}
              onChange={(e) => setTextContent(e.target.value)}
              disabled={isSubmitting}
              rows={6}
              required
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-2">
            {onCancel && (
              <NeuButton
                variant="ghost"
                size="sm"
                onClick={onCancel}
                disabled={isSubmitting}
              >
                Cancel
              </NeuButton>
            )}
            <NeuButton
              type="submit"
              variant="cta"
              size="sm"
              disabled={isSubmitting}
              icon={FileText}
            >
              {isSubmitting ? 'Saving Text...' : 'Add Pasted Text'}
            </NeuButton>
          </div>
        </form>
      )}

      {/* Document Upload Form */}
      {sourceType === 'document' && (
        <form onSubmit={handleDocumentSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-[#2B2D42]">
              Document Title <span className="text-[#8D99AE] font-normal">(Optional)</span>
            </label>
            <NeuInput
              type="text"
              placeholder="e.g. Q3 Financial Statement, Clinical Study"
              value={docTitle}
              onChange={(e) => setDocTitle(e.target.value)}
              disabled={isSubmitting}
              maxLength={255}
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-bold text-[#2B2D42]">
              Select File (PDF or DOCX, max 10 MB) <span className="text-[#D90429]">*</span>
            </label>
            <div className="p-4 rounded-xl border-2 border-dashed border-[#8D99AE]/30 bg-white/30 text-center space-y-2">
              <input
                type="file"
                id="source-file-upload"
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={handleFileChange}
                disabled={isSubmitting}
                className="hidden"
              />
              {docFile ? (
                <div className="flex items-center justify-between p-2.5 rounded-lg bg-white/70 border border-[#8D99AE]/20">
                  <div className="flex items-center gap-2 min-w-0">
                    <File className="size-4 text-[#D90429] shrink-0" />
                    <span className="text-xs font-bold text-[#2B2D42] truncate">
                      {docFile.name}
                    </span>
                    <span className="text-[11px] text-[#8D99AE] shrink-0 font-mono">
                      ({formatFileSize(docFile.size)})
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setDocFile(null)}
                    disabled={isSubmitting}
                    className="p-1 text-[#8D99AE] hover:text-[#D90429] transition-colors"
                    title="Remove file"
                  >
                    <X className="size-4" />
                  </button>
                </div>
              ) : (
                <label
                  htmlFor="source-file-upload"
                  className="flex flex-col items-center justify-center gap-1.5 cursor-pointer py-2 text-[#8D99AE] hover:text-[#2B2D42] transition-colors"
                >
                  <UploadCloud className="size-7 text-[#D90429]" />
                  <span className="text-xs font-semibold text-[#2B2D42]">
                    Click to browse or choose a file
                  </span>
                  <span className="text-[11px] text-[#8D99AE]">
                    Supported formats: PDF, DOCX (up to 10 MB)
                  </span>
                </label>
              )}
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-2">
            {onCancel && (
              <NeuButton
                variant="ghost"
                size="sm"
                onClick={onCancel}
                disabled={isSubmitting}
              >
                Cancel
              </NeuButton>
            )}
            <NeuButton
              type="submit"
              variant="cta"
              size="sm"
              disabled={isSubmitting || !docFile}
              icon={UploadCloud}
            >
              {isSubmitting ? 'Uploading & Extracting...' : 'Upload Document'}
            </NeuButton>
          </div>
        </form>
      )}
    </GlassCard>
  )
}
