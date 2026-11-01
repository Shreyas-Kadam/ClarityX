from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from postgrest.exceptions import APIError

from app.core.config import Settings
from app.core.exceptions import (
    ClarityXException,
    DatabaseConfigurationError,
    DatabaseConnectionError,
)
from app.database.repositories import BaseRepository, ProfileRepository, ResearchRepository
from app.database.supabase import (
    get_supabase_client,
    reset_supabase_client,
    verify_database_connection,
)


@pytest.fixture(autouse=True)
def clean_client_cache():
    """Ensures Supabase client singleton cache is reset between tests."""
    reset_supabase_client()
    yield
    reset_supabase_client()


def test_missing_url_raises_configuration_error():
    """Tests that missing SUPABASE_URL raises a clean DatabaseConfigurationError."""
    fake_settings = Settings()
    fake_settings.SUPABASE_URL = ""
    fake_settings.SUPABASE_SERVICE_ROLE_KEY = "test-service-key"

    with patch("app.database.supabase.get_settings", return_value=fake_settings):
        with pytest.raises(DatabaseConfigurationError) as exc_info:
            get_supabase_client()

        assert "SUPABASE_URL is not configured" in str(exc_info.value)
        # Ensure credentials aren't reflected in the error
        assert "test-service-key" not in str(exc_info.value)


def test_missing_service_key_raises_configuration_error():
    """Tests that missing SUPABASE_SERVICE_ROLE_KEY raises DatabaseConfigurationError."""
    fake_settings = Settings()
    fake_settings.SUPABASE_URL = "https://example.supabase.co"
    fake_settings.SUPABASE_SERVICE_ROLE_KEY = ""

    with patch("app.database.supabase.get_settings", return_value=fake_settings):
        with pytest.raises(DatabaseConfigurationError) as exc_info:
            get_supabase_client()

        assert "SUPABASE_SERVICE_ROLE_KEY is not configured" in str(exc_info.value)


def test_verify_database_connection_when_unconfigured():
    """Tests that verify_database_connection returns a graceful unconfigured status."""
    fake_settings = Settings()
    fake_settings.SUPABASE_URL = ""
    fake_settings.SUPABASE_SERVICE_ROLE_KEY = ""

    with patch("app.database.supabase.get_settings", return_value=fake_settings):
        result = verify_database_connection()
        assert result["connected"] is False
        assert result["status"] == "unconfigured"
        assert "not fully configured" in result["message"]


def test_verify_database_connection_error_sanitized():
    """Tests that unexpected errors during connection check do not leak secrets."""
    mock_client = MagicMock()
    mock_client.auth.admin.list_users.side_effect = RuntimeError("Network timeout simulation")

    with patch("app.database.supabase.get_supabase_client", return_value=mock_client):
        result = verify_database_connection()
        assert result["connected"] is False
        assert result["status"] == "error"
        assert "RuntimeError" in result["message"]


def test_get_supabase_client_singleton():
    """Tests that get_supabase_client returns the same cached instance on repeated calls."""
    client1 = get_supabase_client()
    client2 = get_supabase_client()
    assert client1 is client2


def test_verify_database_connection_live():
    """Live connectivity test verifying Supabase REST/Auth API is reached without tables."""
    result = verify_database_connection()
    assert result["connected"] is True
    assert result["status"] == "connected"
    assert "https://" in result["endpoint"]


# =============================================================================
# REPOSITORY & ERROR HANDLING TESTS
# =============================================================================

def test_base_repository_handle_db_error_generic():
    """Generic exceptions should be translated to DatabaseConnectionError."""
    repo = BaseRepository()
    with pytest.raises(DatabaseConnectionError) as exc_info:
        repo.handle_db_error("test_op", RuntimeError("Database socket dropped"))

    assert "Unable to complete database operation (test_op)" in str(exc_info.value)


def test_base_repository_handle_db_error_postgrest():
    """PostgREST APIErrors should be translated to user-safe ClarityXException."""
    repo = BaseRepository()
    postgrest_err = APIError({"message": "duplicate key value", "code": "23505", "details": None, "hint": None})
    with pytest.raises(ClarityXException) as exc_info:
        repo.handle_db_error("insert_record", postgrest_err)

    assert exc_info.value.status_code == 400
    assert "insert_record" in exc_info.value.message


@pytest.mark.anyio
async def test_profile_repository_get_by_id():
    """ProfileRepository should query table and return first match."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"id": "user-123", "full_name": "Test User"}]

    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_eq.execute.return_value = mock_response

    repo = ProfileRepository()
    with patch("app.database.repositories.get_supabase_client", return_value=mock_client):
        profile = await repo.get_by_id("user-123")
        assert profile is not None
        assert profile["id"] == "user-123"
        assert profile["full_name"] == "Test User"


@pytest.mark.anyio
async def test_research_repository_list_user_sessions():
    """ResearchRepository should query user sessions with pagination."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_order = MagicMock()
    mock_range = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"id": "session-1", "research_goal": "Goal 1"}]

    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_eq.order.return_value = mock_order
    mock_order.range.return_value = mock_range
    mock_range.execute.return_value = mock_response

    repo = ResearchRepository()
    with patch("app.database.repositories.get_supabase_client", return_value=mock_client):
        sessions = await repo.list_user_sessions("user-123", limit=5, offset=0)
        assert len(sessions) == 1
        assert sessions[0]["id"] == "session-1"


# =============================================================================
# SCHEMA MIGRATION SPECIFICATION TESTS
# =============================================================================

def test_migration_sql_file_exists_and_valid():
    """Verifies that 001_initial_schema.sql contains the complete schema specification."""
    migration_path = Path(__file__).resolve().parent.parent / "app" / "database" / "migrations" / "001_initial_schema.sql"
    assert migration_path.exists(), f"Migration file not found at {migration_path}"

    content = migration_path.read_text(encoding="utf-8")

    # Verify all 6 core tables are declared
    required_tables = [
        "public.profiles",
        "public.research_sessions",
        "public.sources",
        "public.findings",
        "public.evidence_references",
        "public.verification_items",
    ]
    for table in required_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in content, f"Table {table} missing from migration"

    # Verify RLS enabled on all 6 tables
    for table in required_tables:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in content, f"RLS not enabled on {table}"

    # Verify Triggers
    assert "trg_check_evidence_reference_session" in content
    assert "trg_check_verification_item_session" in content
    assert "on_auth_user_created" in content
    assert "handle_new_user" in content

    # Verify strict categories
    assert "CHECK (category IN ('missing', 'outdated', 'conflicting', 'unverified'))" in content


# =============================================================================
# USER CLIENT INITIALIZATION TESTS
# =============================================================================

def test_authenticated_user_client_initialization_with_jwt():
    """Verifies that user-scoped client is initialized with anon key and user JWT."""
    from tests.verify_analysis_integration import create_authenticated_user_client

    client = create_authenticated_user_client(
        "https://example.supabase.co",
        "anon-key-12345",
        "test-user-jwt-token",
    )
    assert client is not None
    # Verify postgrest has anon apikey
    assert client.postgrest.headers.get("apikey") == "anon-key-12345"
    # Verify postgrest has user authorization bearer header
    assert client.postgrest.headers.get("authorization") == "Bearer test-user-jwt-token"


