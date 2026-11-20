-- =============================================================================
-- Migration: 004_source_metadata_enrichment.sql
-- Description: Adds optional metadata fields (author, publisher, domain, last_updated_at)
--              to the public.sources table for Phase 2 research intelligence.
--              Fully backward-compatible; existing records remain untouched with NULLs.
-- =============================================================================

ALTER TABLE public.sources
    ADD COLUMN IF NOT EXISTS author TEXT,
    ADD COLUMN IF NOT EXISTS publisher TEXT,
    ADD COLUMN IF NOT EXISTS domain TEXT,
    ADD COLUMN IF NOT EXISTS last_updated_at TIMESTAMPTZ;

COMMENT ON COLUMN public.sources.author IS 'Author or creator attribution extracted from source metadata.';
COMMENT ON COLUMN public.sources.publisher IS 'Publisher, site name, or issuing organization.';
COMMENT ON COLUMN public.sources.domain IS 'Normalized root domain/hostname of website sources.';
COMMENT ON COLUMN public.sources.last_updated_at IS 'Timestamp of last modification or update, if reliably known.';

