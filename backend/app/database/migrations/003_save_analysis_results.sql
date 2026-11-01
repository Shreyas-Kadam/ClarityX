-- =============================================================================
-- Migration: 003_save_analysis_results.sql
-- Description: Creates an atomic PostgreSQL RPC function (save_analysis_results)
--              to persist findings, evidence references, and verification items,
--              preserving completed checklist tasks across re-analysis,
--              updating the session summary/status, and enforcing strict ownership.
-- =============================================================================

CREATE OR REPLACE FUNCTION public.save_analysis_results(
    p_session_id UUID,
    p_user_id UUID,
    p_summary TEXT,
    p_findings JSONB,
    p_evidence_references JSONB,
    p_verification_items JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_session_user_id UUID;
    v_research_goal TEXT;
    v_result JSONB;
    v_findings_result JSONB;
    v_unresolved_result JSONB;
    v_verification_result JSONB;
    v_sources_result JSONB;
    item_finding RECORD;
    item_evidence RECORD;
    item_verification RECORD;
BEGIN
    -- -------------------------------------------------------------------------
    -- 1. Input Parameter Validation
    -- -------------------------------------------------------------------------
    IF p_session_id IS NULL THEN
        RAISE EXCEPTION 'p_session_id cannot be null' USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'p_user_id cannot be null' USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_findings IS NULL OR jsonb_typeof(p_findings) <> 'array' THEN
        RAISE EXCEPTION 'p_findings must be a non-null JSONB array' USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_evidence_references IS NULL OR jsonb_typeof(p_evidence_references) <> 'array' THEN
        RAISE EXCEPTION 'p_evidence_references must be a non-null JSONB array' USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_verification_items IS NULL OR jsonb_typeof(p_verification_items) <> 'array' THEN
        RAISE EXCEPTION 'p_verification_items must be a non-null JSONB array' USING ERRCODE = 'invalid_parameter_value';
    END IF;

    -- -------------------------------------------------------------------------
    -- 2. Concurrency Lock & Ownership Verification
    -- -------------------------------------------------------------------------
    -- Lock the research session row for this transaction to serialize concurrent updates
    SELECT user_id, research_goal INTO v_session_user_id, v_research_goal
    FROM public.research_sessions
    WHERE id = p_session_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Research session % not found', p_session_id USING ERRCODE = 'no_data_found';
    END IF;

    IF v_session_user_id <> p_user_id THEN
        RAISE EXCEPTION 'Unauthorized: Research session does not belong to user %', p_user_id USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- -------------------------------------------------------------------------
    -- 3. Staging and Validation (Before ANY Database Deletions)
    -- -------------------------------------------------------------------------
    -- Explicitly qualify temporary table creation with pg_temp. to prevent public object shadowing
    CREATE TEMP TABLE pg_temp.tmp_incoming_findings (
        id UUID PRIMARY KEY,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        severity TEXT NOT NULL,
        confidence NUMERIC,
        recommended_action TEXT NOT NULL
    ) ON COMMIT DROP;

    FOR item_finding IN SELECT * FROM jsonb_array_elements(p_findings) LOOP
        -- Validate UUID
        IF (item_finding.value->>'id') IS NULL OR length(trim(item_finding.value->>'id')) = 0 THEN
            RAISE EXCEPTION 'Finding id must be a valid UUID' USING ERRCODE = 'invalid_parameter_value';
        END IF;

        IF (item_finding.value->>'id') !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
            RAISE EXCEPTION 'Finding id must be a valid UUID format: %', (item_finding.value->>'id')
                USING ERRCODE = 'invalid_parameter_value';
        END IF;

        -- Validate Category
        IF (item_finding.value->>'category') NOT IN ('missing', 'outdated', 'conflicting', 'unverified') THEN
            RAISE EXCEPTION 'Invalid finding category: %', (item_finding.value->>'category') USING ERRCODE = 'check_violation';
        END IF;

        -- Validate Title
        IF length(trim(COALESCE(item_finding.value->>'title', ''))) = 0 THEN
            RAISE EXCEPTION 'Finding title cannot be empty or whitespace only' USING ERRCODE = 'check_violation';
        END IF;

        -- Validate Severity
        IF COALESCE(item_finding.value->>'severity', 'medium') NOT IN ('low', 'medium', 'high') THEN
            RAISE EXCEPTION 'Invalid finding severity: %', (item_finding.value->>'severity') USING ERRCODE = 'check_violation';
        END IF;

        -- Validate Confidence strictly:
        -- Must be an actual JSON number between 0.0 and 1.0, or actual JSON null (or omitted)
        IF (item_finding.value ? 'confidence') THEN
            IF jsonb_typeof(item_finding.value->'confidence') = 'null' THEN
                -- Explicit null is accepted
                NULL;
            ELSIF jsonb_typeof(item_finding.value->'confidence') = 'number' THEN
                IF (item_finding.value->>'confidence')::NUMERIC < 0.0 OR (item_finding.value->>'confidence')::NUMERIC > 1.0 THEN
                    RAISE EXCEPTION 'Finding confidence must be between 0.0 and 1.0' USING ERRCODE = 'check_violation';
                END IF;
            ELSE
                -- Reject strings (including "" and "0.8"), booleans, arrays, objects
                RAISE EXCEPTION 'Finding confidence must be a numeric value between 0.0 and 1.0 or null'
                    USING ERRCODE = 'check_violation';
            END IF;
        END IF;

        INSERT INTO pg_temp.tmp_incoming_findings (id, category, title, description, severity, confidence, recommended_action)
        VALUES (
            (item_finding.value->>'id')::UUID,
            item_finding.value->>'category',
            trim(item_finding.value->>'title'),
            COALESCE(item_finding.value->>'description', ''),
            COALESCE(item_finding.value->>'severity', 'medium'),
            CASE
                WHEN (item_finding.value ? 'confidence') AND jsonb_typeof(item_finding.value->'confidence') = 'number'
                THEN (item_finding.value->>'confidence')::NUMERIC
                ELSE NULL
            END,
            COALESCE(item_finding.value->>'recommended_action', '')
        );
    END LOOP;

    -- Pre-load valid source codes for this research session (schema-qualified)
    CREATE TEMP TABLE pg_temp.tmp_session_sources ON COMMIT DROP AS
    SELECT id, source_code
    FROM public.sources
    WHERE research_id = p_session_id;

    -- Validate Evidence References
    FOR item_evidence IN SELECT * FROM jsonb_array_elements(p_evidence_references) LOOP
        -- Validate evidence reference id if specified
        IF (item_evidence.value->>'id') IS NOT NULL AND length(trim(item_evidence.value->>'id')) > 0 THEN
            IF (item_evidence.value->>'id') !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
                RAISE EXCEPTION 'Evidence id must be a valid UUID format: %', (item_evidence.value->>'id')
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;
        END IF;

        -- Validate referenced finding exists in incoming findings
        IF (item_evidence.value->>'finding_id') IS NULL OR (item_evidence.value->>'finding_id') !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
            RAISE EXCEPTION 'Evidence finding_id must be a valid UUID: %', (item_evidence.value->>'finding_id')
                USING ERRCODE = 'invalid_parameter_value';
        END IF;

        IF NOT EXISTS (SELECT 1 FROM pg_temp.tmp_incoming_findings WHERE id = (item_evidence.value->>'finding_id')::UUID) THEN
            RAISE EXCEPTION 'Evidence references unknown finding UUID: %', (item_evidence.value->>'finding_id')
                USING ERRCODE = 'foreign_key_violation';
        END IF;

        -- Validate source code exists in this session's sources
        IF NOT EXISTS (SELECT 1 FROM pg_temp.tmp_session_sources WHERE source_code = (item_evidence.value->>'source_code')) THEN
            RAISE EXCEPTION 'Unknown or invalid source code % for research session %', (item_evidence.value->>'source_code'), p_session_id
                USING ERRCODE = 'foreign_key_violation';
        END IF;

        -- Validate non-empty evidence text
        IF length(trim(COALESCE(item_evidence.value->>'evidence_text', ''))) = 0 THEN
            RAISE EXCEPTION 'Evidence text cannot be empty or whitespace only' USING ERRCODE = 'check_violation';
        END IF;

        -- Validate evidence type
        IF COALESCE(item_evidence.value->>'evidence_type', 'supporting') NOT IN ('supporting', 'contradicting', 'contextual') THEN
            RAISE EXCEPTION 'Invalid evidence type: %', (item_evidence.value->>'evidence_type') USING ERRCODE = 'check_violation';
        END IF;
    END LOOP;

    -- Validate Verification Items
    FOR item_verification IN SELECT * FROM jsonb_array_elements(p_verification_items) LOOP
        -- Validate verification item id if specified
        IF (item_verification.value->>'id') IS NOT NULL AND length(trim(item_verification.value->>'id')) > 0 THEN
            IF (item_verification.value->>'id') !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
                RAISE EXCEPTION 'Verification item id must be a valid UUID format: %', (item_verification.value->>'id')
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;
        END IF;

        -- Validate task text
        IF length(trim(COALESCE(item_verification.value->>'task', ''))) = 0 THEN
            RAISE EXCEPTION 'Verification task cannot be empty or whitespace only' USING ERRCODE = 'check_violation';
        END IF;

        -- Validate finding_id:
        -- Accepted: valid UUID string referring to an incoming finding, or actual JSON null (or omitted)
        IF (item_verification.value ? 'finding_id') THEN
            IF jsonb_typeof(item_verification.value->'finding_id') = 'null' THEN
                -- Explicit null is accepted (general unresolved question)
                NULL;
            ELSIF jsonb_typeof(item_verification.value->'finding_id') = 'string' THEN
                IF length(trim(item_verification.value->>'finding_id')) = 0 THEN
                    RAISE EXCEPTION 'Verification finding_id cannot be an empty or whitespace-only string'
                        USING ERRCODE = 'invalid_parameter_value';
                END IF;

                IF (item_verification.value->>'finding_id') !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
                    RAISE EXCEPTION 'Malformed UUID for verification finding_id: %', (item_verification.value->>'finding_id')
                        USING ERRCODE = 'invalid_parameter_value';
                END IF;

                IF NOT EXISTS (SELECT 1 FROM pg_temp.tmp_incoming_findings WHERE id = (item_verification.value->>'finding_id')::UUID) THEN
                    RAISE EXCEPTION 'Verification item references non-existent finding UUID: %', (item_verification.value->>'finding_id')
                        USING ERRCODE = 'foreign_key_violation';
                END IF;
            ELSE
                -- Reject incorrect JSON types (number, boolean, array, object)
                RAISE EXCEPTION 'Verification finding_id must be a UUID string or null'
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;
        END IF;

        -- Validate status
        IF COALESCE(item_verification.value->>'status', 'pending') NOT IN ('pending', 'completed') THEN
            RAISE EXCEPTION 'Invalid verification status: %', (item_verification.value->>'status') USING ERRCODE = 'check_violation';
        END IF;
    END LOOP;

    -- -------------------------------------------------------------------------
    -- 4. Completed Checklist State Preservation (Re-analysis Handling)
    -- -------------------------------------------------------------------------
    -- Record existing completed verification tasks with normalized task text:
    -- Lowercase, trim leading/trailing whitespace, and collapse repeated whitespace.
    CREATE TEMP TABLE pg_temp.tmp_old_completed ON COMMIT DROP AS
    SELECT
        regexp_replace(lower(trim(task)), '\s+', ' ', 'g') AS norm_task,
        completed_at,
        COUNT(*) OVER (PARTITION BY regexp_replace(lower(trim(task)), '\s+', ' ', 'g')) AS cnt
    FROM public.verification_items
    WHERE research_id = p_session_id AND status = 'completed';

    -- Prepare incoming verification tasks and count occurrences of each normalized task
    CREATE TEMP TABLE pg_temp.tmp_incoming_tasks (
        idx INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        id UUID,
        finding_id UUID,
        task TEXT NOT NULL,
        norm_task TEXT NOT NULL,
        task_cnt INT
    ) ON COMMIT DROP;

    INSERT INTO pg_temp.tmp_incoming_tasks (id, finding_id, task, norm_task)
    SELECT
        COALESCE(NULLIF(incoming_task.value->>'id', '')::UUID, gen_random_uuid()),
        CASE
            WHEN (incoming_task.value ? 'finding_id') AND jsonb_typeof(incoming_task.value->'finding_id') = 'string'
            THEN (incoming_task.value->>'finding_id')::UUID
            ELSE NULL
        END,
        trim(incoming_task.value->>'task'),
        regexp_replace(lower(trim(incoming_task.value->>'task')), '\s+', ' ', 'g')
    FROM jsonb_array_elements(p_verification_items) AS incoming_task;

    -- Count occurrences among incoming tasks to detect incoming duplicates
    UPDATE pg_temp.tmp_incoming_tasks target_tasks
    SET task_cnt = sub_counts.cnt
    FROM (
        SELECT norm_task, COUNT(*) AS cnt
        FROM pg_temp.tmp_incoming_tasks
        GROUP BY norm_task
    ) sub_counts
    WHERE target_tasks.norm_task = sub_counts.norm_task;

    -- -------------------------------------------------------------------------
    -- 5. Atomic Deletion of Previous Analysis
    -- -------------------------------------------------------------------------
    -- Delete all old verification items for this session (both specific and general)
    DELETE FROM public.verification_items WHERE research_id = p_session_id;

    -- Delete old findings (cascade automatically deletes evidence_references)
    DELETE FROM public.findings WHERE research_id = p_session_id;

    -- -------------------------------------------------------------------------
    -- 6. Insert New Analysis Records
    -- -------------------------------------------------------------------------
    -- Insert findings
    INSERT INTO public.findings (id, research_id, category, title, description, severity, confidence, recommended_action, created_at)
    SELECT
        staged_finding.id,
        p_session_id,
        staged_finding.category,
        staged_finding.title,
        staged_finding.description,
        staged_finding.severity,
        staged_finding.confidence,
        staged_finding.recommended_action,
        timezone('utc'::text, now())
    FROM pg_temp.tmp_incoming_findings staged_finding;

    -- Insert evidence references
    INSERT INTO public.evidence_references (id, finding_id, source_id, evidence_text, evidence_type, created_at)
    SELECT
        COALESCE(NULLIF(incoming_evidence.value->>'id', '')::UUID, gen_random_uuid()),
        (incoming_evidence.value->>'finding_id')::UUID,
        src.id,
        trim(incoming_evidence.value->>'evidence_text'),
        COALESCE(incoming_evidence.value->>'evidence_type', 'supporting'),
        timezone('utc'::text, now())
    FROM jsonb_array_elements(p_evidence_references) AS incoming_evidence
    JOIN pg_temp.tmp_session_sources src ON src.source_code = (incoming_evidence.value->>'source_code');

    -- Insert verification items:
    -- Preserves 'completed' status and original completed_at ONLY if:
    -- 1. The old completed task has exactly one normalized match (cnt = 1).
    -- 2. The new task has exactly one normalized match (task_cnt = 1).
    -- Otherwise defaults to 'pending' with NULL completed_at.
    INSERT INTO public.verification_items (id, research_id, finding_id, task, status, created_at, updated_at, completed_at)
    SELECT
        staged_task.id,
        p_session_id,
        staged_task.finding_id,
        staged_task.task,
        CASE
            WHEN staged_task.task_cnt = 1 AND old_comp.cnt = 1 THEN 'completed'
            ELSE 'pending'
        END AS status,
        timezone('utc'::text, now()),
        timezone('utc'::text, now()),
        CASE
            WHEN staged_task.task_cnt = 1 AND old_comp.cnt = 1 THEN old_comp.completed_at
            ELSE NULL
        END AS completed_at
    FROM pg_temp.tmp_incoming_tasks staged_task
    LEFT JOIN (
        SELECT norm_task, completed_at, cnt
        FROM pg_temp.tmp_old_completed
        WHERE cnt = 1
    ) old_comp ON old_comp.norm_task = staged_task.norm_task;

    -- -------------------------------------------------------------------------
    -- 7. Update Research Session Status & Summary
    -- -------------------------------------------------------------------------
    UPDATE public.research_sessions
    SET summary = COALESCE(p_summary, ''),
        status = 'completed',
        updated_at = timezone('utc'::text, now())
    WHERE id = p_session_id;

    -- -------------------------------------------------------------------------
    -- 8. Assemble and Return Complete Persisted Report Payload
    -- -------------------------------------------------------------------------
    -- Gather findings with their nested evidence references
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'id', res_finding.id,
                'research_id', res_finding.research_id,
                'category', res_finding.category,
                'title', res_finding.title,
                'description', res_finding.description,
                'severity', res_finding.severity,
                'confidence', res_finding.confidence,
                'recommended_action', res_finding.recommended_action,
                'created_at', res_finding.created_at,
                'evidence_references', COALESCE(
                    (
                        SELECT jsonb_agg(
                            jsonb_build_object(
                                'id', er.id,
                                'finding_id', er.finding_id,
                                'source_id', er.source_id,
                                'source_code', s.source_code,
                                'evidence_text', er.evidence_text,
                                'evidence_type', er.evidence_type,
                                'created_at', er.created_at
                            ) ORDER BY er.created_at ASC
                        )
                        FROM public.evidence_references er
                        JOIN public.sources s ON s.id = er.source_id
                        WHERE er.finding_id = res_finding.id
                    ),
                    '[]'::jsonb
                )
            ) ORDER BY res_finding.created_at ASC
        ),
        '[]'::jsonb
    ) INTO v_findings_result
    FROM public.findings res_finding
    WHERE res_finding.research_id = p_session_id;

    -- Gather general unresolved questions (finding_id IS NULL)
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'id', res_uq.id,
                'task', res_uq.task,
                'status', res_uq.status,
                'created_at', res_uq.created_at
            ) ORDER BY res_uq.created_at ASC
        ),
        '[]'::jsonb
    ) INTO v_unresolved_result
    FROM public.verification_items res_uq
    WHERE res_uq.research_id = p_session_id AND res_uq.finding_id IS NULL;

    -- Gather finding-specific verification items (finding_id IS NOT NULL)
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'id', res_vi.id,
                'research_id', res_vi.research_id,
                'finding_id', res_vi.finding_id,
                'task', res_vi.task,
                'status', res_vi.status,
                'created_at', res_vi.created_at,
                'updated_at', res_vi.updated_at,
                'completed_at', res_vi.completed_at
            ) ORDER BY res_vi.created_at ASC
        ),
        '[]'::jsonb
    ) INTO v_verification_result
    FROM public.verification_items res_vi
    WHERE res_vi.research_id = p_session_id AND res_vi.finding_id IS NOT NULL;

    -- Gather sources with sanitized content_preview (never raw extracted_content)
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'id', res_src.id,
                'research_id', res_src.research_id,
                'source_code', res_src.source_code,
                'title', res_src.title,
                'url', res_src.url,
                'source_type', res_src.source_type,
                'content_preview', CASE
                    WHEN length(res_src.extracted_content) <= 250 THEN res_src.extracted_content
                    ELSE substr(res_src.extracted_content, 1, 250) || '...'
                END,
                'published_at', res_src.published_at,
                'accessed_at', res_src.accessed_at,
                'extraction_status', res_src.extraction_status,
                'created_at', res_src.created_at
            ) ORDER BY res_src.source_code ASC
        ),
        '[]'::jsonb
    ) INTO v_sources_result
    FROM public.sources res_src
    WHERE res_src.research_id = p_session_id;

    v_result := jsonb_build_object(
        'research_id', p_session_id,
        'research_goal', v_research_goal,
        'status', 'completed',
        'summary', COALESCE(p_summary, ''),
        'findings', v_findings_result,
        'sources', v_sources_result,
        'unresolved_questions', v_unresolved_result,
        'verification_items', v_verification_result
    );

    RETURN v_result;
END;
$$;

-- -----------------------------------------------------------------------------
-- Function Security & Execution Grants
-- -----------------------------------------------------------------------------
REVOKE ALL ON FUNCTION public.save_analysis_results(
    UUID, UUID, TEXT, JSONB, JSONB, JSONB
) FROM PUBLIC;

REVOKE ALL ON FUNCTION public.save_analysis_results(
    UUID, UUID, TEXT, JSONB, JSONB, JSONB
) FROM anon, authenticated;

GRANT EXECUTE ON FUNCTION public.save_analysis_results(
    UUID, UUID, TEXT, JSONB, JSONB, JSONB
) TO service_role;

COMMENT ON FUNCTION public.save_analysis_results(UUID, UUID, TEXT, JSONB, JSONB, JSONB) IS
    'Atomically persists AI analysis findings, evidence references, and verification items, preserving completed tasks across re-analysis and enforcing user ownership.';
