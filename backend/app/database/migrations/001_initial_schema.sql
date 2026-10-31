-- =============================================================================
-- ClarityX – Initial Database Schema Migration
-- Migration: 001_initial_schema.sql
-- Description: Creates the 6 core application tables, cross-session validation
--              triggers, auth.users profile sync trigger, indexes, and RLS policies.
-- =============================================================================

-- Ensure UUID generation functions are available
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- 1. PROFILES TABLE
-- =============================================================================
-- Stores user profile data linked directly to Supabase Auth users.
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

COMMENT ON TABLE public.profiles IS 'User profiles mirroring authenticated Supabase users.';

-- =============================================================================
-- 2. RESEARCH SESSIONS TABLE
-- =============================================================================
-- Stores research sessions initiated by authenticated users.
CREATE TABLE IF NOT EXISTS public.research_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    research_goal TEXT NOT NULL CHECK (length(trim(research_goal)) > 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    summary TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

COMMENT ON TABLE public.research_sessions IS 'Research investigations and their current analysis status.';

-- =============================================================================
-- 3. SOURCES TABLE
-- =============================================================================
-- Stores submitted sources and content extracted from URLs or text.
CREATE TABLE IF NOT EXISTS public.sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_id UUID NOT NULL REFERENCES public.research_sessions(id) ON DELETE CASCADE,
    source_code TEXT NOT NULL CHECK (source_code ~ '^S[0-9]+$'),
    title TEXT NOT NULL DEFAULT 'Untitled Source',
    url TEXT,
    source_type TEXT NOT NULL CHECK (source_type IN ('website', 'pasted_text', 'document')),
    extracted_content TEXT NOT NULL DEFAULT '',
    published_at TIMESTAMPTZ,
    accessed_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    extraction_status TEXT NOT NULL DEFAULT 'success' CHECK (extraction_status IN ('success', 'failed', 'partial')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT uq_sources_research_code UNIQUE (research_id, source_code)
);

COMMENT ON TABLE public.sources IS 'Submitted and extracted research sources for a session.';

-- =============================================================================
-- 4. FINDINGS TABLE
-- =============================================================================
-- Stores information gaps classified into 4 strict categories.
CREATE TABLE IF NOT EXISTS public.findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_id UUID NOT NULL REFERENCES public.research_sessions(id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (category IN ('missing', 'outdated', 'conflicting', 'unverified')),
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    description TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high')),
    confidence NUMERIC CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    recommended_action TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

COMMENT ON TABLE public.findings IS 'Detected information gaps categorized into missing, outdated, conflicting, and unverified.';

-- =============================================================================
-- 5. EVIDENCE REFERENCES TABLE
-- =============================================================================
-- Connects findings to specific source excerpts.
CREATE TABLE IF NOT EXISTS public.evidence_references (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id UUID NOT NULL REFERENCES public.findings(id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES public.sources(id) ON DELETE CASCADE,
    evidence_text TEXT NOT NULL CHECK (length(trim(evidence_text)) > 0),
    evidence_type TEXT NOT NULL DEFAULT 'supporting' CHECK (evidence_type IN ('supporting', 'contradicting', 'contextual')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

COMMENT ON TABLE public.evidence_references IS 'Verified source excerpts and quotations connecting findings to sources.';

-- =============================================================================
-- 6. VERIFICATION ITEMS TABLE
-- =============================================================================
-- Actionable checklist tasks. If finding_id IS NULL, represents general unresolved questions.
CREATE TABLE IF NOT EXISTS public.verification_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_id UUID NOT NULL REFERENCES public.research_sessions(id) ON DELETE CASCADE,
    finding_id UUID REFERENCES public.findings(id) ON DELETE CASCADE,
    task TEXT NOT NULL CHECK (length(trim(task)) > 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    completed_at TIMESTAMPTZ
);

COMMENT ON TABLE public.verification_items IS 'Actionable checklist items and broad unresolved research questions (finding_id = NULL).';

-- =============================================================================
-- 7. PERFORMANCE INDEXES
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_research_sessions_user_id ON public.research_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_research_sessions_created_at ON public.research_sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sources_research_id ON public.sources(research_id);
CREATE INDEX IF NOT EXISTS idx_findings_research_id ON public.findings(research_id);
CREATE INDEX IF NOT EXISTS idx_findings_category ON public.findings(category);
CREATE INDEX IF NOT EXISTS idx_evidence_references_finding_id ON public.evidence_references(finding_id);
CREATE INDEX IF NOT EXISTS idx_evidence_references_source_id ON public.evidence_references(source_id);
CREATE INDEX IF NOT EXISTS idx_verification_items_research_id ON public.verification_items(research_id);
CREATE INDEX IF NOT EXISTS idx_verification_items_finding_id ON public.verification_items(finding_id);

-- =============================================================================
-- 8. INTEGRITY TRIGGERS: PREVENT CROSS-SESSION REFERENCES
-- =============================================================================

-- Ensure evidence references only connect findings and sources from the SAME research session
CREATE OR REPLACE FUNCTION public.check_evidence_reference_session()
RETURNS TRIGGER AS $$
DECLARE
    v_finding_research_id UUID;
    v_source_research_id UUID;
BEGIN
    SELECT research_id INTO v_finding_research_id FROM public.findings WHERE id = NEW.finding_id;
    SELECT research_id INTO v_source_research_id FROM public.sources WHERE id = NEW.source_id;

    IF v_finding_research_id IS NULL THEN
        RAISE EXCEPTION 'Referenced finding % does not exist', NEW.finding_id;
    END IF;

    IF v_source_research_id IS NULL THEN
        RAISE EXCEPTION 'Referenced source % does not exist', NEW.source_id;
    END IF;

    IF v_finding_research_id <> v_source_research_id THEN
        RAISE EXCEPTION 'Cross-session reference error: finding % (session %) and source % (session %) belong to different research sessions',
            NEW.finding_id, v_finding_research_id, NEW.source_id, v_source_research_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_check_evidence_reference_session ON public.evidence_references;
CREATE TRIGGER trg_check_evidence_reference_session
    BEFORE INSERT OR UPDATE ON public.evidence_references
    FOR EACH ROW EXECUTE FUNCTION public.check_evidence_reference_session();

-- Ensure verification item finding (if specified) belongs to the SAME research session
CREATE OR REPLACE FUNCTION public.check_verification_item_session()
RETURNS TRIGGER AS $$
DECLARE
    v_finding_research_id UUID;
BEGIN
    IF NEW.finding_id IS NOT NULL THEN
        SELECT research_id INTO v_finding_research_id FROM public.findings WHERE id = NEW.finding_id;

        IF v_finding_research_id IS NULL THEN
            RAISE EXCEPTION 'Referenced finding % does not exist', NEW.finding_id;
        END IF;

        IF v_finding_research_id <> NEW.research_id THEN
            RAISE EXCEPTION 'Cross-session reference error: finding % (session %) does not match verification item session %',
                NEW.finding_id, v_finding_research_id, NEW.research_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_check_verification_item_session ON public.verification_items;
CREATE TRIGGER trg_check_verification_item_session
    BEFORE INSERT OR UPDATE ON public.verification_items
    FOR EACH ROW EXECUTE FUNCTION public.check_verification_item_session();

-- =============================================================================
-- 9. AUTH.USERS PROFILE CREATION TRIGGER
-- =============================================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, full_name, email, created_at, updated_at)
    VALUES (
        new.id,
        COALESCE(new.raw_user_meta_data->>'full_name', ''),
        COALESCE(new.email, ''),
        timezone('utc'::text, now()),
        timezone('utc'::text, now())
    )
    ON CONFLICT (id) DO UPDATE
    SET
        full_name = CASE
            WHEN EXCLUDED.full_name <> '' THEN EXCLUDED.full_name
            ELSE public.profiles.full_name
        END,
        email = EXCLUDED.email,
        updated_at = timezone('utc'::text, now());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- =============================================================================
-- 10. ROW LEVEL SECURITY (RLS) POLICIES
-- =============================================================================

-- Enable RLS on all tables
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.research_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evidence_references ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.verification_items ENABLE ROW LEVEL SECURITY;

-- Profiles: Users can view and update only their own profile
CREATE POLICY "Users can view own profile"
    ON public.profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
    ON public.profiles FOR UPDATE
    USING (auth.uid() = id);

-- Research Sessions: Users can manage only their own sessions
CREATE POLICY "Users can view own research sessions"
    ON public.research_sessions FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own research sessions"
    ON public.research_sessions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own research sessions"
    ON public.research_sessions FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own research sessions"
    ON public.research_sessions FOR DELETE
    USING (auth.uid() = user_id);

-- Sources: Users can manage sources of their own research sessions
CREATE POLICY "Users can view sources of own sessions"
    ON public.sources FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM public.research_sessions
        WHERE research_sessions.id = sources.research_id
          AND research_sessions.user_id = auth.uid()
    ));

CREATE POLICY "Users can insert sources into own sessions"
    ON public.sources FOR INSERT
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.research_sessions
        WHERE research_sessions.id = sources.research_id
          AND research_sessions.user_id = auth.uid()
    ));

CREATE POLICY "Users can update sources of own sessions"
    ON public.sources FOR UPDATE
    USING (EXISTS (
        SELECT 1 FROM public.research_sessions
        WHERE research_sessions.id = sources.research_id
          AND research_sessions.user_id = auth.uid()
    ));

CREATE POLICY "Users can delete sources of own sessions"
    ON public.sources FOR DELETE
    USING (EXISTS (
        SELECT 1 FROM public.research_sessions
        WHERE research_sessions.id = sources.research_id
          AND research_sessions.user_id = auth.uid()
    ));

-- Findings: Users can manage findings of their own research sessions
CREATE POLICY "Users can view findings of own sessions"
    ON public.findings FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM public.research_sessions
        WHERE research_sessions.id = findings.research_id
          AND research_sessions.user_id = auth.uid()
    ));

CREATE POLICY "Users can insert findings into own sessions"
    ON public.findings FOR INSERT
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.research_sessions
        WHERE research_sessions.id = findings.research_id
          AND research_sessions.user_id = auth.uid()
    ));

CREATE POLICY "Users can update findings of own sessions"
    ON public.findings FOR UPDATE
    USING (EXISTS (
        SELECT 1 FROM public.research_sessions
        WHERE research_sessions.id = findings.research_id
          AND research_sessions.user_id = auth.uid()
    ));

CREATE POLICY "Users can delete findings of own sessions"
    ON public.findings FOR DELETE
    USING (EXISTS (
        SELECT 1 FROM public.research_sessions
        WHERE research_sessions.id = findings.research_id
          AND research_sessions.user_id = auth.uid()
    ));

-- Evidence References: Users can manage evidence of their own research sessions
CREATE POLICY "Users can view evidence of own sessions"
    ON public.evidence_references FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM public.findings
        JOIN public.research_sessions ON findings.research_id = research_sessions.id
        WHERE findings.id = evidence_references.finding_id
          AND research_sessions.user_id = auth.uid()
    ));

CREATE POLICY "Users can insert evidence into own sessions"
    ON public.evidence_references FOR INSERT
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.findings
        JOIN public.research_sessions ON findings.research_id = research_sessions.id
        WHERE findings.id = evidence_references.finding_id
          AND research_sessions.user_id = auth.uid()
    ));

CREATE POLICY "Users can update evidence of own sessions"
    ON public.evidence_references FOR UPDATE
    USING (EXISTS (
        SELECT 1 FROM public.findings
        JOIN public.research_sessions ON findings.research_id = research_sessions.id
        WHERE findings.id = evidence_references.finding_id
          AND research_sessions.user_id = auth.uid()
    ));

CREATE POLICY "Users can delete evidence of own sessions"
    ON public.evidence_references FOR DELETE
    USING (EXISTS (
        SELECT 1 FROM public.findings
        JOIN public.research_sessions ON findings.research_id = research_sessions.id
        WHERE findings.id = evidence_references.finding_id
          AND research_sessions.user_id = auth.uid()
    ));

-- Verification Items: Users can manage verification items of their own research sessions
CREATE POLICY "Users can view verification items of own sessions"
    ON public.verification_items FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM public.research_sessions
        WHERE research_sessions.id = verification_items.research_id
          AND research_sessions.user_id = auth.uid()
    ));

CREATE POLICY "Users can insert verification items into own sessions"
    ON public.verification_items FOR INSERT
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.research_sessions
        WHERE research_sessions.id = verification_items.research_id
          AND research_sessions.user_id = auth.uid()
    ));

CREATE POLICY "Users can update verification items of own sessions"
    ON public.verification_items FOR UPDATE
    USING (EXISTS (
        SELECT 1 FROM public.research_sessions
        WHERE research_sessions.id = verification_items.research_id
          AND research_sessions.user_id = auth.uid()
    ));

CREATE POLICY "Users can delete verification items of own sessions"
    ON public.verification_items FOR DELETE
    USING (EXISTS (
        SELECT 1 FROM public.research_sessions
        WHERE research_sessions.id = verification_items.research_id
          AND research_sessions.user_id = auth.uid()
    ));

