import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Compass,
  Globe,
  FileText,
  UploadCloud,
  HelpCircle,
  AlertCircle,
  CheckCircle2,
  Lock,
} from 'lucide-react'
import { GlassCard } from '@/components/common/GlassCard'
import { NeuButton } from '@/components/common/NeuButton'
import { NeuTextarea } from '@/components/common/NeuInput'
import { createResearch } from '@/services/researchService'

export function NewResearchPage() {
  const navigate = useNavigate()
  const [researchGoal, setResearchGoal] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setErrorMsg('')
    setSuccessMsg('')

    const trimmed = researchGoal.trim()
    if (!trimmed) {
      setErrorMsg('Please enter a specific research goal or question.')
      return
    }

    setIsSubmitting(true)

    try {
      const response = await createResearch({ research_goal: trimmed })
      if (response?.data?.id) {
        setSuccessMsg('Research session initialized in database!')
        setTimeout(() => {
          navigate(`/research/${response.data.id}`)
        }, 800)
      } else {
        setSuccessMsg('Research session created successfully!')
        setTimeout(() => {
          navigate('/history')
        }, 800)
      }
    } catch (err) {
      // If unauthenticated or backend error, provide explicit clear message
      if (err.status === 401) {
        setErrorMsg('Authentication token required to persist to live database. (Phase 3 Backend verifies Bearer tokens).')
      } else {
        setErrorMsg(err.message || 'Unable to create research session. Please check backend connection.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header Info */}
      <div className="space-y-1.5">
        <h2 className="text-2xl font-extrabold text-[#2B2D42] tracking-tight">
          Initialize Research Investigation
        </h2>
        <p className="text-sm text-[#8D99AE]">
          Define your research goal. ClarityX will cross-reference source material to reveal digital dark spots.
        </p>
      </div>

      {errorMsg && (
        <div className="p-4 rounded-2xl bg-[#EF233C]/10 border border-[#EF233C]/30 text-[#D90429] text-sm flex items-start gap-3">
          <AlertCircle className="size-5 shrink-0 mt-0.5" />
          <div>
            <strong>Session Creation Notice:</strong> {errorMsg}
          </div>
        </div>
      )}

      {successMsg && (
        <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm flex items-center gap-3">
          <CheckCircle2 className="size-5 shrink-0 text-emerald-600" />
          <span>{successMsg}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
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
          />

          {/* Helper Guidance Box */}
          <div className="p-4 rounded-xl bg-white/50 border border-[#8D99AE]/20 flex items-start gap-3 text-xs text-[#8D99AE]">
            <HelpCircle className="size-4 shrink-0 text-[#2B2D42] mt-0.5" />
            <div className="space-y-1">
              <strong className="text-[#2B2D42] block">Formulating an Effective Goal:</strong>
              <p>
                Be precise about the domain, subject, and timeline. The detection engine evaluates whether provided sources omit critical parameters (missing), reference superseded data (outdated), contradict each other (conflicting), or lack empirical backing (unverified).
              </p>
            </div>
          </div>
        </GlassCard>

        {/* Step 2: Source Extraction Workspace (Intentionally Marked Coming Soon) */}
        <GlassCard className="space-y-4 opacity-90">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-[#2B2D42] flex items-center gap-2">
                2. Input Sources for Cross-Verification
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded-md bg-amber-100 text-amber-800 border border-amber-200">
                  <Lock className="size-3" /> Coming in Phase V
                </span>
              </h3>
              <p className="text-xs text-[#8D99AE] mt-0.5">
                Multi-source extraction engine (Trafilatura & Jina Reader) will accept up to 5 sources in Phase 5.
              </p>
            </div>
          </div>

          {/* Disabled Source Tabs Placeholder */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="p-4 rounded-xl neu-raised border border-dashed border-[#8D99AE]/40 flex flex-col items-center justify-center text-center gap-2 text-[#8D99AE] cursor-not-allowed">
              <Globe className="size-6 text-[#8D99AE]" />
              <div className="font-semibold text-xs text-[#2B2D42]">Websites & URLs</div>
              <p className="text-[10px] text-[#8D99AE]">Auto-extraction via Trafilatura</p>
            </div>

            <div className="p-4 rounded-xl neu-raised border border-dashed border-[#8D99AE]/40 flex flex-col items-center justify-center text-center gap-2 text-[#8D99AE] cursor-not-allowed">
              <FileText className="size-6 text-[#8D99AE]" />
              <div className="font-semibold text-xs text-[#2B2D42]">Pasted Excerpts</div>
              <p className="text-[10px] text-[#8D99AE]">Manual text snippets & quotes</p>
            </div>

            <div className="p-4 rounded-xl neu-raised border border-dashed border-[#8D99AE]/40 flex flex-col items-center justify-center text-center gap-2 text-[#8D99AE] cursor-not-allowed">
              <UploadCloud className="size-6 text-[#8D99AE]" />
              <div className="font-semibold text-xs text-[#2B2D42]">Documents & PDFs</div>
              <p className="text-[10px] text-[#8D99AE]">Document parser & OCR</p>
            </div>
          </div>
        </GlassCard>

        {/* Submit Actions */}
        <div className="flex items-center justify-between pt-2">
          <NeuButton
            variant="ghost"
            type="button"
            onClick={() => navigate('/history')}
          >
            Cancel
          </NeuButton>

          <NeuButton
            variant="cta"
            size="lg"
            type="submit"
            disabled={isSubmitting || !researchGoal.trim()}
            icon={Compass}
          >
            {isSubmitting ? 'Creating Session...' : 'Initialize Research Session'}
          </NeuButton>
        </div>
      </form>
    </div>
  )
}

