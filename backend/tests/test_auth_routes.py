"""Integration tests for ClarityX authenticated routes (GET /api/auth/me)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import ClarityXException, DatabaseConnectionError
from app.database.repositories import ProfileRepository
from app.main import app
from app.schemas.auth import UserProfileResponse


def create_mock_supabase_user(
    user_id: str = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80",
    email: str = "alice@example.com",
    full_name: str = "Alice Smith",
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
# 1. AUTHENTICATED USER WITH EXISTING PROFILE
# =============================================================================

@pytest.mark.anyio
async def test_get_current_user_profile_success():
    """Authenticated user with an existing profile receives HTTP 200 with profile data."""
    user_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    mock_auth_resp = create_mock_supabase_user(user_id=user_id, email="alice@example.com", full_name="Alice Smith")

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = mock_auth_resp

    profile_data = {
        "id": user_id,
        "email": "alice@example.com",
        "full_name": "Alice Smith",
        "created_at": "2026-10-31T12:00:00Z",
        "updated_at": "2026-10-31T12:00:00Z",
    }

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ProfileRepository, "get_by_id", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = profile_data

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer valid-alice-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == user_id
            assert data["email"] == "alice@example.com"
            assert data["full_name"] == "Alice Smith"
            assert data["created_at"] is not None

            # Verify repository was queried with verified user ID
            mock_get.assert_awaited_once_with(user_id)


# =============================================================================
# 2. MISSING PROFILE IS CREATED AND RETURNED
# =============================================================================

@pytest.mark.anyio
async def test_missing_profile_is_created_and_returned():
    """If profile is absent, it is automatically initialized and returned."""
    user_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    mock_auth_resp = create_mock_supabase_user(user_id=user_id, email="bob@example.com", full_name="Bob Jones")

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = mock_auth_resp

    created_profile = {
        "id": user_id,
        "email": "bob@example.com",
        "full_name": "Bob Jones",
        "created_at": "2026-10-31T12:05:00Z",
        "updated_at": "2026-10-31T12:05:00Z",
    }

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ProfileRepository, "get_by_id", new_callable=AsyncMock) as mock_get,
        patch.object(ProfileRepository, "create_profile", new_callable=AsyncMock) as mock_create,
    ):
        # First lookup returns None (missing profile)
        mock_get.return_value = None
        mock_create.return_value = created_profile

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer valid-bob-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == user_id
            assert data["email"] == "bob@example.com"
            assert data["full_name"] == "Bob Jones"

            # Verify create was invoked with verified user ID
            mock_create.assert_awaited_once_with(
                user_id=user_id,
                email="bob@example.com",
                full_name="Bob Jones",
            )


# =============================================================================
# 3. UNAUTHENTICATED REQUEST RECEIVES HTTP 401
# =============================================================================

@pytest.mark.anyio
async def test_unauthenticated_request_receives_401():
    """Request without Authorization header is rejected with 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/auth/me")

        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert "Missing Authorization header" in data["message"]


# =============================================================================
# 4. INVALID TOKEN RECEIVES HTTP 401
# =============================================================================

@pytest.mark.anyio
async def test_invalid_token_receives_401():
    """Request with invalid Bearer token is rejected with 401."""
    mock_client = MagicMock()
    mock_client.auth.get_user.side_effect = Exception("JWT signature is invalid")

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer bad-token-signature"},
            )

            assert response.status_code == 401
            data = response.json()
            assert data["success"] is False
            assert "Invalid or expired authentication token" in data["message"]


# =============================================================================
# 5. USER CANNOT RETRIEVE ANOTHER USER'S PROFILE
# =============================================================================

@pytest.mark.anyio
async def test_user_cannot_retrieve_another_users_profile():
    """User ID cannot be overridden via query parameters or arbitrary inputs."""
    alice_id = "00000000-0000-0000-0000-000000000001"
    victim_bob_id = "99999999-9999-9999-9999-999999999999"

    mock_auth_resp = create_mock_supabase_user(user_id=alice_id, email="alice@test.com", full_name="Alice")

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = mock_auth_resp

    alice_profile = {
        "id": alice_id,
        "email": "alice@test.com",
        "full_name": "Alice",
        "created_at": "2026-10-31T12:00:00Z",
        "updated_at": "2026-10-31T12:00:00Z",
    }

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ProfileRepository, "get_by_id", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = alice_profile

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Attacker sends spoofed user_id in query parameter
            response = await client.get(
                f"/api/auth/me?user_id={victim_bob_id}&id={victim_bob_id}",
                headers={
                    "Authorization": "Bearer alice-valid-token",
                    "X-User-Id": victim_bob_id,
                },
            )

            assert response.status_code == 200
            data = response.json()
            # Verified identity must be Alice, NOT Bob
            assert data["id"] == alice_id
            assert data["email"] == "alice@test.com"

            # Profile repository was never queried for victim Bob
            mock_get.assert_awaited_once_with(alice_id)


# =============================================================================
# 6. DATABASE RETRIEVAL FAILURE RETURNS SANITIZED ERROR
# =============================================================================

@pytest.mark.anyio
async def test_database_retrieval_failure_sanitized():
    """Database connection drops return clean HTTP 503 without leaking credentials."""
    user_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    mock_auth_resp = create_mock_supabase_user(user_id=user_id)

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = mock_auth_resp

    # Low-level PostgREST/network driver failure containing sensitive password
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_eq.execute.side_effect = RuntimeError(
        "FATAL: password authentication failed for postgres:secret_pass@db:5432"
    )
    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch("app.database.repositories.get_supabase_client", return_value=mock_client),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 503
            data = response.json()
            assert data["success"] is False
            # Verify internal credentials and connection strings are completely sanitized
            assert "secret_pass" not in response.text
            assert "Unable to complete database operation" in data["message"]


# =============================================================================
# 7. PROFILE CREATION FAILURE HANDLED SAFELY
# =============================================================================

@pytest.mark.anyio
async def test_profile_creation_concurrent_conflict_recovery():
    """Concurrent profile creation conflict is caught and recovered via second retrieval."""
    user_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    mock_auth_resp = create_mock_supabase_user(user_id=user_id, email="bob@example.com")

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = mock_auth_resp

    concurrently_created_profile = {
        "id": user_id,
        "email": "bob@example.com",
        "full_name": "Bob Concurrently Created",
        "created_at": "2026-10-31T12:00:00Z",
        "updated_at": "2026-10-31T12:00:00Z",
    }

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ProfileRepository, "get_by_id", new_callable=AsyncMock) as mock_get,
        patch.object(ProfileRepository, "create_profile", new_callable=AsyncMock) as mock_create,
    ):
        # 1st get_by_id returns None, create_profile encounters conflict (raises ClarityXException),
        # 2nd get_by_id succeeds with concurrently committed profile
        mock_get.side_effect = [None, concurrently_created_profile]
        mock_create.side_effect = ClarityXException(
            message="Database operation failed during create_profile.",
            status_code=400,
            detail="duplicate key value violates unique constraint 'profiles_pkey'",
        )

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == user_id
            assert data["full_name"] == "Bob Concurrently Created"


@pytest.mark.anyio
async def test_profile_creation_unrecoverable_failure():
    """If profile creation fails and subsequent retrieval also yields None, returns 404."""
    user_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    mock_auth_resp = create_mock_supabase_user(user_id=user_id)

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = mock_auth_resp

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ProfileRepository, "get_by_id", new_callable=AsyncMock) as mock_get,
        patch.object(ProfileRepository, "create_profile", new_callable=AsyncMock) as mock_create,
    ):
        mock_get.return_value = None
        mock_create.side_effect = ClarityXException(message="Creation failed", status_code=400)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 404
            data = response.json()
            assert data["success"] is False
            assert "User profile not found" in data["message"]


# =============================================================================
# 8. RESPONSE FOLLOWS USERPROFILERESPONSE SCHEMA
# =============================================================================

@pytest.mark.anyio
async def test_response_conforms_to_user_profile_response_schema():
    """Response payload can be successfully parsed into UserProfileResponse schema."""
    user_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    mock_auth_resp = create_mock_supabase_user(user_id=user_id)

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = mock_auth_resp

    profile_dict = {
        "id": user_id,
        "email": "test@clarityx.dev",
        "full_name": "Test Researcher",
        "created_at": "2026-10-31T12:00:00Z",
        "updated_at": "2026-10-31T12:30:00Z",
    }

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_client),
        patch.object(ProfileRepository, "get_by_id", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = profile_dict

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer valid-token"},
            )

            assert response.status_code == 200
            data = response.json()

            # Strictly validate schema via Pydantic model
            profile_model = UserProfileResponse.model_validate(data)
            assert profile_model.id == UUID(user_id)
            assert profile_model.email == "test@clarityx.dev"
            assert profile_model.full_name == "Test Researcher"
            assert profile_model.created_at is not None
            assert profile_model.updated_at is not None


# =============================================================================
# 9. OPENAPI DOCUMENTATION CONFORMANCE
# =============================================================================

@pytest.mark.anyio
async def test_openapi_schema_contains_auth_me():
    """OpenAPI schema must declare /api/auth/me endpoint with tags and response schema."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()
        assert "/api/auth/me" in schema["paths"]
        get_op = schema["paths"]["/api/auth/me"]["get"]
        assert "Authentication" in get_op["tags"]
        assert "200" in get_op["responses"]
