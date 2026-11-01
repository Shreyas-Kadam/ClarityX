"""Integration and unit tests for ClarityX Analysis API Route (Phase 6.3.4.2).

Endpoint tested:
    POST /api/research/{research_id}/analyze

Tests:
 1. Successful analysis returns 200 with complete ResearchReportEnvelope.
 2. Missing authentication returns 401.
 3. Invalid research UUID returns 400.
 4. Nonexistent research session returns 404.
 5. Cross-user research session access returns 404.
 6. Session with no sources returns 400.
 7. Session where all sources failed extraction or have empty content returns 400.
 8. Correct conversion to SourceAnalysisInput schema (filters failed, keeps usable).
 9. Correct research goal from saved session passed to AIService.
10. AI service not configured returns 503 and preserves database.
11. AI timeout (AITimeoutError) returns 504 and preserves database.
12. AI provider failure (AIProviderError 502) returns 502 and preserves database.
13. AI response validation failure (AIResponseValidationError 502) returns 502.
14. Persistence preflight failure (unmatched finding title) returns 400.
15. Persistence service is strictly NOT called if AI analysis fails.
16. Successful response strictly uses ResearchReportEnvelope schema.
17. Full extracted_content is never exposed in response; previews only.
18. Correct authenticated user UUID is passed to persistence service.
19. Database is untouched when AI analysis fails.
20. Completed verification preservation payload is passed intact to persistence.
21. AI provider rate limit returns 429.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import (
    AIProviderError,
    AIResponseValidationError,
    AITimeoutError,
    ClarityXException,
    DatabaseConnectionError,
)
from app.database.repositories import ResearchRepository, SourceRepository
from app.main import app
from app.routes.research import (
    get_ai_service,
    get_analysis_persistence_service,
    get_research_repository,
    get_source_repository,
)
from app.schemas.analysis import (
    LLMAnalysisResponse,
    LLMEvidenceItem,
    LLMFindingItem,
    LLMVerificationItem,
    SourceAnalysisInput,
)
from app.schemas.research import (
    EvidenceReferenceResponse,
    FindingResponse,
    ResearchReportData,
    ResearchReportEnvelope,
    UnresolvedQuestionResponse,
    VerificationItemResponse,
)
from app.schemas.source import SourcePreviewResponse
from app.services.ai_service import AIService
from app.services.analysis_persistence_service import AnalysisPersistenceService


@pytest.fixture(autouse=True)
def reset_overrides():
    """Ensures dependency overrides are cleared after each test."""
    yield
    app.dependency_overrides.clear()


def create_mock_auth_user(
    user_id: str = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80",
    email: str = "alice@clarityx.dev",
    full_name: str = "Alice Researcher",
):
    """Helper creating a mocked Supabase Auth user response."""
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.email = email
    mock_user.user_metadata = {"full_name": full_name}

    mock_resp = MagicMock()
    mock_resp.user = mock_user
    return mock_resp


def make_sample_ai_response() -> LLMAnalysisResponse:
    """Creates a sample valid LLMAnalysisResponse."""
    return LLMAnalysisResponse(
        summary="Comprehensive executive summary of scholarship research and detected gaps.",
        findings=[
            LLMFindingItem(
                category="missing",
                title="Application Deadline Not Specified",
                description="Neither source provides the final date to apply.",
                severity="high",
                confidence=0.92,
                recommended_action="Contact admissions office directly.",
                evidence=[
                    LLMEvidenceItem(
                        source_code="S1",
                        quote="Scholarships will be awarded for the upcoming academic year.",
                        evidence_type="contextual",
                    )
                ],
            )
        ],
        verification_checklist=[
            LLMVerificationItem(
                task="Contact admissions office to verify application cutoff date.",
                is_general_unresolved_question=False,
                related_finding_title="Application Deadline Not Specified",
            ),
            LLMVerificationItem(
                task="What is the official GPA cutoff for international applicants?",
                is_general_unresolved_question=True,
                related_finding_title=None,
            ),
        ],
    )


def make_sample_report_data(session_id: str) -> ResearchReportData:
    """Creates a sample ResearchReportData matching AnalysisPersistenceService output."""
    s_uuid = UUID(session_id)
    f_uuid = uuid4()
    src_uuid = uuid4()
    now = datetime.now(timezone.utc)

    return ResearchReportData(
        research_id=s_uuid,
        research_goal="Investigate scholarship deadlines and eligibility",
        status="completed",
        summary="Comprehensive executive summary of scholarship research and detected gaps.",
        findings=[
            FindingResponse(
                id=f_uuid,
                research_id=s_uuid,
                category="missing",
                title="Application Deadline Not Specified",
                description="Neither source provides the final date to apply.",
                severity="high",
                confidence=0.92,
                recommended_action="Contact admissions office directly.",
                evidence_references=[
                    EvidenceReferenceResponse(
                        id=uuid4(),
                        finding_id=f_uuid,
                        source_id=src_uuid,
                        source_code="S1",
                        evidence_text="Scholarships will be awarded for the upcoming academic year.",
                        evidence_type="contextual",
                        created_at=now,
                    )
                ],
                created_at=now,
            )
        ],
        sources=[
            SourcePreviewResponse(
                id=src_uuid,
                research_id=s_uuid,
                source_code="S1",
                title="Scholarship Guidelines",
                url="https://example.com/scholarship",
                source_type="website",
                content_preview="Scholarships will be awarded for the upcoming academic year...",
                published_at=None,
                accessed_at=now,
                extraction_status="success",
                created_at=now,
            )
        ],
        unresolved_questions=[
            UnresolvedQuestionResponse(
                id=uuid4(),
                task="What is the official GPA cutoff for international applicants?",
                status="pending",
                created_at=now,
            )
        ],
        verification_items=[
            VerificationItemResponse(
                id=uuid4(),
                research_id=s_uuid,
                finding_id=f_uuid,
                task="Contact admissions office to verify application cutoff date.",
                status="pending",
                created_at=now,
                updated_at=now,
                completed_at=None,
            )
        ],
    )


# =============================================================================
# 1. SUCCESSFUL ANALYSIS ORCHESTRATION TESTS
# =============================================================================

@pytest.mark.anyio
async def test_analyze_success():
    """1. Successful analysis returns 200 with complete ResearchReportEnvelope."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    # Mock research repository
    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Investigate scholarship deadlines and eligibility",
        "status": "pending",
        "summary": "",
    })

    # Mock source repository
    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Scholarship Guidelines",
            "url": "https://example.com/scholarship",
            "source_type": "website",
            "extracted_content": "Scholarships will be awarded for the upcoming academic year. Apply soon.",
            "extraction_status": "success",
        }
    ])

    # Mock AI service
    ai_response = make_sample_ai_response()
    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock(return_value=ai_response)

    # Mock persistence service
    report_data = make_sample_report_data(session_id)
    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock(return_value=report_data)

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["message"] == "Research analysis completed successfully"
            assert data["data"]["research_id"] == session_id
            assert len(data["data"]["findings"]) == 1
            assert len(data["data"]["sources"]) == 1
            assert len(data["data"]["unresolved_questions"]) == 1
            assert len(data["data"]["verification_items"]) == 1

            mock_research_repo.get_session_by_id.assert_awaited_once_with(
                session_id=session_id,
                user_id=alice_id,
            )
            mock_source_repo.get_raw_sources_by_session.assert_awaited_once_with(
                session_id=session_id,
                user_id=alice_id,
            )
            mock_ai_service.analyze.assert_awaited_once()
            mock_persistence_service.persist_analysis.assert_awaited_once_with(
                session_id=session_id,
                user_id=alice_id,
                analysis=ai_response,
            )


# =============================================================================
# 2. AUTHENTICATION & INPUT VALIDATION TESTS
# =============================================================================

@pytest.mark.anyio
async def test_analyze_missing_authentication():
    """2. Missing authentication returns 401."""
    session_id = "11111111-2222-3333-4444-555555555555"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/research/{session_id}/analyze")
        assert response.status_code == 401
        assert response.json()["success"] is False


@pytest.mark.anyio
async def test_analyze_invalid_research_uuid():
    """3. Invalid research UUID returns 400."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/research/not-a-valid-uuid/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 400
            assert "Invalid research session ID" in response.json()["message"]


# =============================================================================
# 3. OWNERSHIP & SESSION ACCESS TESTS
# =============================================================================

@pytest.mark.anyio
async def test_analyze_nonexistent_research_session():
    """4. Nonexistent research session returns 404."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value=None)
    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 404
            assert "Research session not found" in response.json()["message"]


@pytest.mark.anyio
async def test_analyze_cross_user_research_session():
    """5. Cross-user research session access returns 404."""
    bob_id = "99999999-9999-9999-9999-999999999999"
    session_id = "11111111-2222-3333-4444-555555555555"  # Belongs to Alice

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=bob_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    # Repository filters by user_id so Bob sees None
    mock_research_repo.get_session_by_id = AsyncMock(return_value=None)
    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 404
            assert "Research session not found" in response.json()["message"]


# =============================================================================
# 4. SOURCE CONTENT VALIDATION TESTS
# =============================================================================

@pytest.mark.anyio
async def test_analyze_no_sources():
    """6. Session with no sources returns 400."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "A goal with no sources",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[])

    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock()

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock()

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 400
            assert "Insufficient source content for analysis" in response.json()["message"]
            assert "has no sources" in response.json()["detail"]

            mock_ai_service.analyze.assert_not_called()
            mock_persistence_service.persist_analysis.assert_not_called()


@pytest.mark.anyio
async def test_analyze_sources_with_unusable_empty_extracted_content():
    """7. Session where all sources failed extraction or have empty content returns 400."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Goal with failed sources",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Failed Website",
            "url": "https://example.com/fail",
            "source_type": "website",
            "extracted_content": "",
            "extraction_status": "failed",
        },
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S2",
            "title": "Whitespace Only",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "    \n\t  ",
            "extraction_status": "success",
        },
    ])

    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock()

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock()

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 400
            assert "failed extraction or have empty content" in response.json()["detail"]

            mock_ai_service.analyze.assert_not_called()
            mock_persistence_service.persist_analysis.assert_not_called()


@pytest.mark.anyio
async def test_analyze_correct_conversion_to_source_analysis_input():
    """8. Correct conversion to SourceAnalysisInput schema (filters failed, keeps usable)."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Conversion check",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Valid Website",
            "url": "https://example.com/one",
            "source_type": "website",
            "extracted_content": "Valid website text content.",
            "extraction_status": "success",
        },
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S2",
            "title": "Failed Source",
            "url": "https://example.com/failed",
            "source_type": "website",
            "extracted_content": "",
            "extraction_status": "failed",
        },
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S3",
            "title": "Pasted Notes",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "Valid notes text content.",
            "extraction_status": "success",
        },
    ])

    ai_response = make_sample_ai_response()
    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock(return_value=ai_response)

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock(return_value=make_sample_report_data(session_id))

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 200

            # Verify that only S1 and S3 were passed to AIService.analyze
            call_args = mock_ai_service.analyze.call_args
            assert call_args is not None
            passed_sources = call_args.kwargs.get("sources") or call_args.args[1]
            assert len(passed_sources) == 2
            assert all(isinstance(s, SourceAnalysisInput) for s in passed_sources)
            assert passed_sources[0].source_code == "S1"
            assert passed_sources[0].extracted_content == "Valid website text content."
            assert passed_sources[1].source_code == "S3"
            assert passed_sources[1].extracted_content == "Valid notes text content."


@pytest.mark.anyio
async def test_analyze_correct_research_goal_passed_to_ai_service():
    """9. Correct research goal from saved session passed to AIService."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"
    expected_goal = "Evaluate renewable energy subsidies in 2026"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": expected_goal,
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Subsidies Report",
            "url": "https://example.com/subsidies",
            "source_type": "website",
            "extracted_content": "Subsidy policies are active.",
            "extraction_status": "success",
        }
    ])

    ai_response = make_sample_ai_response()
    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock(return_value=ai_response)

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock(return_value=make_sample_report_data(session_id))

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 200

            call_args = mock_ai_service.analyze.call_args
            assert call_args is not None
            passed_goal = call_args.kwargs.get("research_goal") or call_args.args[0]
            assert passed_goal == expected_goal


# =============================================================================
# 5. AI FAILURE AND SAFE PRESERVATION TESTS
# =============================================================================

@pytest.mark.anyio
async def test_analyze_ai_service_not_configured():
    """10. AI service not configured returns 503 and preserves database."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Goal with unconfigured AI",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Source",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "Some content",
            "extraction_status": "success",
        }
    ])

    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = False
    mock_ai_service.client = None

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock()

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 503
            assert "AI service is not configured" in response.json()["message"]

            mock_persistence_service.persist_analysis.assert_not_called()


@pytest.mark.anyio
async def test_analyze_ai_timeout():
    """11. AI timeout (AITimeoutError) returns 504 and preserves database."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Goal that times out",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Source",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "Some content",
            "extraction_status": "success",
        }
    ])

    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock(side_effect=AITimeoutError(
        message="The AI analysis request timed out. Please try again.",
        detail="Request exceeded timeout.",
    ))

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock()

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 504
            assert "timed out" in response.json()["message"]

            mock_persistence_service.persist_analysis.assert_not_called()


@pytest.mark.anyio
async def test_analyze_ai_provider_failure():
    """12. AI provider failure (AIProviderError 502) returns 502 and preserves database."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Goal with failing provider",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Source",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "Some content",
            "extraction_status": "success",
        }
    ])

    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock(side_effect=AIProviderError(
        message="Unable to connect to the AI service provider.",
        detail="Connection to OpenRouter service failed.",
        status_code=502,
    ))

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock()

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 502
            assert "Unable to connect" in response.json()["message"]

            mock_persistence_service.persist_analysis.assert_not_called()


@pytest.mark.anyio
async def test_analyze_ai_response_validation_failure():
    """13. AI response validation failure (AIResponseValidationError 502) returns 502."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Goal with invalid output",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Source",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "Some content",
            "extraction_status": "success",
        }
    ])

    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock(side_effect=AIResponseValidationError(
        message="The AI model produced an invalid or unparseable analysis output.",
        detail="JSON validation failed.",
        status_code=502,
    ))

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock()

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 502
            assert "invalid or unparseable" in response.json()["message"]

            mock_persistence_service.persist_analysis.assert_not_called()


# =============================================================================
# 6. PERSISTENCE FAILURE SAFETY TESTS
# =============================================================================

@pytest.mark.anyio
async def test_analyze_persistence_preflight_failure():
    """14. Persistence preflight failure (unmatched finding title) returns 400."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Goal with mapping issue",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Source",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "Some content",
            "extraction_status": "success",
        }
    ])

    ai_response = make_sample_ai_response()
    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock(return_value=ai_response)

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock(side_effect=ClarityXException(
        message="Verification item references unknown finding title",
        status_code=400,
        detail="No finding matches title.",
    ))

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 400
            assert "unknown finding title" in response.json()["message"]


@pytest.mark.anyio
async def test_analyze_persistence_not_called_if_ai_fails():
    """15. Persistence service is strictly NOT called if AI analysis fails."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Goal where AI crashes",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Source",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "Valid source content",
            "extraction_status": "success",
        }
    ])

    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock(side_effect=AIProviderError("AI model crashed", status_code=502))

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock()

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 502

            # Crucial assertion: persist_analysis must NOT have been called
            mock_persistence_service.persist_analysis.assert_not_called()


# =============================================================================
# 7. RESPONSE ENVELOPE AND PRIVACY TESTS
# =============================================================================

@pytest.mark.anyio
async def test_analyze_successful_response_uses_research_report_envelope():
    """16. Successful response strictly matches ResearchReportEnvelope schema."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Schema validation check",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Source",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "Valid source content",
            "extraction_status": "success",
        }
    ])

    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock(return_value=make_sample_ai_response())

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock(return_value=make_sample_report_data(session_id))

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 200

            # Validate against Pydantic envelope model directly
            validated = ResearchReportEnvelope.model_validate(response.json())
            assert validated.success is True
            assert validated.data.research_id == UUID(session_id)


@pytest.mark.anyio
async def test_analyze_response_does_not_expose_extracted_content():
    """17. Full extracted_content is never exposed in response; previews only."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Privacy validation check",
    })

    secret_raw_content = "SECRET_EXTRACTED_CONTENT_NEVER_RETURN_IN_REPORT"
    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Source",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": secret_raw_content,
            "extraction_status": "success",
        }
    ])

    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock(return_value=make_sample_ai_response())

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock(return_value=make_sample_report_data(session_id))

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 200

            raw_response_text = response.text
            assert secret_raw_content not in raw_response_text
            assert "extracted_content" not in response.json()["data"]["sources"][0]
            assert "content_preview" in response.json()["data"]["sources"][0]


@pytest.mark.anyio
async def test_analyze_correct_authenticated_user_uuid_passed_to_persistence():
    """18. Correct authenticated user UUID is passed to persistence service."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "User ID check",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Source",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "Content",
            "extraction_status": "success",
        }
    ])

    ai_response = make_sample_ai_response()
    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock(return_value=ai_response)

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock(return_value=make_sample_report_data(session_id))

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 200

            # Ensure exact verified alice_id was passed, NOT any header or forged identity
            mock_persistence_service.persist_analysis.assert_awaited_once_with(
                session_id=session_id,
                user_id=alice_id,
                analysis=ai_response,
            )


@pytest.mark.anyio
async def test_analyze_existing_report_not_overwritten_when_ai_fails():
    """19. Database is untouched when AI analysis fails."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Preserve previous state test",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Source",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "Content",
            "extraction_status": "success",
        }
    ])

    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock(side_effect=AIProviderError("API connection error", status_code=502))

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock()

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 502
            mock_persistence_service.persist_analysis.assert_not_called()


@pytest.mark.anyio
async def test_analyze_completed_verification_preservation_payload():
    """20. Completed verification preservation payload is passed intact to persistence."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Checklist preservation test",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Source",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "Content",
            "extraction_status": "success",
        }
    ])

    ai_response = make_sample_ai_response()
    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock(return_value=ai_response)

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock(return_value=make_sample_report_data(session_id))

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 200

            call_args = mock_persistence_service.persist_analysis.call_args
            assert call_args is not None
            passed_analysis = call_args.kwargs.get("analysis") or call_args.args[2]
            assert len(passed_analysis.verification_checklist) == 2
            assert passed_analysis.verification_checklist[0].task == "Contact admissions office to verify application cutoff date."


@pytest.mark.anyio
async def test_analyze_ai_provider_rate_limit_returns_429():
    """21. AI provider rate limit returns 429."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Goal hitting rate limit",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.get_raw_sources_by_session = AsyncMock(return_value=[
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Source",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "Content",
            "extraction_status": "success",
        }
    ])

    mock_ai_service = MagicMock(spec=AIService)
    mock_ai_service.settings = MagicMock()
    mock_ai_service.settings.is_ai_configured = True
    mock_ai_service.client = MagicMock()
    mock_ai_service.analyze = AsyncMock(side_effect=AIProviderError(
        message="The AI service rate limit has been exceeded. Please try again shortly.",
        detail="OpenRouter rate limit reached.",
        status_code=429,
    ))

    mock_persistence_service = MagicMock(spec=AnalysisPersistenceService)
    mock_persistence_service.persist_analysis = AsyncMock()

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    app.dependency_overrides[get_analysis_persistence_service] = lambda: mock_persistence_service

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{session_id}/analyze",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 429
            assert "rate limit has been exceeded" in response.json()["message"]
            mock_persistence_service.persist_analysis.assert_not_called()
