"""Unit tests for FindingRepository, EvidenceReferenceRepository, VerificationRepository,
and Analysis Response Schemas (Phase 6.3.2).

All database calls are mocked – no real database operations or migrations are performed.
Tests verify:
1. FindingRepository creation, bulk creation, ownership checks, constraint validation, retrieval, deletion.
2. EvidenceReferenceRepository creation, session validation for finding & source IDs, bulk creation, retrieval.
3. VerificationRepository creation (nullable finding_id), status updates (pending/completed timestamps),
   strict field isolation, ownership rejection.
4. map_verification_to_finding_id strict title mapping (exact, normalized, duplicate, unmatched, general).
5. Response schemas validation (FindingResponse, EvidenceReferenceResponse, VerificationItemResponse,
   ResearchReportData, VerificationStatusUpdate).
6. Safe database error translation and cross-user isolation.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import ClarityXException, DatabaseConnectionError
from app.database.repositories import (
    EvidenceReferenceRepository,
    FindingRepository,
    VerificationRepository,
    map_verification_to_finding_id,
)
from app.schemas.analysis import LLMVerificationItem
from app.schemas.research import (
    EvidenceReferenceResponse,
    FindingResponse,
    ResearchReportData,
    ResearchReportEnvelope,
    UnresolvedQuestionResponse,
    VerificationItemResponse,
    VerificationStatusUpdate,
)


@pytest.fixture
def mock_supabase():
    """Provides a fresh mocked Supabase client for repository tests."""
    with patch("app.database.repositories.get_supabase_client") as mock_get:
        client = MagicMock()
        mock_get.return_value = client
        yield client


# =============================================================================
# 1. FindingRepository Tests
# =============================================================================

@pytest.mark.anyio
async def test_create_finding_success(mock_supabase):
    """FindingRepository persists a finding with generated UUID and nullable confidence."""
    session_id = str(uuid4())
    user_id = str(uuid4())
    finding_id = str(uuid4())

    # Mock ownership check
    mock_sessions = MagicMock()
    mock_supabase.table.return_value = mock_sessions
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    # Mock insert
    mock_findings = MagicMock()
    mock_findings.insert.return_value.execute.return_value.data = [
        {
            "id": finding_id,
            "research_id": session_id,
            "category": "missing",
            "title": "Application Deadline Absent",
            "description": "No application deadline provided in sources.",
            "severity": "high",
            "confidence": 0.95,
            "recommended_action": "Contact admissions.",
            "created_at": "2026-11-01T12:00:00Z",
        }
    ]

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        return mock_findings

    mock_supabase.table.side_effect = table_router

    repo = FindingRepository()
    result = await repo.create_finding(
        session_id=session_id,
        user_id=user_id,
        category="missing",
        title="Application Deadline Absent",
        description="No application deadline provided in sources.",
        severity="high",
        confidence=0.95,
        recommended_action="Contact admissions.",
    )

    assert result["id"] == finding_id
    assert result["category"] == "missing"
    assert result["confidence"] == 0.95
    assert result["severity"] == "high"


@pytest.mark.anyio
async def test_create_finding_unauthorized_rejection(mock_supabase):
    """FindingRepository rejects creation when session ownership verification fails."""
    mock_table = MagicMock()
    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value = mock_table

    repo = FindingRepository()
    with pytest.raises(ClarityXException) as exc_info:
        await repo.create_finding(
            session_id=str(uuid4()),
            user_id=str(uuid4()),
            category="missing",
            title="Title",
            description="Description",
        )

    assert exc_info.value.status_code == 404
    assert "unauthorized" in exc_info.value.message.lower()


@pytest.mark.anyio
async def test_create_finding_invalid_category_rejection(mock_supabase):
    """FindingRepository rejects categories outside the 4 allowed."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_table = MagicMock()
    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]
    mock_supabase.table.return_value = mock_table

    repo = FindingRepository()
    with pytest.raises(ClarityXException) as exc_info:
        await repo.create_finding(
            session_id=session_id,
            user_id=user_id,
            category="invalid_category",
            title="Title",
            description="Desc",
        )

    assert exc_info.value.status_code == 400
    assert "Invalid category" in exc_info.value.message


@pytest.mark.anyio
async def test_create_finding_invalid_severity_rejection(mock_supabase):
    """FindingRepository rejects severities outside low/medium/high."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_table = MagicMock()
    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]
    mock_supabase.table.return_value = mock_table

    repo = FindingRepository()
    with pytest.raises(ClarityXException) as exc_info:
        await repo.create_finding(
            session_id=session_id,
            user_id=user_id,
            category="missing",
            title="Title",
            description="Desc",
            severity="critical",  # invalid
        )

    assert exc_info.value.status_code == 400
    assert "Invalid severity" in exc_info.value.message


@pytest.mark.anyio
async def test_create_finding_title_validation(mock_supabase):
    """FindingRepository validates title length and non-emptiness."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_table = MagicMock()
    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]
    mock_supabase.table.return_value = mock_table

    repo = FindingRepository()

    # Empty / whitespace-only title
    with pytest.raises(ClarityXException) as exc_info:
        await repo.create_finding(
            session_id=session_id,
            user_id=user_id,
            category="missing",
            title="   \n\t  ",
            description="Desc",
        )
    assert exc_info.value.status_code == 400

    # Title exceeding 255 chars
    with pytest.raises(ClarityXException) as exc_info:
        await repo.create_finding(
            session_id=session_id,
            user_id=user_id,
            category="missing",
            title="T" * 256,
            description="Desc",
        )
    assert exc_info.value.status_code == 400


@pytest.mark.anyio
async def test_create_findings_bulk_success(mock_supabase):
    """FindingRepository creates multiple findings in a single operation."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    mock_findings = MagicMock()
    mock_findings.insert.return_value.execute.return_value.data = [
        {"id": str(uuid4()), "title": "F1", "category": "missing"},
        {"id": str(uuid4()), "title": "F2", "category": "conflicting"},
    ]

    def table_router(table_name):
        return mock_sessions if table_name == "research_sessions" else mock_findings

    mock_supabase.table.side_effect = table_router

    repo = FindingRepository()
    results = await repo.create_findings_bulk(
        session_id=session_id,
        user_id=user_id,
        findings_data=[
            {"category": "missing", "title": "F1", "description": "D1"},
            {"category": "conflicting", "title": "F2", "description": "D2"},
        ],
    )

    assert len(results) == 2
    assert results[0]["title"] == "F1"
    assert results[1]["title"] == "F2"


@pytest.mark.anyio
async def test_get_findings_by_session(mock_supabase):
    """FindingRepository retrieves all findings for a session ordered by created_at."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    mock_findings = MagicMock()
    mock_findings.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
        {"id": str(uuid4()), "title": "F1"},
        {"id": str(uuid4()), "title": "F2"},
    ]

    def table_router(table_name):
        return mock_sessions if table_name == "research_sessions" else mock_findings

    mock_supabase.table.side_effect = table_router

    repo = FindingRepository()
    results = await repo.get_findings_by_session(session_id, user_id)
    assert len(results) == 2


@pytest.mark.anyio
async def test_delete_findings_by_session(mock_supabase):
    """FindingRepository deletes findings for a session verifying ownership."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    mock_findings = MagicMock()
    mock_findings.delete.return_value.eq.return_value.execute.return_value.data = [
        {"id": "f1"},
        {"id": "f2"},
    ]

    def table_router(table_name):
        return mock_sessions if table_name == "research_sessions" else mock_findings

    mock_supabase.table.side_effect = table_router

    repo = FindingRepository()
    count = await repo.delete_findings_by_session(session_id, user_id)
    assert count == 2


# =============================================================================
# 2. EvidenceReferenceRepository Tests
# =============================================================================

@pytest.mark.anyio
async def test_create_evidence_reference_success(mock_supabase):
    """EvidenceReferenceRepository creates evidence linking finding and source in same session."""
    session_id = str(uuid4())
    user_id = str(uuid4())
    finding_id = str(uuid4())
    source_id = str(uuid4())
    evidence_id = str(uuid4())

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    mock_findings = MagicMock()
    mock_findings.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": finding_id}
    ]

    mock_sources = MagicMock()
    mock_sources.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": source_id}
    ]

    mock_evidence = MagicMock()
    mock_evidence.insert.return_value.execute.return_value.data = [
        {
            "id": evidence_id,
            "finding_id": finding_id,
            "source_id": source_id,
            "evidence_text": "Exact quote from source S1.",
            "evidence_type": "supporting",
        }
    ]

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        elif table_name == "findings":
            return mock_findings
        elif table_name == "sources":
            return mock_sources
        return mock_evidence

    mock_supabase.table.side_effect = table_router

    repo = EvidenceReferenceRepository()
    result = await repo.create_evidence_reference(
        session_id=session_id,
        user_id=user_id,
        finding_id=finding_id,
        source_id=source_id,
        evidence_text="Exact quote from source S1.",
        evidence_type="supporting",
    )

    assert result["id"] == evidence_id
    assert result["finding_id"] == finding_id
    assert result["source_id"] == source_id


@pytest.mark.anyio
async def test_create_evidence_reference_rejects_foreign_finding(mock_supabase):
    """EvidenceReferenceRepository rejects evidence when finding belongs to another session."""
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    mock_findings = MagicMock()
    # Finding not found in this session
    mock_findings.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

    def table_router(table_name):
        return mock_sessions if table_name == "research_sessions" else mock_findings

    mock_supabase.table.side_effect = table_router

    repo = EvidenceReferenceRepository()
    with pytest.raises(ClarityXException) as exc_info:
        await repo.create_evidence_reference(
            session_id=session_id,
            user_id=user_id,
            finding_id=str(uuid4()),
            source_id=str(uuid4()),
            evidence_text="Quote",
        )

    assert exc_info.value.status_code == 400
    assert "Referenced finding does not belong" in exc_info.value.message


@pytest.mark.anyio
async def test_create_evidence_reference_rejects_foreign_source(mock_supabase):
    """EvidenceReferenceRepository rejects evidence when source belongs to another session."""
    session_id = str(uuid4())
    user_id = str(uuid4())
    finding_id = str(uuid4())

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    mock_findings = MagicMock()
    mock_findings.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": finding_id}
    ]

    mock_sources = MagicMock()
    # Source not found in this session
    mock_sources.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        elif table_name == "findings":
            return mock_findings
        return mock_sources

    mock_supabase.table.side_effect = table_router

    repo = EvidenceReferenceRepository()
    with pytest.raises(ClarityXException) as exc_info:
        await repo.create_evidence_reference(
            session_id=session_id,
            user_id=user_id,
            finding_id=finding_id,
            source_id=str(uuid4()),
            evidence_text="Quote",
        )

    assert exc_info.value.status_code == 400
    assert "Referenced source does not belong" in exc_info.value.message


@pytest.mark.anyio
async def test_create_evidence_references_bulk(mock_supabase):
    """EvidenceReferenceRepository persists multiple evidence items with session validation."""
    session_id = str(uuid4())
    user_id = str(uuid4())
    f1 = str(uuid4())
    s1 = str(uuid4())

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    mock_findings = MagicMock()
    mock_findings.select.return_value.eq.return_value.execute.return_value.data = [{"id": f1}]

    mock_sources = MagicMock()
    mock_sources.select.return_value.eq.return_value.execute.return_value.data = [{"id": s1}]

    mock_evidence = MagicMock()
    mock_evidence.insert.return_value.execute.return_value.data = [
        {"id": str(uuid4()), "finding_id": f1, "source_id": s1, "evidence_text": "Quote"}
    ]

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        elif table_name == "findings":
            return mock_findings
        elif table_name == "sources":
            return mock_sources
        return mock_evidence

    mock_supabase.table.side_effect = table_router

    repo = EvidenceReferenceRepository()
    results = await repo.create_evidence_references_bulk(
        session_id=session_id,
        user_id=user_id,
        evidence_items=[
            {
                "finding_id": f1,
                "source_id": s1,
                "evidence_text": "Quote",
                "evidence_type": "supporting",
            }
        ],
    )

    assert len(results) == 1


# =============================================================================
# 3. VerificationRepository Tests
# =============================================================================

@pytest.mark.anyio
async def test_create_verification_item_finding_specific(mock_supabase):
    """VerificationRepository creates finding-specific task verifying finding belongs to session."""
    session_id = str(uuid4())
    user_id = str(uuid4())
    finding_id = str(uuid4())
    item_id = str(uuid4())

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    mock_findings = MagicMock()
    mock_findings.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": finding_id}
    ]

    mock_items = MagicMock()
    mock_items.insert.return_value.execute.return_value.data = [
        {
            "id": item_id,
            "research_id": session_id,
            "finding_id": finding_id,
            "task": "Verify GPA requirement with department",
            "status": "pending",
        }
    ]

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        elif table_name == "findings":
            return mock_findings
        return mock_items

    mock_supabase.table.side_effect = table_router

    repo = VerificationRepository()
    result = await repo.create_verification_item(
        session_id=session_id,
        user_id=user_id,
        task="Verify GPA requirement with department",
        finding_id=finding_id,
    )

    assert result["id"] == item_id
    assert result["finding_id"] == finding_id
    assert result["status"] == "pending"


@pytest.mark.anyio
async def test_create_verification_item_general_unresolved_question(mock_supabase):
    """VerificationRepository supports general questions where finding_id is None."""
    session_id = str(uuid4())
    user_id = str(uuid4())
    item_id = str(uuid4())

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    mock_items = MagicMock()
    mock_items.insert.return_value.execute.return_value.data = [
        {
            "id": item_id,
            "research_id": session_id,
            "finding_id": None,
            "task": "What is the global tuition fee for 2026?",
            "status": "pending",
        }
    ]

    def table_router(table_name):
        return mock_sessions if table_name == "research_sessions" else mock_items

    mock_supabase.table.side_effect = table_router

    repo = VerificationRepository()
    result = await repo.create_verification_item(
        session_id=session_id,
        user_id=user_id,
        task="What is the global tuition fee for 2026?",
        finding_id=None,
    )

    assert result["id"] == item_id
    assert result["finding_id"] is None


@pytest.mark.anyio
async def test_update_item_status_completed_sets_completed_at(mock_supabase):
    """Status update to 'completed' sets completed_at and updated_at timestamps."""
    session_id = str(uuid4())
    user_id = str(uuid4())
    item_id = str(uuid4())

    mock_items = MagicMock()
    mock_items.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": item_id, "research_id": session_id, "status": "pending"}
    ]
    mock_items.update.return_value.eq.return_value.execute.return_value.data = [
        {
            "id": item_id,
            "status": "completed",
            "completed_at": "2026-11-01T12:00:00Z",
        }
    ]

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    def table_router(table_name):
        return mock_sessions if table_name == "research_sessions" else mock_items

    mock_supabase.table.side_effect = table_router

    repo = VerificationRepository()
    result = await repo.update_item_status(item_id, user_id, "completed")

    assert result["status"] == "completed"
    assert result["completed_at"] is not None


@pytest.mark.anyio
async def test_update_item_status_pending_clears_completed_at(mock_supabase):
    """Status update back to 'pending' clears completed_at to None."""
    session_id = str(uuid4())
    user_id = str(uuid4())
    item_id = str(uuid4())

    mock_items = MagicMock()
    mock_items.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": item_id, "research_id": session_id, "status": "completed"}
    ]
    mock_items.update.return_value.eq.return_value.execute.return_value.data = [
        {
            "id": item_id,
            "status": "pending",
            "completed_at": None,
        }
    ]

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    def table_router(table_name):
        return mock_sessions if table_name == "research_sessions" else mock_items

    mock_supabase.table.side_effect = table_router

    repo = VerificationRepository()
    result = await repo.update_item_status(item_id, user_id, "pending")

    assert result["status"] == "pending"
    assert result["completed_at"] is None


@pytest.mark.anyio
async def test_update_item_status_invalid_value_rejected(mock_supabase):
    """VerificationRepository rejects statuses outside pending/completed."""
    repo = VerificationRepository()
    with pytest.raises(ClarityXException) as exc_info:
        await repo.update_item_status("item-1", "user-1", "in_progress")

    assert exc_info.value.status_code == 400
    assert "Invalid verification status" in exc_info.value.message


@pytest.mark.anyio
async def test_update_item_status_unauthorized_rejection(mock_supabase):
    """VerificationRepository returns None when item belongs to another user's session."""
    session_id = str(uuid4())
    other_user_id = str(uuid4())
    item_id = str(uuid4())

    mock_items = MagicMock()
    mock_items.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": item_id, "research_id": session_id, "status": "pending"}
    ]

    mock_sessions = MagicMock()
    # verify_session_ownership returns empty because user does not own session
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

    def table_router(table_name):
        return mock_sessions if table_name == "research_sessions" else mock_items

    mock_supabase.table.side_effect = table_router

    repo = VerificationRepository()
    result = await repo.update_item_status(item_id, other_user_id, "completed")
    assert result is None


# =============================================================================
# 4. map_verification_to_finding_id Tests
# =============================================================================

def test_map_verification_general_question_resolves_to_none():
    """Explicit general questions resolve to None without requiring a title."""
    item = LLMVerificationItem(
        task="What is the overall admission timeline?",
        is_general_unresolved_question=True,
        related_finding_title=None,
    )
    findings = [{"id": str(uuid4()), "title": "Some Finding"}]

    finding_id = map_verification_to_finding_id(item, findings)
    assert finding_id is None


def test_map_verification_unique_normalized_title_match():
    """Finding-specific item resolves to the unique matching finding ID with case/whitespace normalization."""
    target_id = str(uuid4())
    findings = [
        {"id": target_id, "title": "Conflicting GPA Requirements"},
        {"id": str(uuid4()), "title": "Tuition Fee Missing"},
    ]
    item = LLMVerificationItem(
        task="Confirm GPA with admissions",
        is_general_unresolved_question=False,
        related_finding_title="  conflicting   gpa  requirements  ",
    )

    resolved_id = map_verification_to_finding_id(item, findings)
    assert resolved_id == target_id


def test_map_verification_duplicate_title_raises_error():
    """Ambiguous duplicate finding titles in session raise ClarityXException(400)."""
    findings = [
        {"id": str(uuid4()), "title": "Duplicate Title"},
        {"id": str(uuid4()), "title": "Duplicate Title"},
    ]
    item = LLMVerificationItem(
        task="Task",
        is_general_unresolved_question=False,
        related_finding_title="Duplicate Title",
    )

    with pytest.raises(ClarityXException) as exc_info:
        map_verification_to_finding_id(item, findings)

    assert exc_info.value.status_code == 400
    assert "Ambiguous finding title" in exc_info.value.message


def test_map_verification_unmatched_title_raises_error():
    """Unmatched related finding title raises ClarityXException(400); never silently converts to None."""
    findings = [
        {"id": str(uuid4()), "title": "Existing Title"}
    ]
    item = LLMVerificationItem(
        task="Task",
        is_general_unresolved_question=False,
        related_finding_title="Non Existent Title",
    )

    with pytest.raises(ClarityXException) as exc_info:
        map_verification_to_finding_id(item, findings)

    assert exc_info.value.status_code == 400
    assert "Unmatched finding title" in exc_info.value.message


def test_map_verification_missing_title_on_non_general_raises_error():
    """Non-general item without related_finding_title raises ClarityXException(400)."""
    item = LLMVerificationItem(
        task="Task",
        is_general_unresolved_question=False,
        related_finding_title=None,
    )
    findings = [{"id": str(uuid4()), "title": "Some Title"}]

    with pytest.raises(ClarityXException) as exc_info:
        map_verification_to_finding_id(item, findings)

    assert exc_info.value.status_code == 400
    assert "must specify a related finding title" in exc_info.value.message


# =============================================================================
# 5. Response Schemas Validation Tests
# =============================================================================

def test_evidence_reference_response_schema():
    """EvidenceReferenceResponse validates UUIDs, types, and source code."""
    ev_id = uuid4()
    f_id = uuid4()
    s_id = uuid4()

    ev = EvidenceReferenceResponse(
        id=ev_id,
        finding_id=f_id,
        source_id=s_id,
        source_code="S1",
        evidence_text="Verified quotation from document.",
        evidence_type="supporting",
        created_at=datetime.now(timezone.utc),
    )
    assert ev.id == ev_id
    assert ev.evidence_type == "supporting"
    assert ev.source_code == "S1"


def test_finding_response_schema_with_evidence():
    """FindingResponse supports attached evidence references and nullable confidence."""
    f_id = uuid4()
    ev = EvidenceReferenceResponse(
        id=uuid4(),
        finding_id=f_id,
        source_id=uuid4(),
        source_code="S1",
        evidence_text="Quote",
        evidence_type="contextual",
    )
    finding = FindingResponse(
        id=f_id,
        category="missing",
        title="Application Deadline",
        description="Deadline absent in sources",
        severity="high",
        confidence=0.92,
        recommended_action="Check registrar.",
        evidence_references=[ev],
    )
    assert finding.id == f_id
    assert finding.confidence == 0.92
    assert len(finding.evidence_references) == 1
    assert finding.evidence_references[0].source_code == "S1"

    # Preserves nullable confidence
    finding_no_conf = FindingResponse(
        id=f_id,
        category="missing",
        title="Title",
        description="Desc",
        severity="medium",
        confidence=None,
    )
    assert finding_no_conf.confidence is None


def test_verification_item_response_schemas():
    """VerificationItemResponse and UnresolvedQuestionResponse handle status and dates."""
    v_id = uuid4()
    f_id = uuid4()
    item = VerificationItemResponse(
        id=v_id,
        finding_id=f_id,
        task="Actionable task",
        status="pending",
        completed_at=None,
    )
    assert item.id == v_id
    assert item.finding_id == f_id
    assert item.status == "pending"

    unresolved = UnresolvedQuestionResponse(
        id=uuid4(),
        task="Broad open question?",
        status="pending",
    )
    assert unresolved.task == "Broad open question?"


def test_verification_status_update_schema():
    """VerificationStatusUpdate forbids extra fields and only allows pending/completed."""
    valid_completed = VerificationStatusUpdate(status="completed")
    assert valid_completed.status == "completed"

    valid_pending = VerificationStatusUpdate(status="pending")
    assert valid_pending.status == "pending"

    # Forbids invalid status
    with pytest.raises(Exception):
        VerificationStatusUpdate(status="in_progress")


def test_research_report_envelope_schema():
    """ResearchReportEnvelope encapsulates complete report conforming to API.md Section 5.1."""
    report_data = ResearchReportData(
        research_id=uuid4(),
        research_goal="Analyse scholarship requirements",
        status="completed",
        summary="Executive summary of findings",
        findings=[],
        sources=[],
        unresolved_questions=[],
        verification_items=[],
    )
    envelope = ResearchReportEnvelope(success=True, data=report_data)
    assert envelope.success is True
    assert envelope.data.status == "completed"


# =============================================================================
# 6. Database Error Translation & Cross-User Isolation Tests
# =============================================================================

@pytest.mark.anyio
async def test_database_error_handling_sanitizes_apierror(mock_supabase):
    """Repository translates PostgREST APIError into clean ClarityXException without leaking secrets."""
    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "session-1"}
    ]

    mock_findings = MagicMock()
    api_error = APIError(
        {"message": "check constraint violation: check_category", "code": "23514"}
    )
    mock_findings.insert.return_value.execute.side_effect = api_error

    def table_router(table_name):
        return mock_sessions if table_name == "research_sessions" else mock_findings

    mock_supabase.table.side_effect = table_router

    repo = FindingRepository()
    with pytest.raises(ClarityXException) as exc_info:
        await repo.create_finding(
            session_id="session-1",
            user_id="user-1",
            category="missing",
            title="Title",
            description="Desc",
        )

    assert exc_info.value.status_code == 400
    assert "Database operation failed" in exc_info.value.message


@pytest.mark.anyio
async def test_database_connection_error_on_unexpected_exception(mock_supabase):
    """Repository translates unexpected exceptions into DatabaseConnectionError."""
    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.side_effect = (
        RuntimeError("Network socket abruptly closed")
    )
    mock_supabase.table.return_value = mock_sessions

    repo = FindingRepository()
    with pytest.raises(DatabaseConnectionError) as exc_info:
        await repo.create_finding(
            session_id="session-1",
            user_id="user-1",
            category="missing",
            title="Title",
            description="Desc",
        )

    assert "Unable to complete database operation" in exc_info.value.message

