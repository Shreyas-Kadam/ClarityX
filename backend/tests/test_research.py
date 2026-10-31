"""Integration and unit tests for ClarityX research session persistence and CRUD APIs."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import DatabaseConnectionError
from app.database.repositories import ResearchRepository
from app.main import app
from app.schemas.research import ResearchSessionResponse


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
# 3. GET SINGLE RESEARCH SESSION TESTS
# =============================================================================

@pytest.mark.anyio
async def test_user_can_retrieve_their_own_session():
    """User can retrieve their own research session by ID."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    session_id = "33333333-3333-3333-3333-333333333333"

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    session_data = {
        "id": session_id,
        "user_id": alice_id,
        "research_goal": "AI Alignment gaps",
        "status": "completed",
        "summary": "Analyzed 4 sources",
        "created_at": "2026-10-31T12:00:00Z",
        "updated_at": "2026-10-31T12:00:00Z",
    }

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ResearchRepository, "get_session_by_id", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = session_data

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/research/{session_id}",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["id"] == session_id
            assert data["data"]["user_id"] == alice_id

            mock_get.assert_awaited_once_with(session_id=session_id, user_id=alice_id)


@pytest.mark.anyio
async def test_user_cannot_retrieve_another_users_session():
    """When a session belongs to another user, 404 is returned without leaking information."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    victim_session_id = "44444444-4444-4444-4444-444444444444"

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ResearchRepository, "get_session_by_id", new_callable=AsyncMock) as mock_get,
    ):
        # Repository queries for (id, alice_id) and returns None because owner is Bob
        mock_get.return_value = None

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/research/{victim_session_id}",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 404
            data = response.json()
            assert "Research session not found" in data["message"]


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

