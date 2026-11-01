"""Integration and unit tests for ClarityX research session persistence and CRUD APIs."""

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import ClarityXException, DatabaseConnectionError
from app.database.repositories import (
    EvidenceReferenceRepository,
    FindingRepository,
    ResearchRepository,
    SourceRepository,
    VerificationRepository,
)
from app.main import app
from app.schemas.research import (
    EvidenceReferenceResponse,
    FindingResponse,
    ResearchReportData,
    ResearchReportEnvelope,
    ResearchSessionResponse,
    UnresolvedQuestionResponse,
    VerificationItemResponse,
)
from app.schemas.source import SourcePreviewResponse


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


def make_sample_report_data(
    session_id: str,
    user_id: str = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80",
    status: str = "completed",
    summary: str = "Comprehensive executive summary of quantum research.",
) -> ResearchReportData:
    """Creates a sample valid ResearchReportData for tests."""
    s_uuid = UUID(session_id)
    f_uuid = uuid4()
    src_uuid = uuid4()
    ev_uuid = uuid4()
    vq_uuid = uuid4()
    vt_uuid = uuid4()
    now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)

    return ResearchReportData(
        research_id=s_uuid,
        research_goal="Investigate quantum computing gap",
        status=status,
        summary=summary,
        findings=[
            FindingResponse(
                id=f_uuid,
                research_id=s_uuid,
                category="missing",
                title="Qubit Decoherence Timeline Omitted",
                description="The source text omits critical decoherence thresholds.",
                severity="high",
                confidence=0.88,
                recommended_action="Cross-reference with recent hardware benchmarks.",
                evidence_references=[
                    EvidenceReferenceResponse(
                        id=ev_uuid,
                        finding_id=f_uuid,
                        source_id=src_uuid,
                        source_code="S1",
                        evidence_text="Superconducting qubits require millikelvin temperatures.",
                        evidence_type="supporting",
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
                title="Quantum Hardware Review 2026",
                url="https://example.com/quantum",
                source_type="website",
                content_preview="Superconducting qubits require millikelvin temperatures...",
                published_at=None,
                accessed_at=now,
                extraction_status="success",
                created_at=now,
            )
        ],
        unresolved_questions=[
            UnresolvedQuestionResponse(
                id=vq_uuid,
                task="What error correction threshold is required for fault tolerance?",
                status="pending",
                created_at=now,
            )
        ],
        verification_items=[
            VerificationItemResponse(
                id=vt_uuid,
                research_id=s_uuid,
                finding_id=f_uuid,
                task="Verify millikelvin cooling requirement against manufacturer specs.",
                status="completed",
                created_at=now,
                updated_at=now,
                completed_at=now,
            )
        ],
    )


# =============================================================================
# 1. CREATE RESEARCH SESSION TESTS
# =============================================================================

@pytest.mark.anyio
async def test_create_research_session_success():
    """Authenticated user can create a research session with verified user_id."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "11111111-2222-3333-4444-555555555555"

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    created_session = {
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Investigate quantum computing gap",
        "status": "pending",
        "summary": "",
        "created_at": "2026-10-31T12:00:00Z",
        "updated_at": "2026-10-31T12:00:00Z",
    }

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ResearchRepository, "create_session", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = created_session

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/research",
                headers={"Authorization": "Bearer valid-token"},
                json={"research_goal": "Investigate quantum computing gap"},
            )

            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True
            assert data["message"] == "Research session created successfully"
            assert data["data"]["id"] == session_id
            assert data["data"]["user_id"] == alice_id
            assert data["data"]["research_goal"] == "Investigate quantum computing gap"
            assert data["data"]["status"] == "pending"

            mock_create.assert_awaited_once_with(
                user_id=alice_id,
                research_goal="Investigate quantum computing gap",
            )


@pytest.mark.anyio
async def test_client_cannot_spoof_user_id_on_create():
    """Extra fields such as user_id in payload are rejected with 422."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    attacker_bob_id = "99999999-9999-9999-9999-999999999999"

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/research",
                headers={"Authorization": "Bearer valid-token"},
                json={
                    "research_goal": "Spoof attempt",
                    "user_id": attacker_bob_id,
                },
            )

            # Extra forbidden raises 422
            assert response.status_code == 422
            data = response.json()
            assert data["success"] is False


@pytest.mark.anyio
async def test_empty_research_goal_rejected():
    """Empty or whitespace-only research goals are rejected with 422."""
    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user()

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/research",
                headers={"Authorization": "Bearer valid-token"},
                json={"research_goal": "    "},
            )

            assert response.status_code == 422


# =============================================================================
# 2. LIST RESEARCH SESSIONS TESTS
# =============================================================================

@pytest.mark.anyio
async def test_user_can_list_only_their_own_sessions():
    """Listing sessions strictly filters by the authenticated user's ID."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_sessions = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "user_id": alice_id,
            "research_goal": "Goal 1",
            "status": "completed",
            "summary": "Summary 1",
            "created_at": "2026-10-31T12:00:00Z",
            "updated_at": "2026-10-31T12:30:00Z",
        },
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "user_id": alice_id,
            "research_goal": "Goal 2",
            "status": "pending",
            "summary": "",
            "created_at": "2026-10-31T13:00:00Z",
            "updated_at": "2026-10-31T13:00:00Z",
        },
    ]

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ResearchRepository, "list_user_sessions", new_callable=AsyncMock) as mock_list,
        patch.object(ResearchRepository, "count_user_sessions", new_callable=AsyncMock) as mock_count,
    ):
        mock_list.return_value = mock_sessions
        mock_count.return_value = 2

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/research?limit=10&offset=0",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"]["total"] == 2
            assert len(data["data"]["research_sessions"]) == 2
            assert data["data"]["research_sessions"][0]["id"] == "11111111-1111-1111-1111-111111111111"

            mock_list.assert_awaited_once_with(
                user_id=alice_id,
                limit=10,
                offset=0,
                status=None,
            )


@pytest.mark.anyio
async def test_empty_research_list_returns_valid_empty_response():
    """When a user has no sessions, list endpoint returns an empty array with total 0."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ResearchRepository, "list_user_sessions", new_callable=AsyncMock) as mock_list,
        patch.object(ResearchRepository, "count_user_sessions", new_callable=AsyncMock) as mock_count,
    ):
        mock_list.return_value = []
        mock_count.return_value = 0

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/research",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"]["research_sessions"] == []
            assert data["data"]["total"] == 0


@pytest.mark.anyio
async def test_list_research_sessions_invalid_status_filter():
    """Invalid status query filter is rejected with 400."""
    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user()

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/research?status=invalid_status_value",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 400
            data = response.json()
            assert "Invalid status filter" in data["message"]


# =============================================================================
# 3. GET SINGLE RESEARCH REPORT TESTS (PHASE 6.3.5)
# =============================================================================

@pytest.mark.anyio
async def test_user_can_retrieve_complete_research_report():
    """Authenticated user can retrieve complete research report with all sections."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "33333333-3333-3333-3333-333333333333"

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    sample_report = make_sample_report_data(session_id=session_id, user_id=alice_id)

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ResearchRepository, "get_research_report", new_callable=AsyncMock) as mock_get_report,
    ):
        mock_get_report.return_value = sample_report

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/research/{session_id}",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            report = data["data"]
            assert report["research_id"] == session_id
            assert report["research_goal"] == "Investigate quantum computing gap"
            assert report["status"] == "completed"
            assert "quantum" in report["summary"].lower()

            # Findings with nested evidence
            assert len(report["findings"]) == 1
            f0 = report["findings"][0]
            assert f0["category"] == "missing"
            assert f0["title"] == "Qubit Decoherence Timeline Omitted"
            assert len(f0["evidence_references"]) == 1
            ev0 = f0["evidence_references"][0]
            assert ev0["source_code"] == "S1"
            assert "millikelvin" in ev0["evidence_text"]

            # Sources with privacy preview
            assert len(report["sources"]) == 1
            src0 = report["sources"][0]
            assert src0["source_code"] == "S1"
            assert "extracted_content" not in src0
            assert "content_preview" in src0

            # Unresolved questions & verification items partitioned
            assert len(report["unresolved_questions"]) == 1
            assert "fault tolerance" in report["unresolved_questions"][0]["task"]
            assert len(report["verification_items"]) == 1
            assert report["verification_items"][0]["status"] == "completed"
            assert report["verification_items"][0]["completed_at"] is not None

            mock_get_report.assert_awaited_once_with(session_id=session_id, user_id=alice_id)


@pytest.mark.anyio
async def test_user_can_retrieve_unanalyzed_session_report():
    """Unanalyzed sessions (pending/processing) return valid report with empty finding lists."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "33333333-3333-3333-3333-333333333333"

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    unanalyzed_report = ResearchReportData(
        research_id=UUID(session_id),
        research_goal="Unanalyzed research goal",
        status="pending",
        summary="",
        findings=[],
        sources=[
            SourcePreviewResponse(
                id=uuid4(),
                research_id=UUID(session_id),
                source_code="S1",
                title="Added source before analysis",
                url="https://example.com/source1",
                source_type="website",
                content_preview="Preliminary text...",
                published_at=None,
                accessed_at=now,
                extraction_status="success",
                created_at=now,
            )
        ],
        unresolved_questions=[],
        verification_items=[],
    )

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ResearchRepository, "get_research_report", new_callable=AsyncMock) as mock_get_report,
    ):
        mock_get_report.return_value = unanalyzed_report

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/research/{session_id}",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            report = data["data"]
            assert report["status"] == "pending"
            assert report["findings"] == []
            assert report["unresolved_questions"] == []
            assert report["verification_items"] == []
            assert len(report["sources"]) == 1


@pytest.mark.anyio
async def test_get_research_report_nonexistent_session_returns_404():
    """When a session does not exist, 404 is returned with standard error envelope."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    missing_session_id = "44444444-4444-4444-4444-444444444444"

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ResearchRepository, "get_research_report", new_callable=AsyncMock) as mock_get_report,
    ):
        mock_get_report.return_value = None

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/research/{missing_session_id}",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 404
            data = response.json()
            assert data["success"] is False
            assert "Research session not found" in data["message"]


@pytest.mark.anyio
async def test_get_research_report_cross_user_isolation_returns_404():
    """When a session belongs to another user, 404 is returned without leaking information."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    bob_session_id = "55555555-5555-5555-5555-555555555555"

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ResearchRepository, "get_research_report", new_callable=AsyncMock) as mock_get_report,
    ):
        # Repository enforces ownership and returns None because owner is Bob
        mock_get_report.return_value = None

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/research/{bob_session_id}",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 404
            data = response.json()
            assert data["success"] is False
            assert "Research session not found" in data["message"]
            assert "bob" not in response.text.lower()


@pytest.mark.anyio
async def test_get_research_report_database_failure_returns_503():
    """Database exception during get_research_report returns HTTP 503 without leaking credentials."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "66666666-6666-6666-6666-666666666666"

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    # Raw database exception containing sensitive connection string
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_select.execute.side_effect = RuntimeError(
        "FATAL: connection failure for postgres:secret_password_123@db:5432"
    )
    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_select

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch("app.database.repositories.get_supabase_client", return_value=mock_client),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/research/{session_id}",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 503
            data = response.json()
            assert data["success"] is False
            assert "secret_password_123" not in response.text
            assert "Unable to complete database operation" in data["message"]


# =============================================================================
# 3b. REPOSITORY UNIT TESTS: get_research_report
# =============================================================================

@pytest.mark.anyio
async def test_repo_get_research_report_aggregation_and_grouping():
    """Repository aggregates findings, groups evidence references, partitions tasks, and lists sources."""
    user_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "77777777-7777-7777-7777-777777777777"
    f1_id = "aaaaaaaa-1111-1111-1111-111111111111"
    f2_id = "bbbbbbbb-2222-2222-2222-222222222222"
    src1_id = "cccccccc-3333-3333-3333-333333333333"
    src2_id = "dddddddd-4444-4444-4444-444444444444"
    ev1_id = "eeeeeeee-5555-5555-5555-555555555555"
    ev2_id = "ffffffff-6666-6666-6666-666666666666"
    ev3_id = "10101010-7777-7777-7777-777777777777"
    uq_id = "20202020-8888-8888-8888-888888888888"
    vt_id = "30303030-9999-9999-9999-999999999999"

    mock_finding_repo = MagicMock(spec=FindingRepository)
    mock_evidence_repo = MagicMock(spec=EvidenceReferenceRepository)
    mock_verification_repo = MagicMock(spec=VerificationRepository)
    mock_source_repo = MagicMock(spec=SourceRepository)

    repo = ResearchRepository(
        finding_repo=mock_finding_repo,
        evidence_repo=mock_evidence_repo,
        verification_repo=mock_verification_repo,
        source_repo=mock_source_repo,
    )

    # 1. Mock session
    repo.get_session_by_id = AsyncMock(
        return_value={
            "id": session_id,
            "user_id": user_id,
            "research_goal": "Compare deep learning architectures",
            "status": "completed",
            "summary": "Deep learning analysis completed successfully.",
        }
    )

    # 2. Mock findings (2 findings)
    mock_finding_repo.get_findings_by_session = AsyncMock(
        return_value=[
            {
                "id": f1_id,
                "research_id": session_id,
                "category": "missing",
                "title": "Transformer Attention Complexity",
                "description": "Quadratic complexity not mentioned.",
                "severity": "medium",
                "confidence": 0.85,
                "recommended_action": "Consult Vaswani et al.",
            },
            {
                "id": f2_id,
                "research_id": session_id,
                "category": "conflicting",
                "title": "Batch Normalization vs Layer Normalization",
                "description": "Conflicting claims on convergence rate.",
                "severity": "high",
                "confidence": 0.90,
                "recommended_action": "Benchmark both normalizers.",
            },
        ]
    )

    # 3. Mock evidence (2 for f1, 1 for f2, with source_code from join)
    mock_evidence_repo.get_evidence_for_findings = AsyncMock(
        return_value=[
            {
                "id": ev1_id,
                "finding_id": f1_id,
                "source_id": src1_id,
                "source_code": "S1",
                "evidence_text": "Standard self-attention scales quadratically with length.",
                "evidence_type": "supporting",
            },
            {
                "id": ev2_id,
                "finding_id": f1_id,
                "source_id": src2_id,
                "source_code": "S2",
                "evidence_text": "Linear attention mitigates memory bounds.",
                "evidence_type": "contextual",
            },
            {
                "id": ev3_id,
                "finding_id": f2_id,
                "source_id": src1_id,
                "source_code": "S1",
                "evidence_text": "LayerNorm stabilizes hidden state dynamics.",
                "evidence_type": "contradicting",
            },
        ]
    )

    # 4. Mock verification items (1 unresolved question with finding_id=None, 1 task with finding_id=f1_id)
    now_str = "2026-10-31T15:00:00Z"
    mock_verification_repo.list_items_by_session = AsyncMock(
        return_value=[
            {
                "id": uq_id,
                "research_id": session_id,
                "finding_id": None,
                "task": "Does FlashAttention-3 provide speedup on Hopper GPUs?",
                "status": "pending",
                "created_at": now_str,
            },
            {
                "id": vt_id,
                "research_id": session_id,
                "finding_id": f1_id,
                "task": "Profile attention memory consumption up to 8k tokens.",
                "status": "completed",
                "created_at": now_str,
                "updated_at": now_str,
                "completed_at": now_str,
            },
        ]
    )

    # 5. Mock source previews
    mock_source_repo.list_sources = AsyncMock(
        return_value={
            "sources": [
                {
                    "id": src1_id,
                    "research_id": session_id,
                    "source_code": "S1",
                    "title": "Attention Is All You Need",
                    "url": "https://arxiv.org/abs/1706.03762",
                    "source_type": "website",
                    "content_preview": "The dominant sequence transduction models...",
                    "accessed_at": now_str,
                    "extraction_status": "success",
                    "created_at": now_str,
                },
                {
                    "id": src2_id,
                    "research_id": session_id,
                    "source_code": "S2",
                    "title": "Transformers Are RNNs",
                    "url": "https://arxiv.org/abs/2006.16236",
                    "source_type": "website",
                    "content_preview": "Linear Transformers achieve linear complexity...",
                    "accessed_at": now_str,
                    "extraction_status": "success",
                    "created_at": now_str,
                },
            ],
            "total": 2,
        }
    )

    # Execute
    report = await repo.get_research_report(session_id=session_id, user_id=user_id)

    assert report is not None
    assert str(report.research_id) == session_id
    assert report.research_goal == "Compare deep learning architectures"
    assert report.status == "completed"
    assert report.summary == "Deep learning analysis completed successfully."

    # Evidence grouping verification
    assert len(report.findings) == 2
    f1 = next(f for f in report.findings if str(f.id) == f1_id)
    f2 = next(f for f in report.findings if str(f.id) == f2_id)

    assert len(f1.evidence_references) == 2
    assert {e.source_code for e in f1.evidence_references} == {"S1", "S2"}
    assert any("quadratically" in e.evidence_text for e in f1.evidence_references)

    assert len(f2.evidence_references) == 1
    assert f2.evidence_references[0].source_code == "S1"
    assert "LayerNorm" in f2.evidence_references[0].evidence_text

    # Partitioning verification
    assert len(report.unresolved_questions) == 1
    assert str(report.unresolved_questions[0].id) == uq_id
    assert "FlashAttention" in report.unresolved_questions[0].task

    assert len(report.verification_items) == 1
    vt = report.verification_items[0]
    assert str(vt.id) == vt_id
    assert str(vt.finding_id) == f1_id
    assert vt.status == "completed"
    assert vt.completed_at is not None

    # Sources verification
    assert len(report.sources) == 2
    assert {s.source_code for s in report.sources} == {"S1", "S2"}
    # Verify extracted_content is not an attribute of SourcePreviewResponse
    for s in report.sources:
        assert not hasattr(s, "extracted_content")
        assert s.content_preview is not None


@pytest.mark.anyio
async def test_repo_get_research_report_returns_none_if_session_not_found():
    """Repository returns None when session is nonexistent or foreign without calling sub-repos."""
    user_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "88888888-8888-8888-8888-888888888888"

    mock_finding_repo = MagicMock(spec=FindingRepository)
    mock_evidence_repo = MagicMock(spec=EvidenceReferenceRepository)

    repo = ResearchRepository(
        finding_repo=mock_finding_repo,
        evidence_repo=mock_evidence_repo,
    )
    repo.get_session_by_id = AsyncMock(return_value=None)

    report = await repo.get_research_report(session_id=session_id, user_id=user_id)

    assert report is None
    mock_finding_repo.get_findings_by_session.assert_not_called()
    mock_evidence_repo.get_evidence_for_findings.assert_not_called()


@pytest.mark.anyio
async def test_repo_get_research_report_empty_findings_does_not_query_evidence():
    """When a session has no findings, evidence repository is safely skipped."""
    user_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "99999999-9999-9999-9999-999999999999"

    mock_finding_repo = MagicMock(spec=FindingRepository)
    mock_evidence_repo = MagicMock(spec=EvidenceReferenceRepository)
    mock_verification_repo = MagicMock(spec=VerificationRepository)
    mock_source_repo = MagicMock(spec=SourceRepository)

    repo = ResearchRepository(
        finding_repo=mock_finding_repo,
        evidence_repo=mock_evidence_repo,
        verification_repo=mock_verification_repo,
        source_repo=mock_source_repo,
    )

    repo.get_session_by_id = AsyncMock(
        return_value={
            "id": session_id,
            "user_id": user_id,
            "research_goal": "Clean session without findings",
            "status": "pending",
            "summary": "",
        }
    )
    mock_finding_repo.get_findings_by_session = AsyncMock(return_value=[])
    mock_evidence_repo.get_evidence_for_findings = AsyncMock()
    mock_verification_repo.list_items_by_session = AsyncMock(return_value=[])
    mock_source_repo.list_sources = AsyncMock(return_value={"sources": [], "total": 0})

    report = await repo.get_research_report(session_id=session_id, user_id=user_id)

    assert report is not None
    assert report.findings == []
    # Critical requirement: evidence repo MUST NOT be called with empty finding IDs
    mock_evidence_repo.get_evidence_for_findings.assert_not_called()


@pytest.mark.anyio
async def test_repo_get_research_report_child_query_failure_propagates():
    """If a child repository query fails, exception propagates to prevent partial reports."""
    user_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    mock_finding_repo = MagicMock(spec=FindingRepository)
    repo = ResearchRepository(
        finding_repo=mock_finding_repo,
    )

    repo.get_session_by_id = AsyncMock(
        return_value={
            "id": session_id,
            "user_id": user_id,
            "research_goal": "Goal with failing child",
            "status": "completed",
            "summary": "",
        }
    )
    mock_finding_repo.get_findings_by_session = AsyncMock(
        side_effect=DatabaseConnectionError("Database query failed")
    )

    with pytest.raises(DatabaseConnectionError):
        await repo.get_research_report(session_id=session_id, user_id=user_id)


# =============================================================================
# 4. UPDATE RESEARCH SESSION TESTS
# =============================================================================

@pytest.mark.anyio
async def test_user_can_update_their_own_session():
    """User can update research_goal, status, and summary on their own session."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "55555555-5555-5555-5555-555555555555"

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    updated_data = {
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "Updated Goal",
        "status": "processing",
        "summary": "Processing in progress",
        "created_at": "2026-10-31T12:00:00Z",
        "updated_at": "2026-10-31T12:45:00Z",
    }

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ResearchRepository, "update_session", new_callable=AsyncMock) as mock_update,
    ):
        mock_update.return_value = updated_data

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/research/{session_id}",
                headers={"Authorization": "Bearer valid-token"},
                json={
                    "research_goal": "Updated Goal",
                    "status": "processing",
                    "summary": "Processing in progress",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Research session updated successfully"
            assert data["data"]["status"] == "processing"
            assert data["data"]["research_goal"] == "Updated Goal"


@pytest.mark.anyio
async def test_user_cannot_update_another_users_session():
    """Updating a session owned by another user returns 404."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    victim_session_id = "66666666-6666-6666-6666-666666666666"

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ResearchRepository, "update_session", new_callable=AsyncMock) as mock_update,
    ):
        mock_update.return_value = None

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/research/{victim_session_id}",
                headers={"Authorization": "Bearer valid-token"},
                json={"status": "completed"},
            )

            assert response.status_code == 404
            data = response.json()
            assert "Research session not found" in data["message"]


@pytest.mark.anyio
async def test_update_session_invalid_status_rejected():
    """Setting an invalid status in update is rejected with 422."""
    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user()

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                "/api/research/11111111-2222-3333-4444-555555555555",
                headers={"Authorization": "Bearer valid-token"},
                json={"status": "unsupported_status"},
            )

            assert response.status_code == 422


# =============================================================================
# 5. DELETE RESEARCH SESSION TESTS
# =============================================================================

@pytest.mark.anyio
async def test_user_can_delete_their_own_session():
    """User can delete their own session and receives exact standard response."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "77777777-7777-7777-7777-777777777777"

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ResearchRepository, "delete_session", new_callable=AsyncMock) as mock_delete,
    ):
        mock_delete.return_value = True

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/research/{session_id}",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["message"] == "Research deleted successfully"

            mock_delete.assert_awaited_once_with(session_id=session_id, user_id=alice_id)


@pytest.mark.anyio
async def test_user_cannot_delete_another_users_session():
    """Attempting to delete another user's session returns 404."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    victim_session_id = "88888888-8888-8888-8888-888888888888"

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ResearchRepository, "delete_session", new_callable=AsyncMock) as mock_delete,
    ):
        mock_delete.return_value = False

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/research/{victim_session_id}",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 404
            data = response.json()
            assert "Research session not found" in data["message"]


# =============================================================================
# 6. INVALID UUID VALIDATION TESTS
# =============================================================================

@pytest.mark.parametrize("invalid_id", ["not-a-uuid", "12345", "xyz-abc-123", "   "])
@pytest.mark.anyio
async def test_invalid_uuid_returns_client_error(invalid_id: str):
    """Non-UUID path identifiers return HTTP 400 client error."""
    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user()

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/research/{invalid_id}",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 400
            data = response.json()
            assert "Invalid research session ID" in data["message"]


# =============================================================================
# 7. SANITIZED DATABASE FAILURES
# =============================================================================

@pytest.mark.anyio
async def test_database_failure_returns_sanitized_error():
    """Database connection failures return clean HTTP 503 without leaking credentials."""
    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user()

    # Raw driver exception containing connection string with credentials
    mock_table = MagicMock()
    mock_insert = MagicMock()
    mock_insert.execute.side_effect = RuntimeError(
        "FATAL: database password failure for postgres:secret_pass_123@db:5432"
    )
    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_insert

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch("app.database.repositories.get_supabase_client", return_value=mock_client),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/research",
                headers={"Authorization": "Bearer valid-token"},
                json={"research_goal": "Goal that causes database error"},
            )

            assert response.status_code == 503
            data = response.json()
            assert data["success"] is False
            assert "secret_pass_123" not in response.text
            assert "Unable to complete database operation" in data["message"]


# =============================================================================
# 8. UNAUTHENTICATED ENDPOINT ACCESS
# =============================================================================

@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/research"),
        ("GET", "/api/research"),
        ("GET", "/api/research/11111111-2222-3333-4444-555555555555"),
        ("PATCH", "/api/research/11111111-2222-3333-4444-555555555555"),
        ("DELETE", "/api/research/11111111-2222-3333-4444-555555555555"),
    ],
)
@pytest.mark.anyio
async def test_unauthenticated_research_endpoints_receive_401(method: str, path: str):
    """All research endpoints reject unauthenticated access with 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(method, path)
        assert response.status_code == 401
        assert response.json()["success"] is False

