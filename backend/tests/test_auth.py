"""Authentication unit and integration tests for ClarityX."""

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import AuthenticationError, register_exception_handlers
from app.dependencies.auth import get_current_user, get_token_header
from app.schemas.auth import AuthenticatedUser, UserProfileResponse

# Create an isolated FastAPI test application to verify dependency injection
auth_test_app = FastAPI()
register_exception_handlers(auth_test_app)


@auth_test_app.get("/test-protected")
async def protected_endpoint(user: AuthenticatedUser = Depends(get_current_user)):
    """Test endpoint protected by get_current_user dependency."""
    return {
        "status": "success",
        "user_id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "metadata": user.metadata,
    }


# =============================================================================
# 1. MISSING AUTHORIZATION HEADER TESTS
# =============================================================================

def test_missing_authorization_header_unit():
    """get_token_header should raise AuthenticationError (401) when header is None or empty."""
    with pytest.raises(AuthenticationError) as exc_info:
        get_token_header(None)

    assert exc_info.value.status_code == 401
    assert "Missing Authorization header" in exc_info.value.message
    assert "Bearer" in exc_info.value.detail


@pytest.mark.anyio
async def test_missing_authorization_header_http():
    """Requests without Authorization header must receive a 401 JSON envelope."""
    transport = ASGITransport(app=auth_test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test-protected")

        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert "Missing Authorization header" in data["message"]


# =============================================================================
# 2. MALFORMED BEARER HEADER TESTS
# =============================================================================

@pytest.mark.parametrize(
    "malformed_header",
    [
        "Basic dXNlcjpwYXNz",
        "Bearer",
        "Bearer   ",
        "Token eyJhbGciOi...",
        "Bearer token1 token2",
        "bearer_without_space_token",
        "CustomAuth xyz123",
    ],
)
def test_malformed_bearer_header_unit(malformed_header: str):
    """get_token_header should reject any non-'Bearer <token>' format with 401."""
    with pytest.raises(AuthenticationError) as exc_info:
        get_token_header(malformed_header)

    assert exc_info.value.status_code == 401
    assert "Malformed Authorization header" in exc_info.value.message


@pytest.mark.anyio
async def test_malformed_bearer_header_http():
    """Requests with malformed Bearer headers must receive a 401 response."""
    transport = ASGITransport(app=auth_test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/test-protected",
            headers={"Authorization": "Token not_a_bearer_scheme"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert "Malformed Authorization header" in data["message"]


# =============================================================================
# 3. INVALID TOKEN TESTS
# =============================================================================

def test_invalid_token_returns_401_unit():
    """get_current_user should raise AuthenticationError (401) on invalid token rejection."""
    mock_client = MagicMock()
    mock_client.auth.get_user.side_effect = Exception("Invalid JWT token signature")

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        with pytest.raises(AuthenticationError) as exc_info:
            get_current_user("invalid-token-xyz")

        assert exc_info.value.status_code == 401
        assert "Invalid or expired authentication token" in exc_info.value.message


@pytest.mark.anyio
async def test_invalid_token_returns_401_http():
    """Requests with invalid token must receive a 401 response."""
    mock_client = MagicMock()
    mock_client.auth.get_user.side_effect = Exception("Invalid JWT token signature")

    transport = ASGITransport(app=auth_test_app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/test-protected",
                headers={"Authorization": "Bearer invalid-token-xyz"},
            )

            assert response.status_code == 401
            data = response.json()
            assert data["success"] is False
            assert "Invalid or expired authentication token" in data["message"]


# =============================================================================
# 4. EXPIRED OR REJECTED TOKEN TESTS
# =============================================================================

def test_expired_token_returns_401_unit():
    """get_current_user should raise AuthenticationError (401) on token expiration."""
    mock_client = MagicMock()
    mock_client.auth.get_user.side_effect = Exception("JWT expired at timestamp 1700000000")

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        with pytest.raises(AuthenticationError) as exc_info:
            get_current_user("expired-token-xyz")

        assert exc_info.value.status_code == 401
        assert "Invalid or expired authentication token" in exc_info.value.message


@pytest.mark.anyio
async def test_expired_token_returns_401_http():
    """Requests with expired token must receive a 401 response."""
    mock_client = MagicMock()
    mock_client.auth.get_user.side_effect = Exception("JWT expired at timestamp 1700000000")

    transport = ASGITransport(app=auth_test_app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/test-protected",
                headers={"Authorization": "Bearer expired-token-xyz"},
            )

            assert response.status_code == 401
            data = response.json()
            assert data["success"] is False
            assert "Invalid or expired authentication token" in data["message"]


# =============================================================================
# 5. VALID MOCKED SUPABASE AUTHENTICATION TESTS
# =============================================================================

def test_valid_supabase_authentication_unit():
    """get_current_user should construct a valid AuthenticatedUser from Supabase response."""
    mock_user = MagicMock()
    mock_user.id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    mock_user.email = "researcher@clarityx.dev"
    mock_user.user_metadata = {
        "full_name": "Dr. Clara Oswald",
        "organization": "TruthLab",
    }
    mock_response = MagicMock()
    mock_response.user = mock_user

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = mock_response

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        user = get_current_user("valid-supabase-jwt-token")

        assert isinstance(user, AuthenticatedUser)
        assert user.id == UUID("e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80")
        assert user.email == "researcher@clarityx.dev"
        assert user.full_name == "Dr. Clara Oswald"
        assert user.metadata["organization"] == "TruthLab"


@pytest.mark.anyio
async def test_valid_supabase_authentication_http():
    """Protected endpoint should accept valid Bearer token and return 200 with user data."""
    mock_user = MagicMock()
    mock_user.id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    mock_user.email = "alice@example.com"
    mock_user.user_metadata = {"full_name": "Alice Cooper"}
    mock_response = MagicMock()
    mock_response.user = mock_user

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = mock_response

    transport = ASGITransport(app=auth_test_app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/test-protected",
                headers={"Authorization": "Bearer valid-access-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["user_id"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            assert data["email"] == "alice@example.com"
            assert data["full_name"] == "Alice Cooper"


# =============================================================================
# 6. CREDENTIAL / SECRET LEAK PREVENTION TESTS
# =============================================================================

def test_supabase_auth_failure_does_not_expose_secrets_unit():
    """Verification exceptions containing sensitive strings must never leak to user."""
    sensitive_token = "secret-jwt-token-with-private-claims"
    sensitive_service_key = "service_role_secret_key_abcdef123456"

    mock_client = MagicMock()
    mock_client.auth.get_user.side_effect = RuntimeError(
        f"Internal Gotrue failure connecting to {sensitive_service_key} using {sensitive_token}"
    )

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        with pytest.raises(AuthenticationError) as exc_info:
            get_current_user(sensitive_token)

        combined_message = f"{exc_info.value.message} {exc_info.value.detail}"
        assert sensitive_token not in combined_message
        assert sensitive_service_key not in combined_message


@pytest.mark.anyio
async def test_supabase_auth_failure_does_not_expose_secrets_http():
    """HTTP error responses on auth failure must not contain secrets or raw tokens."""
    sensitive_token = "ultra-secret-user-bearer-token"
    mock_client = MagicMock()
    mock_client.auth.get_user.side_effect = RuntimeError(
        "Failed request to https://project.supabase.co/auth/v1/user with Authorization: secret-key"
    )

    transport = ASGITransport(app=auth_test_app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/test-protected",
                headers={"Authorization": f"Bearer {sensitive_token}"},
            )

            assert response.status_code == 401
            body_text = response.text
            assert sensitive_token not in body_text
            assert "secret-key" not in body_text


# =============================================================================
# 7. SCHEMA & EDGE CASE VALIDATION
# =============================================================================

def test_empty_user_in_supabase_response():
    """When Supabase response contains no user, raise 401."""
    mock_response = MagicMock()
    mock_response.user = None

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = mock_response

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        with pytest.raises(AuthenticationError) as exc_info:
            get_current_user("valid-looking-token")

        assert exc_info.value.status_code == 401
        assert "Invalid or expired authentication token" in exc_info.value.message


def test_invalid_uuid_in_supabase_user():
    """When Supabase user has a non-UUID ID, raise 401."""
    mock_user = MagicMock()
    mock_user.id = "not-a-valid-uuid"
    mock_user.email = "test@example.com"
    mock_user.user_metadata = {}
    mock_response = MagicMock()
    mock_response.user = mock_user

    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = mock_response

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        with pytest.raises(AuthenticationError) as exc_info:
            get_current_user("token")

        assert exc_info.value.status_code == 401
        assert "Invalid user identifier" in exc_info.value.message


def test_user_profile_response_schema():
    """UserProfileResponse schema can be created with valid fields."""
    profile = UserProfileResponse(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        email="test@example.com",
        full_name="Test User",
    )
    assert profile.email == "test@example.com"
    assert profile.full_name == "Test User"
    assert profile.created_at is None
