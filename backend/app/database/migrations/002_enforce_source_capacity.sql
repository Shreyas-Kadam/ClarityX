-- =============================================================================
-- Migration: 002_enforce_source_capacity.sql
-- Description: Enforce maximum of 5 sources per research session atomically.
-- Uses transaction-level row locking on the parent research_sessions row
-- to serialize concurrent source insertions and prevent race conditions.
-- =============================================================================

CREATE OR REPLACE FUNCTION public.enforce_source_capacity_limit()
RETURNS TRIGGER AS $$
DECLARE
    v_source_count INT;
BEGIN
    -- Explicitly lock the parent research session row for this transaction.
    -- This serializes concurrent source insertions targeting the same research session,
    -- preventing race conditions where parallel requests bypass capacity checks.
    PERFORM 1
    FROM public.research_sessions
    WHERE id = NEW.research_id
    FOR UPDATE;

    -- Count existing sources for this session
    SELECT COUNT(*) INTO v_source_count
    FROM public.sources
    WHERE research_id = NEW.research_id;

    -- Enforce the strict hard limit of 5 sources per session
    IF v_source_count >= 5 THEN
        RAISE EXCEPTION 'Source capacity limit reached. A research session cannot have more than 5 sources.'
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;

-- Create the trigger on public.sources
DROP TRIGGER IF EXISTS trg_enforce_source_capacity_limit ON public.sources;
CREATE TRIGGER trg_enforce_source_capacity_limit
    BEFORE INSERT ON public.sources
    FOR EACH ROW EXECUTE FUNCTION public.enforce_source_capacity_limit();

COMMENT ON FUNCTION public.enforce_source_capacity_limit() IS
    'Atomically serializes and enforces the hard 5-source quota per research session using row-level locking.';

