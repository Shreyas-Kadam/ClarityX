"""Unit tests for AnalysisPersistenceService and save_analysis_results RPC integration (Phase 6.3.3).

All Supabase client and PostgREST calls are mocked.
Tests verify:
1. Successful persistence flow.
2. Finding UUID generation and mapping.
3. Evidence quote -> evidence_text mapping.
4. Source-code payload mapping.
5. Nullable confidence preservation.
6. General unresolved questions with null finding IDs.
7. Unique finding-title mapping.
8. Ambiguous finding-title rejection.
9. Unmatched finding-title rejection.
10. Unknown source-code RPC failure handling.
11. Ownership mismatch handling.
12. Missing session handling.
13. Database error sanitization.
14. Async thread offloading.
15. Completed checklist preservation payload behavior.
16. Duplicate old/new task behavior.
17. Sanitized report response without extracted_content.
18. RPC failure does not produce a successful report response.
19. Invalid UUID inputs rejection.
"""

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import anyio
import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import ClarityXException, DatabaseConnectionError
from app.schemas.analysis import (
    LLMAnalysisResponse,
    LLMEvidenceItem,
    LLMFindingItem,
    LLMVerificationItem,
)
from app.schemas.research import ResearchReportData
from app.schemas.source import SourcePreviewResponse
from app.services.analysis_persistence_service import (
    AnalysisPersistenceService,
    parse_uuid,
)


@pytest.fixture
def sample_analysis():
    """Provides a sample valid LLMAnalysisResponse."""
    return LLMAnalysisResponse(
        summary="Comprehensive analysis of financial requirements and information gaps.",
        findings=[
            LLMFindingItem(
                category="missing",
                title="Application Deadline Absent",
                description="The application deadline is not mentioned in any available source.",
                severity="high",
                confidence=0.95,
                recommended_action="Contact registrar office for exact cutoff date.",
                evidence=[
                    LLMEvidenceItem(
                        source_code="S1",
                        quote="All applicants must apply before the semester begins.",
                        evidence_type="supporting",
                    )
                ],
            ),
            LLMFindingItem(
                category="conflicting",
                title="Conflicting GPA Requirements",
                description="Source S1 requires 3.0 whereas Source S2 indicates 3.5 minimum GPA.",
                severity="medium",
                confidence=None,  # Nullable confidence
                recommended_action="Verify with academic council.",
                evidence=[
                    LLMEvidenceItem(
                        source_code="S1",
                        quote="Minimum GPA requirement is 3.0 on a 4.0 scale.",
                        evidence_type="supporting",
                    ),
                    LLMEvidenceItem(
                        source_code="S2",
                        quote="Competitive applicants must maintain at least a 3.5 GPA.",
                        evidence_type="contradicting",
                    ),
                ],
            ),
        ],
        verification_checklist=[
            LLMVerificationItem(
                task="Confirm admissions deadline with admissions director.",
                is_general_unresolved_question=False,
                related_finding_title="Application Deadline Absent",
            ),
            LLMVerificationItem(
                task="Are international credentials evaluated under WES or in-house?",
                is_general_unresolved_question=True,
                related_finding_title=None,
            ),
        ],
    )


def mock_rpc_response_data(session_id: str, findings_payload: list, verification_payload: list):
    """Constructs a mock RPC return dictionary matching save_analysis_results output."""
    findings_data = []
    for f in findings_payload:
        findings_data.append({
            "id": f["id"],
            "research_id": session_id,
            "category": f["category"],
            "title": f["title"],
            "description": f["description"],
            "severity": f["severity"],
            "confidence": f["confidence"],
            "recommended_action": f["recommended_action"],
            "created_at": "2026-11-01T12:00:00Z",
            "evidence_references": [
                {
                    "id": str(uuid4()),
                    "finding_id": f["id"],
                    "source_id": str(uuid4()),
                    "source_code": "S1",
                    "evidence_text": "Exemplary evidence excerpt.",
                    "evidence_type": "supporting",
                    "created_at": "2026-11-01T12:00:00Z",
                }
            ],
        })

    unresolved_questions = []
    verification_items = []
    for v in verification_payload:
        if v.get("finding_id") is None:
            unresolved_questions.append({
                "id": v["id"],
                "task": v["task"],
                "status": "pending",
                "created_at": "2026-11-01T12:00:00Z",
            })
        else:
            verification_items.append({
                "id": v["id"],
                "research_id": session_id,
                "finding_id": v["finding_id"],
                "task": v["task"],
                "status": "pending",
                "created_at": "2026-11-01T12:00:00Z",
                "updated_at": "2026-11-01T12:00:00Z",
                "completed_at": None,
            })

    sources_data = [
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Admissions Guide 2026",
            "url": "https://example.com/admissions",
            "source_type": "website",
            "content_preview": "All applicants must apply before the semester begins...",
            "published_at": "2026-01-10T00:00:00Z",
            "accessed_at": "2026-11-01T12:00:00Z",
            "extraction_status": "success",
            "created_at": "2026-11-01T12:00:00Z",
        }
    ]

    return {
        "research_id": session_id,
        "research_goal": "Investigate admission requirements",
        "status": "completed",
        "summary": "Comprehensive analysis of financial requirements and information gaps.",
        "findings": findings_data,
        "sources": sources_data,
        "unresolved_questions": unresolved_questions,
        "verification_items": verification_items,
    }


# =============================================================================
# 1. Successful Persistence Flow & Field Mappings
# =============================================================================

@pytest.mark.anyio
async def test_persist_analysis_success(sample_analysis):
    """AnalysisPersistenceService prepares payload, calls RPC, and returns ResearchReportData."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    mock_rpc_call = MagicMock()
    mock_client.rpc.return_value = mock_rpc_call

    captured_payload = {}

    def execute_mock():
        resp = MagicMock()
        resp.data = mock_rpc_response_data(
            session_id,
            captured_payload.get("p_findings", []),
            captured_payload.get("p_verification_items", []),
        )
        return resp

    def rpc_side_effect(fn_name, payload):
        nonlocal captured_payload
        captured_payload = payload
        mock_rpc_call.execute.side_effect = execute_mock
        return mock_rpc_call

    mock_client.rpc.side_effect = rpc_side_effect

    service = AnalysisPersistenceService(client=mock_client)
    report = await service.persist_analysis(session_id, user_id, sample_analysis)

    assert isinstance(report, ResearchReportData)
    assert str(report.research_id) == session_id
    assert report.status == "completed"
    assert len(report.findings) == 2
    assert len(report.unresolved_questions) == 1
    assert len(report.verification_items) == 1
    assert len(report.sources) == 1
    assert isinstance(report.sources[0], SourcePreviewResponse)


# =============================================================================
# 2. Finding UUID Generation and Mapping
# =============================================================================

@pytest.mark.anyio
async def test_finding_uuid_generation_and_mapping(sample_analysis):
    """Every finding receives a unique UUID mapped accurately to evidence and tasks."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    captured_payload = {}

    def execute_mock():
        resp = MagicMock()
        resp.data = mock_rpc_response_data(
            session_id,
            captured_payload.get("p_findings", []),
            captured_payload.get("p_verification_items", []),
        )
        return resp

    mock_rpc_call = MagicMock()
    mock_rpc_call.execute.side_effect = execute_mock
    mock_client.rpc.return_value = mock_rpc_call

    def rpc_side_effect(fn_name, payload):
        nonlocal captured_payload
        captured_payload = payload
        return mock_rpc_call

    mock_client.rpc.side_effect = rpc_side_effect

    service = AnalysisPersistenceService(client=mock_client)
    await service.persist_analysis(session_id, user_id, sample_analysis)

    findings = captured_payload["p_findings"]
    assert len(findings) == 2
    f1_id = findings[0]["id"]
    f2_id = findings[1]["id"]
    assert f1_id != f2_id
    # Ensure they are valid UUID strings
    assert UUID(f1_id)
    assert UUID(f2_id)


# =============================================================================
# 3. Evidence Quote -> evidence_text Mapping
# =============================================================================

@pytest.mark.anyio
async def test_evidence_quote_to_evidence_text_mapping(sample_analysis):
    """AI evidence quotes are mapped strictly to the database column 'evidence_text'."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    captured_payload = {}

    def rpc_side_effect(fn_name, payload):
        nonlocal captured_payload
        captured_payload = payload
        call_mock = MagicMock()
        call_mock.execute.return_value.data = mock_rpc_response_data(session_id, payload["p_findings"], payload["p_verification_items"])
        return call_mock

    mock_client.rpc.side_effect = rpc_side_effect

    service = AnalysisPersistenceService(client=mock_client)
    await service.persist_analysis(session_id, user_id, sample_analysis)

    evidence_refs = captured_payload["p_evidence_references"]
    assert len(evidence_refs) == 3

    # Check evidence_text is populated and quote is not used as payload field
    for ref in evidence_refs:
        assert "evidence_text" in ref
        assert "quote" not in ref
        assert len(ref["evidence_text"]) > 0

    assert evidence_refs[0]["evidence_text"] == "All applicants must apply before the semester begins."


# =============================================================================
# 4. Source-Code Payload Mapping
# =============================================================================

@pytest.mark.anyio
async def test_source_code_payload_mapping(sample_analysis):
    """Source code (e.g. S1, S2) is passed on every evidence reference for RPC resolution."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    captured_payload = {}

    def rpc_side_effect(fn_name, payload):
        nonlocal captured_payload
        captured_payload = payload
        call_mock = MagicMock()
        call_mock.execute.return_value.data = mock_rpc_response_data(session_id, payload["p_findings"], payload["p_verification_items"])
        return call_mock

    mock_client.rpc.side_effect = rpc_side_effect

    service = AnalysisPersistenceService(client=mock_client)
    await service.persist_analysis(session_id, user_id, sample_analysis)

    evidence_refs = captured_payload["p_evidence_references"]
    assert evidence_refs[0]["source_code"] == "S1"
    assert evidence_refs[1]["source_code"] == "S1"
    assert evidence_refs[2]["source_code"] == "S2"


# =============================================================================
# 5. Nullable Confidence Preservation
# =============================================================================

@pytest.mark.anyio
async def test_nullable_confidence_preservation(sample_analysis):
    """Model confidence score is preserved when present and stays null when absent."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    captured_payload = {}

    def rpc_side_effect(fn_name, payload):
        nonlocal captured_payload
        captured_payload = payload
        call_mock = MagicMock()
        call_mock.execute.return_value.data = mock_rpc_response_data(session_id, payload["p_findings"], payload["p_verification_items"])
        return call_mock

    mock_client.rpc.side_effect = rpc_side_effect

    service = AnalysisPersistenceService(client=mock_client)
    await service.persist_analysis(session_id, user_id, sample_analysis)

    findings = captured_payload["p_findings"]
    assert findings[0]["confidence"] == 0.95
    assert findings[1]["confidence"] is None


# =============================================================================
# 6. General Unresolved Questions with Null Finding ID
# =============================================================================

@pytest.mark.anyio
async def test_general_unresolved_questions_with_null_finding_id(sample_analysis):
    """General unresolved questions are assigned finding_id = None strictly."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    captured_payload = {}

    def rpc_side_effect(fn_name, payload):
        nonlocal captured_payload
        captured_payload = payload
        call_mock = MagicMock()
        call_mock.execute.return_value.data = mock_rpc_response_data(session_id, payload["p_findings"], payload["p_verification_items"])
        return call_mock

    mock_client.rpc.side_effect = rpc_side_effect

    service = AnalysisPersistenceService(client=mock_client)
    await service.persist_analysis(session_id, user_id, sample_analysis)

    tasks = captured_payload["p_verification_items"]
    specific_task = next(t for t in tasks if "admissions director" in t["task"].lower())
    general_task = next(t for t in tasks if "international credentials" in t["task"].lower())

    assert specific_task["finding_id"] is not None
    assert general_task["finding_id"] is None


@pytest.mark.anyio
async def test_unresolved_questions_field_mapped_to_null_finding_id(sample_analysis):
    """Items in analysis.unresolved_questions are persisted with finding_id = None."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    captured_payload = {}

    def rpc_side_effect(fn_name, payload):
        nonlocal captured_payload
        captured_payload = payload
        call_mock = MagicMock()
        call_mock.execute.return_value.data = mock_rpc_response_data(
            session_id, payload["p_findings"], payload["p_verification_items"]
        )
        return call_mock

    mock_client.rpc.side_effect = rpc_side_effect

    # Add an unresolved question to analysis.unresolved_questions
    analysis_with_uq = sample_analysis.model_copy(
        update={
            "unresolved_questions": [
                LLMVerificationItem(
                    task="What are the housing deposit deadlines?",
                    is_general_unresolved_question=True,
                    related_finding_title=None,
                )
            ]
        },
        deep=True,
    )

    service = AnalysisPersistenceService(client=mock_client)
    await service.persist_analysis(session_id, user_id, analysis_with_uq)

    tasks = captured_payload["p_verification_items"]
    housing_task = next((t for t in tasks if "housing deposit" in t["task"].lower()), None)

    assert housing_task is not None
    assert housing_task["finding_id"] is None


# =============================================================================
# 7. Unique Finding-Title Mapping (Case and Whitespace Normalized)
# =============================================================================

@pytest.mark.anyio
async def test_unique_finding_title_mapping():
    """Finding titles with extra whitespace or different casing map to the unique finding."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    analysis = LLMAnalysisResponse(
        summary="Analysis summary here.",
        findings=[
            LLMFindingItem(
                category="outdated",
                title="Tuition Rates Outdated",
                description="Tuition rates reflect 2024 academic year.",
                severity="medium",
            )
        ],
        verification_checklist=[
            LLMVerificationItem(
                task="Obtain 2026 tuition table.",
                is_general_unresolved_question=False,
                related_finding_title="   tuition   rates   outdated  ",  # normalized match
            )
        ],
    )

    mock_client = MagicMock()
    captured_payload = {}

    def rpc_side_effect(fn_name, payload):
        nonlocal captured_payload
        captured_payload = payload
        call_mock = MagicMock()
        call_mock.execute.return_value.data = mock_rpc_response_data(session_id, payload["p_findings"], payload["p_verification_items"])
        return call_mock

    mock_client.rpc.side_effect = rpc_side_effect

    service = AnalysisPersistenceService(client=mock_client)
    await service.persist_analysis(session_id, user_id, analysis)

    finding_id = captured_payload["p_findings"][0]["id"]
    task_finding_id = captured_payload["p_verification_items"][0]["finding_id"]
    assert task_finding_id == finding_id


# =============================================================================
# 8. Ambiguous Finding-Title Rejection
# =============================================================================

@pytest.mark.anyio
async def test_ambiguous_finding_title_rejection():
    """Ambiguous finding titles raise ClarityXException(400) before calling RPC."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    analysis = LLMAnalysisResponse(
        summary="Analysis summary here.",
        findings=[
            LLMFindingItem(category="missing", title="Duplicate Title", description="Desc 1"),
            LLMFindingItem(category="outdated", title="Duplicate Title", description="Desc 2"),
        ],
        verification_checklist=[
            LLMVerificationItem(
                task="Follow up task",
                is_general_unresolved_question=False,
                related_finding_title="Duplicate Title",
            )
        ],
    )

    mock_client = MagicMock()
    service = AnalysisPersistenceService(client=mock_client)

    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(session_id, user_id, analysis)

    assert exc_info.value.status_code == 400
    assert "Ambiguous finding title" in exc_info.value.message
    # RPC must not be called
    mock_client.rpc.assert_not_called()


# =============================================================================
# 9. Unmatched Finding-Title Rejection
# =============================================================================

@pytest.mark.anyio
async def test_unmatched_finding_title_rejection():
    """Unmatched finding title raises ClarityXException(400) before calling RPC."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    analysis = LLMAnalysisResponse(
        summary="Analysis summary here.",
        findings=[
            LLMFindingItem(category="missing", title="Existing Title", description="Valid description here"),
        ],
        verification_checklist=[
            LLMVerificationItem(
                task="Follow up task",
                is_general_unresolved_question=False,
                related_finding_title="Non Existent Title",
            )
        ],
    )

    mock_client = MagicMock()
    service = AnalysisPersistenceService(client=mock_client)

    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(session_id, user_id, analysis)

    assert exc_info.value.status_code == 400
    assert "Unmatched finding title" in exc_info.value.message
    mock_client.rpc.assert_not_called()


# =============================================================================
# 10. Unknown Source-Code RPC Failure Handling
# =============================================================================

@pytest.mark.anyio
async def test_unknown_source_code_rpc_failure_handling(sample_analysis):
    """RPC failure for foreign/unknown source code translates to ClarityXException(400)."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    api_error = APIError({
        "message": "Unknown or invalid source code S99 for research session",
        "code": "23503",
    })
    mock_client.rpc.return_value.execute.side_effect = api_error

    service = AnalysisPersistenceService(client=mock_client)
    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(session_id, user_id, sample_analysis)

    assert exc_info.value.status_code == 400
    assert "Invalid evidence reference" in exc_info.value.message


# =============================================================================
# 11. Ownership Mismatch Handling
# =============================================================================

@pytest.mark.anyio
async def test_ownership_mismatch_handling(sample_analysis):
    """RPC ownership rejection translates to ClarityXException(403)."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    api_error = APIError({
        "message": "Unauthorized: Research session does not belong to user",
        "code": "42501",
    })
    mock_client.rpc.return_value.execute.side_effect = api_error

    service = AnalysisPersistenceService(client=mock_client)
    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(session_id, user_id, sample_analysis)

    assert exc_info.value.status_code == 403
    assert "Unauthorized" in exc_info.value.message


# =============================================================================
# 12. Missing Session Handling
# =============================================================================

@pytest.mark.anyio
async def test_missing_session_handling(sample_analysis):
    """Missing research session translates to ClarityXException(404)."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    api_error = APIError({
        "message": f"Research session {session_id} not found",
        "code": "P0002",
    })
    mock_client.rpc.return_value.execute.side_effect = api_error

    service = AnalysisPersistenceService(client=mock_client)
    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(session_id, user_id, sample_analysis)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.message


# =============================================================================
# 13. Database Error Sanitization
# =============================================================================

@pytest.mark.anyio
async def test_database_error_sanitization(sample_analysis):
    """PostgREST APIErrors are sanitized and do not leak SQL statements or schema internals."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    api_error = APIError({
        "message": "SELECT * FROM public.internal_table failed with constraint xyz_internal_pkey",
        "code": "40001",
    })
    mock_client.rpc.return_value.execute.side_effect = api_error

    service = AnalysisPersistenceService(client=mock_client)
    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(session_id, user_id, sample_analysis)

    assert exc_info.value.status_code == 400
    assert "Failed to persist analysis results" in exc_info.value.message
    # Internal table details must be omitted from error message
    assert "internal_table" not in exc_info.value.message


# =============================================================================
# 14. Async Thread Offloading
# =============================================================================

@pytest.mark.anyio
async def test_async_thread_offloading(sample_analysis):
    """Synchronous Supabase RPC call is offloaded to anyio.to_thread.run_sync."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    mock_client.rpc.return_value.execute.return_value.data = mock_rpc_response_data(session_id, [], [])

    service = AnalysisPersistenceService(client=mock_client)

    with patch("anyio.to_thread.run_sync", wraps=anyio.to_thread.run_sync) as spy_run_sync:
        await service.persist_analysis(session_id, user_id, sample_analysis)
        assert spy_run_sync.called


# =============================================================================
# 15. Completed Checklist Preservation Payload Behavior
# =============================================================================

@pytest.mark.anyio
async def test_completed_checklist_preservation_payload_behavior(sample_analysis):
    """Service sends verification items with status 'pending' to let RPC match completed tasks."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    captured_payload = {}

    def rpc_side_effect(fn_name, payload):
        nonlocal captured_payload
        captured_payload = payload
        call_mock = MagicMock()
        call_mock.execute.return_value.data = mock_rpc_response_data(session_id, payload["p_findings"], payload["p_verification_items"])
        return call_mock

    mock_client.rpc.side_effect = rpc_side_effect

    service = AnalysisPersistenceService(client=mock_client)
    await service.persist_analysis(session_id, user_id, sample_analysis)

    tasks = captured_payload["p_verification_items"]
    for t in tasks:
        assert t["status"] == "pending"
        assert UUID(t["id"])


# =============================================================================
# 16. Duplicate Old / New Task Behavior
# =============================================================================

@pytest.mark.anyio
async def test_duplicate_old_new_task_behavior():
    """Duplicate tasks in checklist are passed with distinct item UUIDs for RPC evaluation."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    analysis = LLMAnalysisResponse(
        summary="Analysis summary.",
        findings=[
            LLMFindingItem(category="missing", title="Some Gap", description="Description")
        ],
        verification_checklist=[
            LLMVerificationItem(
                task="Duplicate task text",
                is_general_unresolved_question=True,
                related_finding_title=None,
            ),
            LLMVerificationItem(
                task="Duplicate task text",
                is_general_unresolved_question=True,
                related_finding_title=None,
            ),
        ],
    )

    mock_client = MagicMock()
    captured_payload = {}

    def rpc_side_effect(fn_name, payload):
        nonlocal captured_payload
        captured_payload = payload
        call_mock = MagicMock()
        call_mock.execute.return_value.data = mock_rpc_response_data(session_id, payload["p_findings"], payload["p_verification_items"])
        return call_mock

    mock_client.rpc.side_effect = rpc_side_effect

    service = AnalysisPersistenceService(client=mock_client)
    await service.persist_analysis(session_id, user_id, analysis)

    tasks = captured_payload["p_verification_items"]
    assert len(tasks) == 2
    assert tasks[0]["id"] != tasks[1]["id"]
    assert tasks[0]["task"] == tasks[1]["task"]


# =============================================================================
# 17. Sanitized Report Response Without extracted_content
# =============================================================================

@pytest.mark.anyio
async def test_sanitized_report_response_without_extracted_content(sample_analysis):
    """ResearchReportData.sources contains SourcePreviewResponse without extracted_content."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    mock_client.rpc.return_value.execute.return_value.data = mock_rpc_response_data(
        session_id,
        [{"id": str(uuid4()), "category": "missing", "title": "T", "description": "D", "severity": "medium", "confidence": None, "recommended_action": ""}],
        [],
    )

    service = AnalysisPersistenceService(client=mock_client)
    report = await service.persist_analysis(session_id, user_id, sample_analysis)

    assert len(report.sources) == 1
    src = report.sources[0]
    assert isinstance(src, SourcePreviewResponse)
    assert hasattr(src, "content_preview")
    assert not hasattr(src, "extracted_content")


# =============================================================================
# 18. RPC Failure Does Not Produce a Successful Report Response
# =============================================================================

@pytest.mark.anyio
async def test_rpc_failure_empty_data_raises_500(sample_analysis):
    """Empty data returned from RPC raises ClarityXException(500)."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    mock_client.rpc.return_value.execute.return_value.data = None

    service = AnalysisPersistenceService(client=mock_client)
    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(session_id, user_id, sample_analysis)

    assert exc_info.value.status_code == 500
    assert "Failed to persist analysis results" in exc_info.value.message


@pytest.mark.anyio
async def test_rpc_failure_invalid_schema_raises_500(sample_analysis):
    """Malformed return data from RPC raises ClarityXException(500)."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    # Missing required research_id and status
    mock_client.rpc.return_value.execute.return_value.data = {"invalid": "payload"}

    service = AnalysisPersistenceService(client=mock_client)
    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(session_id, user_id, sample_analysis)

    assert exc_info.value.status_code == 500
    assert "failed to format report response" in exc_info.value.message


# =============================================================================
# 19. Invalid UUID Inputs Rejection
# =============================================================================

@pytest.mark.anyio
async def test_invalid_uuid_inputs_rejection(sample_analysis):
    """Invalid session_id or user_id raises ClarityXException(400) immediately."""
    mock_client = MagicMock()
    service = AnalysisPersistenceService(client=mock_client)

    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis("not-a-uuid", str(uuid4()), sample_analysis)
    assert exc_info.value.status_code == 400
    assert "Invalid research_id" in exc_info.value.message

    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(str(uuid4()), "not-a-uuid", sample_analysis)
    assert exc_info.value.status_code == 400
    assert "Invalid user_id" in exc_info.value.message

    mock_client.rpc.assert_not_called()


@pytest.mark.anyio
async def test_database_connection_error_on_network_failure(sample_analysis):
    """Network connection errors translate to DatabaseConnectionError(503)."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    mock_client.rpc.return_value.execute.side_effect = ConnectionError("Connection refused by database")

    service = AnalysisPersistenceService(client=mock_client)
    with pytest.raises(DatabaseConnectionError) as exc_info:
        await service.persist_analysis(session_id, user_id, sample_analysis)

    assert exc_info.value.status_code == 503
    assert "Unable to connect to the database" in exc_info.value.message


# =============================================================================
# 20. Strict SQLSTATE Error Mapping Tests (Phase 6.3.3.1)
# =============================================================================

@pytest.mark.anyio
async def test_sqlstate_23502_not_null_violation_maps_to_400(sample_analysis):
    """SQLSTATE 23502 (not_null_violation) maps to ClarityXException(400)."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    api_error = APIError({
        "message": "null value in column violates not-null constraint",
        "code": "23502",
    })
    mock_client.rpc.return_value.execute.side_effect = api_error

    service = AnalysisPersistenceService(client=mock_client)
    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(session_id, user_id, sample_analysis)

    assert exc_info.value.status_code == 400
    assert "violates schema constraints" in exc_info.value.message


@pytest.mark.anyio
async def test_sqlstate_22003_numeric_out_of_range_maps_to_400(sample_analysis):
    """SQLSTATE 22003 (numeric_value_out_of_range) maps to ClarityXException(400)."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    api_error = APIError({
        "message": "numeric field overflow",
        "code": "22003",
    })
    mock_client.rpc.return_value.execute.side_effect = api_error

    service = AnalysisPersistenceService(client=mock_client)
    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(session_id, user_id, sample_analysis)

    assert exc_info.value.status_code == 400
    assert "violates schema constraints" in exc_info.value.message


@pytest.mark.anyio
async def test_sqlstate_invalid_parameter_value_maps_to_400(sample_analysis):
    """PostgreSQL invalid_parameter_value maps to ClarityXException(400)."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    api_error = APIError({
        "message": "Finding confidence must be a numeric value between 0.0 and 1.0 or null",
        "code": "22023",  # invalid_parameter_value
    })
    mock_client.rpc.return_value.execute.side_effect = api_error

    service = AnalysisPersistenceService(client=mock_client)
    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(session_id, user_id, sample_analysis)

    assert exc_info.value.status_code == 400
    assert "violates schema constraints" in exc_info.value.message


# =============================================================================
# 21. Strict Confidence Payload & Validation Tests (Phase 6.3.3.1)
# =============================================================================

@pytest.mark.anyio
async def test_confidence_payload_serializes_numeric_and_null():
    """Valid numeric confidence is serialized as float, and None as JSON null."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    analysis = LLMAnalysisResponse(
        summary="Analysis summary for confidence testing.",
        findings=[
            LLMFindingItem(category="missing", title="Finding One", description="Valid description", confidence=0.88),
            LLMFindingItem(category="outdated", title="Finding Two", description="Valid description", confidence=None),
        ],
        verification_checklist=[
            LLMVerificationItem(task="General task?", is_general_unresolved_question=True),
        ],
    )

    mock_client = MagicMock()
    captured_payload = {}

    def rpc_side_effect(fn_name, payload):
        nonlocal captured_payload
        captured_payload = payload
        call_mock = MagicMock()
        call_mock.execute.return_value.data = mock_rpc_response_data(session_id, payload["p_findings"], payload["p_verification_items"])
        return call_mock

    mock_client.rpc.side_effect = rpc_side_effect

    service = AnalysisPersistenceService(client=mock_client)
    await service.persist_analysis(session_id, user_id, analysis)

    findings = captured_payload["p_findings"]
    assert findings[0]["confidence"] == 0.88
    assert isinstance(findings[0]["confidence"], float)
    assert findings[1]["confidence"] is None


@pytest.mark.anyio
async def test_confidence_rpc_rejection_for_check_violation(sample_analysis):
    """RPC error for out-of-range or malformed confidence translates to ClarityXException(400)."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    api_error = APIError({
        "message": "Finding confidence must be between 0.0 and 1.0",
        "code": "23514",  # check_violation
    })
    mock_client.rpc.return_value.execute.side_effect = api_error

    service = AnalysisPersistenceService(client=mock_client)
    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(session_id, user_id, sample_analysis)

    assert exc_info.value.status_code == 400
    assert "violates schema constraints" in exc_info.value.message


# =============================================================================
# 22. Strict Verification finding_id Payload & Validation Tests (Phase 6.3.3.1)
# =============================================================================

@pytest.mark.anyio
async def test_verification_finding_id_payload_rules():
    """Specific tasks receive finding UUID string; general questions receive None."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    analysis = LLMAnalysisResponse(
        summary="Analysis summary.",
        findings=[
            LLMFindingItem(category="missing", title="Target Finding", description="Valid description"),
        ],
        verification_checklist=[
            LLMVerificationItem(
                task="Specific task for target finding",
                is_general_unresolved_question=False,
                related_finding_title="Target Finding",
            ),
            LLMVerificationItem(
                task="General question without finding",
                is_general_unresolved_question=True,
                related_finding_title=None,
            ),
        ],
    )

    mock_client = MagicMock()
    captured_payload = {}

    def rpc_side_effect(fn_name, payload):
        nonlocal captured_payload
        captured_payload = payload
        call_mock = MagicMock()
        call_mock.execute.return_value.data = mock_rpc_response_data(session_id, payload["p_findings"], payload["p_verification_items"])
        return call_mock

    mock_client.rpc.side_effect = rpc_side_effect

    service = AnalysisPersistenceService(client=mock_client)
    await service.persist_analysis(session_id, user_id, analysis)

    f_id = captured_payload["p_findings"][0]["id"]
    tasks = captured_payload["p_verification_items"]

    assert tasks[0]["finding_id"] == f_id
    assert UUID(tasks[0]["finding_id"])  # Valid UUID format
    assert tasks[1]["finding_id"] is None  # Strictly null for general question


@pytest.mark.anyio
async def test_verification_finding_id_rpc_malformed_uuid_rejection(sample_analysis):
    """RPC error for malformed finding_id string translates to ClarityXException(400)."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    api_error = APIError({
        "message": "Malformed UUID for verification finding_id",
        "code": "22P02",
    })
    mock_client.rpc.return_value.execute.side_effect = api_error

    service = AnalysisPersistenceService(client=mock_client)
    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(session_id, user_id, sample_analysis)

    assert exc_info.value.status_code == 400
    assert "violates schema constraints" in exc_info.value.message


@pytest.mark.anyio
async def test_verification_finding_id_rpc_foreign_key_rejection(sample_analysis):
    """RPC error for non-existent finding_id translates to ClarityXException(400)."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_client = MagicMock()
    api_error = APIError({
        "message": "Verification item references non-existent finding UUID",
        "code": "23503",
    })
    mock_client.rpc.return_value.execute.side_effect = api_error

    service = AnalysisPersistenceService(client=mock_client)
    with pytest.raises(ClarityXException) as exc_info:
        await service.persist_analysis(session_id, user_id, sample_analysis)

    assert exc_info.value.status_code == 400
    assert "Invalid evidence reference in analysis" in exc_info.value.message

