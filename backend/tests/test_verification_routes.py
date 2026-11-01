"""Integration and unit tests for ClarityX Verification API Route (Phase 7.2).

Endpoint tested:
    PATCH /api/verification/{item_id}

Tests covered:
 1. Successful update to status='completed' returns 200 with VerificationItemEnvelope.
 2. Successful update to status='pending' returns 200 with completed_at=None.
 3. Missing authentication header returns 401.
 4. Invalid JWT token returns 401.
 5. Invalid item UUID format returns 400.
 6. Invalid status value (not 'pending' or 'completed') returns 422.
 7. Extra unexpected payload fields (e.g., user_id injection) returns 422.
 8. Nonexistent verification item returns 404.
 9. Cross-user verification item access returns 404 without leaking existence.
10. Database connection failure returns 503 error.
11. Successfully preserves finding_id (both null and non-null) and research_id.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import ClarityXException, DatabaseConnectionError
from app.database.repositories import VerificationRepository
from app.main import app
from app.routes.verification import get_verification_repository


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


def make_sample_verification_item(
    item_id: str,
    research_id: str,
    finding_id: str = None,
    task: str = "Verify registration details directly with the state licensing board.",
    status: str = "completed",
    completed_at: str = None,
):
    """Creates a sample verification item dictionary representing a database row."""
    now_utc = datetime.now(timezone.utc).isoformat()
    return {
        "id": item_id,
        "research_id": research_id,
        "finding_id": finding_id,
        "task": task,
        "status": status,
        "completed_at": completed_at or (now_utc if status == "completed" else None),
        "created_at": now_utc,
        "updated_at": now_utc,
    }


# =============================================================================
# 1. SUCCESSFUL VERIFICATION STATUS UPDATE TESTS
# =============================================================================

@pytest.mark.anyio
async def test_update_verification_item_completed_success():
    """1. Successful update to status='completed' returns 200 with VerificationItemEnvelope."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    item_id = str(uuid4())
    research_id = str(uuid4())
    finding_id = str(uuid4())
    now_utc = datetime.now(timezone.utc).isoformat()

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    updated_record = make_sample_verification_item(
        item_id=item_id,
        research_id=research_id,
        finding_id=finding_id,
        task="Verify registration details directly with the state licensing board.",
        status="completed",
        completed_at=now_utc,
    )

    mock_verification_repo = MagicMock(spec=VerificationRepository)
    mock_verification_repo.update_item_status = AsyncMock(return_value=updated_record)

    app.dependency_overrides[get_verification_repository] = lambda: mock_verification_repo

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.patch(
                f"/api/verification/{item_id}",
                headers={"Authorization": "Bearer valid-token-alice"},
                json={"status": "completed"},
            )

    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["message"] == "Verification item updated successfully"
    assert body["data"]["id"] == item_id
    assert body["data"]["research_id"] == research_id
    assert body["data"]["finding_id"] == finding_id
    assert body["data"]["task"] == "Verify registration details directly with the state licensing board."
    assert body["data"]["status"] == "completed"
    assert body["data"]["completed_at"] is not None
    assert body["data"]["created_at"] is not None
    assert body["data"]["updated_at"] is not None

    mock_verification_repo.update_item_status.assert_awaited_once_with(
        item_id=item_id,
        user_id=alice_id,
        status="completed",
    )


@pytest.mark.anyio
async def test_update_verification_item_pending_success():
    """2. Successful update to status='pending' returns 200 with completed_at=None."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    item_id = str(uuid4())
    research_id = str(uuid4())

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    updated_record = make_sample_verification_item(
        item_id=item_id,
        research_id=research_id,
        finding_id=None,
        task="What is the official accreditation board for this institution?",
        status="pending",
        completed_at=None,
    )

    mock_verification_repo = MagicMock(spec=VerificationRepository)
    mock_verification_repo.update_item_status = AsyncMock(return_value=updated_record)

    app.dependency_overrides[get_verification_repository] = lambda: mock_verification_repo

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.patch(
                f"/api/verification/{item_id}",
                headers={"Authorization": "Bearer valid-token-alice"},
                json={"status": "pending"},
            )

    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["id"] == item_id
    assert body["data"]["research_id"] == research_id
    assert body["data"]["finding_id"] is None
    assert body["data"]["status"] == "pending"
    assert body["data"]["completed_at"] is None

    mock_verification_repo.update_item_status.assert_awaited_once_with(
        item_id=item_id,
        user_id=alice_id,
        status="pending",
    )


# =============================================================================
# 2. AUTHENTICATION & AUTHORIZATION TESTS
# =============================================================================

@pytest.mark.anyio
async def test_update_verification_missing_authentication():
    """3. Missing authentication header returns 401."""
    item_id = str(uuid4())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.patch(
            f"/api/verification/{item_id}",
            json={"status": "completed"},
        )
    assert res.status_code == 401


@pytest.mark.anyio
async def test_update_verification_invalid_jwt():
    """4. Invalid JWT token returns 401."""
    item_id = str(uuid4())
    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.side_effect = Exception("Invalid JWT token")

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.patch(
                f"/api/verification/{item_id}",
                headers={"Authorization": "Bearer invalid-token"},
                json={"status": "completed"},
            )
    assert res.status_code == 401


# =============================================================================
# 3. INPUT VALIDATION TESTS
# =============================================================================

@pytest.mark.anyio
async def test_update_verification_invalid_uuid():
    """5. Invalid item UUID format returns 400."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_verification_repo = MagicMock(spec=VerificationRepository)
    app.dependency_overrides[get_verification_repository] = lambda: mock_verification_repo

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.patch(
                "/api/verification/not-a-valid-uuid",
                headers={"Authorization": "Bearer valid-token"},
                json={"status": "completed"},
            )

    assert res.status_code == 400
    body = res.json()
    assert "Invalid verification item ID" in body.get("message", "")
    mock_verification_repo.update_item_status.assert_not_called()


@pytest.mark.anyio
async def test_update_verification_invalid_status():
    """6. Invalid status value (not 'pending' or 'completed') returns 422."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    item_id = str(uuid4())
    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_verification_repo = MagicMock(spec=VerificationRepository)
    app.dependency_overrides[get_verification_repository] = lambda: mock_verification_repo

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.patch(
                f"/api/verification/{item_id}",
                headers={"Authorization": "Bearer valid-token"},
                json={"status": "in_progress"},
            )

    assert res.status_code == 422
    mock_verification_repo.update_item_status.assert_not_called()


@pytest.mark.anyio
async def test_update_verification_forbids_extra_fields():
    """7. Extra unexpected payload fields (e.g. user_id injection) returns 422."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    item_id = str(uuid4())
    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_verification_repo = MagicMock(spec=VerificationRepository)
    app.dependency_overrides[get_verification_repository] = lambda: mock_verification_repo

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.patch(
                f"/api/verification/{item_id}",
                headers={"Authorization": "Bearer valid-token"},
                json={"status": "completed", "user_id": "attacker-id"},
            )

    assert res.status_code == 422
    mock_verification_repo.update_item_status.assert_not_called()


# =============================================================================
# 4. OWNERSHIP & NOT FOUND TESTS
# =============================================================================

@pytest.mark.anyio
async def test_update_verification_nonexistent_item():
    """8. Nonexistent verification item returns 404."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    item_id = str(uuid4())

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_verification_repo = MagicMock(spec=VerificationRepository)
    mock_verification_repo.update_item_status = AsyncMock(return_value=None)

    app.dependency_overrides[get_verification_repository] = lambda: mock_verification_repo

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.patch(
                f"/api/verification/{item_id}",
                headers={"Authorization": "Bearer valid-token"},
                json={"status": "completed"},
            )

    assert res.status_code == 404
    body = res.json()
    assert "Verification item not found" in body.get("message", "")


@pytest.mark.anyio
async def test_update_verification_cross_user_forbidden():
    """9. Cross-user verification item access returns 404 without leaking existence."""
    bob_id = "99999999-9999-9999-9999-999999999999"
    item_id = str(uuid4())

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=bob_id, email="bob@clarityx.dev")

    mock_verification_repo = MagicMock(spec=VerificationRepository)
    # Repository returns None when session ownership check fails for Bob
    mock_verification_repo.update_item_status = AsyncMock(return_value=None)

    app.dependency_overrides[get_verification_repository] = lambda: mock_verification_repo

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.patch(
                f"/api/verification/{item_id}",
                headers={"Authorization": "Bearer valid-token-bob"},
                json={"status": "completed"},
            )

    assert res.status_code == 404
    body = res.json()
    assert "Verification item not found" in body.get("message", "")
    # Verifies bob_id was passed to repository ownership check
    mock_verification_repo.update_item_status.assert_awaited_once_with(
        item_id=item_id,
        user_id=bob_id,
        status="completed",
    )


# =============================================================================
# 5. DATABASE ERROR & RESILIENCE TESTS
# =============================================================================

@pytest.mark.anyio
async def test_update_verification_database_error():
    """10. Database connection failure returns 503 error."""
    alice_id = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
    item_id = str(uuid4())

    mock_auth_client = MagicMock()
    mock_auth_client.auth.get_user.return_value = create_mock_auth_user(user_id=alice_id)

    mock_verification_repo = MagicMock(spec=VerificationRepository)
    mock_verification_repo.update_item_status = AsyncMock(
        side_effect=DatabaseConnectionError("Unable to complete database operation (update_item_status).")
    )

    app.dependency_overrides[get_verification_repository] = lambda: mock_verification_repo

    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res = await ac.patch(
                f"/api/verification/{item_id}",
                headers={"Authorization": "Bearer valid-token"},
                json={"status": "completed"},
            )

    assert res.status_code == 503
    body = res.json()
    assert "database operation" in body.get("message", "").lower()

