import { ExternalLink, Check, X, FileText } from 'lucide-react'
import { isValidUrl } from '@/lib/formatters'
import { cn } from '@/lib/utils'

/**
 * EvidenceQuote Component
 *
 * Displays a single evidence reference quote connected to a research source.
 * Includes source code badge, resolved source title, evidence type indicator,
 * exact verbatim quotation text, and safe external website link.
 *
 * @param {Object} props
 * @param {Object} props.evidence - EvidenceReferenceResponse object
 * @param {Object} [props.source] - Resolved SourcePreviewResponse object (if available)
 * @param {string} [props.className]
 */
export function EvidenceQuote({ evidence, source, className }) {
  if (!evidence) return null

  const sourceCode = evidence.source_code || source?.source_code || ''
  const sourceTitle = source?.title?.trim() || 'Untitled Source'
  const isWebsite = source?.source_type === 'website'
  const canLink = isWebsite && source?.url && isValidUrl(source.url)

  const evidenceType = (evidence.evidence_type || 'supporting').toLowerCase()
  const typeConfig = {
    supporting: {
      label: 'Supporting',
      icon: Check,
      style: 'bg-emerald-50 text-emerald-700 border-emerald-200/70',
    },
    contradicting: {
      label: 'Contradicting',
      icon: X,
      style: 'bg-rose-50 text-rose-700 border-rose-200/70',
    },
    contextual: {
      label: 'Contextual',
      icon: FileText,
      style: 'bg-blue-50 text-blue-700 border-blue-200/70',
    },
  }

  const currentType = typeConfig[evidenceType] || {
    label: evidenceType.charAt(0).toUpperCase() + evidenceType.slice(1),
    icon: FileText,
    style: 'bg-slate-100 text-slate-600 border-slate-200',
  }
  const TypeIcon = currentType.icon

  return (
    <div
      className={cn(
        'p-3.5 rounded-xl border border-[#8D99AE]/20 bg-white/70 space-y-2.5 transition-all text-left shadow-xs',
        className
      )}
    >
      {/* Evidence Source & Type Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          {sourceCode && (
            <span className="px-1.5 py-0.5 rounded bg-[#2B2D42] text-[#EDF2F4] text-[10px] font-mono font-bold tracking-wide shrink-0">
              {sourceCode}
            </span>
          )}

          {canLink ? (
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs font-semibold text-[#2B2D42] hover:text-[#D90429] transition-colors truncate max-w-[280px] sm:max-w-[360px]"
              title={`Open source: ${sourceTitle} (${source.url})`}
            >
              <span className="truncate underline underline-offset-2">{sourceTitle}</span>
              <ExternalLink className="size-3 shrink-0 text-[#8D99AE]" />
            </a>
          ) : (
            <span
              className="text-xs font-semibold text-[#2B2D42] truncate max-w-[280px] sm:max-w-[360px]"
              title={sourceTitle}
            >
              {sourceTitle}
            </span>
          )}
        </div>

        {/* Evidence Role Badge */}
        <span
          className={cn(
            'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border shrink-0',
            currentType.style
          )}
        >
          <TypeIcon className="size-3 shrink-0" />
          {currentType.label}
        </span>
      </div>

      {/* Verbatim Evidence Excerpt */}
      <div className="neu-inset bg-white/40 p-3 rounded-lg border border-[#8D99AE]/10">
        <blockquote className="text-xs text-[#2B2D42] font-mono leading-relaxed whitespace-pre-wrap break-words italic">
          &ldquo;{evidence.evidence_text}&rdquo;
        </blockquote>
      </div>
    </div>
  )
}

