import { Globe, FileText, File, ExternalLink, Trash2, Calendar, Clock } from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { SourceStatusBadge } from './SourceStatusBadge'

/**
 * Safely formats an ISO timestamp or date string.
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
 * SourceCard Component
 *
 * Displays a single ingested source preview with metadata,
 * extraction status, content preview excerpt, and delete action.
 *
 * @param {Object} props
 * @param {Object} props.source - SourcePreviewResponse object
 * @param {Function} props.onDelete - Callback when delete is confirmed
 * @param {boolean} [props.isDeleting=false] - Whether this source is currently being deleted
 */
export function SourceCard({ source, onDelete, isDeleting = false }) {
  const publishedFormatted = formatTimestamp(source.published_at)
  const accessedFormatted = formatTimestamp(source.accessed_at)

  const typeConfig = {
    website: { label: 'Website', icon: Globe },
    pasted_text: { label: 'Pasted Text', icon: FileText },
    document: { label: 'Document', icon: File },
  }

  const currentType = typeConfig[source.source_type] || { label: source.source_type || 'Source', icon: File }
  const TypeIcon = currentType.icon

  const handleDelete = () => {
    if (isDeleting) return
    const sourceLabel = source.source_code ? `[${source.source_code}] ` : ''
    const titleLabel = source.title ? `"${source.title}"` : 'this source'
    if (window.confirm(`Are you sure you want to delete ${sourceLabel}${titleLabel}? This will permanently remove it from the research session.`)) {
      onDelete(source.id)
    }
  }

  return (
    <GlassCard className="p-5 space-y-3.5 transition-all">
      {/* Header: Source Code, Title, Status, and Delete */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1.5 flex-1 min-w-[200px]">
          <div className="flex flex-wrap items-center gap-2">
            {source.source_code && (
              <span className="px-2 py-0.5 rounded-lg bg-[#2B2D42] text-[#EDF2F4] text-xs font-mono font-bold tracking-wide">
                {source.source_code}
              </span>
            )}
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-[#8D99AE]">
              <TypeIcon className="size-3.5" />
              {currentType.label}
            </span>
            <SourceStatusBadge status={source.extraction_status} />
          </div>

          <h4 className="text-base font-bold text-[#2B2D42] leading-snug">
            {source.title || 'Untitled Source'}
          </h4>

          {/* URL for website sources */}
          {source.url && source.source_type === 'website' && (
            <div className="pt-0.5">
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-[#8D99AE] hover:text-[#D90429] transition-colors truncate max-w-full"
                title={source.url}
              >
                <ExternalLink className="size-3 shrink-0" />
                <span className="truncate underline underline-offset-2">{source.url}</span>
              </a>
            </div>
          )}
        </div>

        {/* Delete Action */}
        <NeuButton
          variant="destructive"
          size="sm"
          onClick={handleDelete}
          disabled={isDeleting}
          icon={Trash2}
          title="Delete this source"
        >
          {isDeleting ? 'Deleting...' : 'Delete'}
        </NeuButton>
      </div>

      {/* Content Preview Box */}
      <div className="p-3.5 rounded-xl neu-inset bg-white/40 space-y-1">
        <div className="text-[11px] font-bold uppercase tracking-wider text-[#8D99AE]">
          Content Preview
        </div>
        <p className="text-xs text-[#2B2D42] leading-relaxed font-mono whitespace-pre-wrap break-words">
          {source.content_preview?.trim() || (
            <span className="italic text-[#8D99AE]">
              {source.extraction_status === 'failed'
                ? 'Extraction failed to produce usable content.'
                : 'No content preview available for this source.'}
            </span>
          )}
        </p>
      </div>

      {/* Metadata Footer: Timestamps */}
      {(publishedFormatted || accessedFormatted) && (
        <div className="flex flex-wrap items-center gap-4 text-[11px] text-[#8D99AE] pt-1 border-t border-[#8D99AE]/15">
          {publishedFormatted && (
            <span className="flex items-center gap-1" title="Publication Date">
              <Calendar className="size-3" />
              Published: {publishedFormatted}
            </span>
          )}
          {accessedFormatted && (
            <span className="flex items-center gap-1" title="Accessed Date">
              <Clock className="size-3" />
              Accessed: {accessedFormatted}
            </span>
          )}
        </div>
      )}
    </GlassCard>
  )
}

