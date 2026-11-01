"""Unit & Integration Tests for SourceRepository (Checkpoint 4.4.1).

Tests:
1. Session ownership verification (authorized vs unauthorized).
2. Sequential source-code allocation (S1, S2, S3, gap handling).
3. Source creation with all source types (website, pasted_text, document).
4. Unique constraint collision (code 23505) and successful optimistic retry.
5. Retry exhaustion on persistent collisions (HTTP 409).
6. Unrelated database errors are not retried.
7. Listing sources with pagination and count.
8. Content preview truncation (first 250 characters + '...' only if longer, no extracted_content in list items).
9. Full extracted_content retrieval in get_source_by_id.
10. Cross-user access rejection (create, list, get, delete).
11. Cross-session source access rejection.
12. Source deletion with session ownership checks.
13. Schema validation for SourceResponse, SourcePreviewResponse, and Envelopes.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import ClarityXException, DatabaseConnectionError
from app.database.repositories import SourceRepository
from app.schemas.source import (
    SourceEnvelope,
    SourceListEnvelope,
    SourceListResponse,
    SourcePreviewResponse,
    SourceResponse,
    make_content_preview,
)


@pytest.fixture
def mock_supabase():
    """Provides a fresh mocked Supabase client for repository tests."""
    with patch("app.database.repositories.get_supabase_client") as mock_get:
        client = MagicMock()
        mock_get.return_value = client
        yield client


# =============================================================================
# 1. SESSION OWNERSHIP VERIFICATION TESTS
# =============================================================================


@pytest.mark.anyio
async def test_verify_session_ownership_success(mock_supabase):
    """Returns True when the research session belongs to the user."""
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_eq1 = MagicMock()
    mock_eq2 = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"id": "session-123"}]

    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq1
    mock_eq1.eq.return_value = mock_eq2
    mock_eq2.execute.return_value = mock_response

    repo = SourceRepository()
    result = await repo.verify_session_ownership("session-123", "user-456")

    assert result is True
    mock_supabase.table.assert_called_with("research_sessions")
    mock_select.eq.assert_called_with("id", "session-123")
    mock_eq1.eq.assert_called_with("user_id", "user-456")


@pytest.mark.anyio
async def test_verify_session_ownership_unauthorized(mock_supabase):
    """Returns False when the session does not exist or belongs to another user."""
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_eq1 = MagicMock()
    mock_eq2 = MagicMock()
    mock_response = MagicMock()
    mock_response.data = []

    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq1
    mock_eq1.eq.return_value = mock_eq2
    mock_eq2.execute.return_value = mock_response

    repo = SourceRepository()
    result = await repo.verify_session_ownership("session-123", "user-other")

    assert result is False


# =============================================================================
# 2. SEQUENTIAL SOURCE CODE ALLOCATION TESTS
# =============================================================================


@pytest.mark.anyio
async def test_get_next_source_code_first_source(mock_supabase):
    """First source in a session receives code 'S1'."""
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_response = MagicMock()
    mock_response.data = []

    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_eq.execute.return_value = mock_response

    repo = SourceRepository()
    code = await repo.get_next_source_code("session-123")

    assert code == "S1"


@pytest.mark.anyio
async def test_get_next_source_code_sequential(mock_supabase):
    """Calculates next sequential code (S3 when S1 and S2 exist)."""
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"source_code": "S1"}, {"source_code": "S2"}]

    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_eq.execute.return_value = mock_response

    repo = SourceRepository()
    code = await repo.get_next_source_code("session-123")

    assert code == "S3"


@pytest.mark.anyio
async def test_get_next_source_code_gap_and_non_sequential(mock_supabase):
    """Correctly parses highest numerical suffix when non-consecutive codes exist."""
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"source_code": "S1"}, {"source_code": "S14"}]

    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_eq.execute.return_value = mock_response

    repo = SourceRepository()
    code = await repo.get_next_source_code("session-123")

    assert code == "S15"


# =============================================================================
# 3. SOURCE CREATION & COLLISION RETRY TESTS
# =============================================================================


@pytest.mark.anyio
async def test_create_source_success(mock_supabase):
    """Standard source creation succeeds and returns persisted dictionary record."""
    repo = SourceRepository()

    # Mock ownership check
    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "sess-1"}]

    # Mock next source code query
    mock_sources_query = MagicMock()
    mock_sources_query.select.return_value.eq.return_value.execute.return_value.data = []

    # Mock insert
    mock_sources_insert = MagicMock()
    created_record = {
        "id": str(uuid4()),
        "research_id": "sess-1",
        "source_code": "S1",
        "title": "Scholarship Overview",
        "url": "https://example.com/scholarship",
        "source_type": "website",
        "extracted_content": "Extracted text content",
        "published_at": None,
        "accessed_at": datetime.now(timezone.utc).isoformat(),
        "extraction_status": "success",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    mock_sources_insert.insert.return_value.execute.return_value.data = [created_record]

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        return mock_sources_insert

    mock_supabase.table.side_effect = table_router

    result = await repo.create_source(
        session_id="sess-1",
        user_id="user-1",
        source_type="website",
        extracted_content="Extracted text content",
        title="Scholarship Overview",
        url="https://example.com/scholarship",
    )

    assert result is not None
    assert result["source_code"] == "S1"
    assert result["title"] == "Scholarship Overview"
    assert result["source_type"] == "website"


@pytest.mark.anyio
async def test_create_source_unauthorized_session_rejected(mock_supabase):
    """Attempting to insert a source into an unauthorized session raises 404."""
    repo = SourceRepository()

    # Mock ownership check returning empty (unauthorized / not found)
    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value = mock_sessions

    with pytest.raises(ClarityXException) as exc_info:
        await repo.create_source(
            session_id="sess-other",
            user_id="user-attacker",
            source_type="pasted_text",
            extracted_content="Sneaky payload",
        )

    assert exc_info.value.status_code == 404
    assert "not found or unauthorized" in exc_info.value.message.lower()


@pytest.mark.anyio
async def test_create_source_invalid_constraints_rejected(mock_supabase):
    """Invalid source_type or extraction_status raises 400 validation error."""
    repo = SourceRepository()

    # Mock ownership check passing
    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "sess-1"}]
    mock_supabase.table.return_value = mock_sessions

    # Invalid source_type
    with pytest.raises(ClarityXException) as exc1:
        await repo.create_source(
            session_id="sess-1",
            user_id="user-1",
            source_type="invalid_type",
            extracted_content="Sample text",
        )
    assert exc1.value.status_code == 400

    # Invalid extraction_status
    with pytest.raises(ClarityXException) as exc2:
        await repo.create_source(
            session_id="sess-1",
            user_id="user-1",
            source_type="website",
            extracted_content="Sample text",
            extraction_status="corrupted_status",
        )
    assert exc2.value.status_code == 400


@pytest.mark.anyio
async def test_create_source_collision_and_successful_retry(mock_supabase):
    """A unique constraint collision (23505) triggers automatic retry and succeeds."""
    repo = SourceRepository()

    # Mock ownership check
    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "sess-1"}]

    # First get_next_source_code returns S1, second call returns S2
    code_calls = 0

    def mock_table_handler(table_name):
        nonlocal code_calls
        if table_name == "research_sessions":
            return mock_sessions

        # sources table
        t = MagicMock()
        if code_calls == 0:
            # Query for existing codes returns [] -> candidate S1
            t.select.return_value.eq.return_value.execute.return_value.data = []
            # First insert triggers 23505 collision
            err = APIError({"message": "duplicate key value violates unique constraint uq_sources_research_code", "code": "23505"})
            t.insert.return_value.execute.side_effect = err
            code_calls += 1
            return t
        else:
            # Query for existing codes now returns S1 -> candidate S2
            t.select.return_value.eq.return_value.execute.return_value.data = [{"source_code": "S1"}]
            # Second insert succeeds!
            t.insert.return_value.execute.side_effect = None
            t.insert.return_value.execute.return_value.data = [
                {"id": str(uuid4()), "source_code": "S2", "title": "Second Attempt"}
            ]
            return t

    mock_supabase.table.side_effect = mock_table_handler

    result = await repo.create_source(
        session_id="sess-1",
        user_id="user-1",
        source_type="pasted_text",
        extracted_content="Pasted text payload",
    )

    assert result is not None
    assert result["source_code"] == "S2"


@pytest.mark.anyio
async def test_create_source_retry_exhaustion(mock_supabase):
    """Exhausting 3 consecutive unique collisions raises HTTP 409 ClarityXException."""
    repo = SourceRepository()

    # Mock ownership check
    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "sess-1"}]

    mock_sources = MagicMock()
    mock_sources.select.return_value.eq.return_value.execute.return_value.data = []
    # Always raise 23505 unique conflict
    err = APIError({"message": "duplicate key value violates unique constraint uq_sources_research_code", "code": "23505"})
    mock_sources.insert.return_value.execute.side_effect = err

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        return mock_sources

    mock_supabase.table.side_effect = table_router

    with pytest.raises(ClarityXException) as exc_info:
        await repo.create_source(
            session_id="sess-1",
            user_id="user-1",
            source_type="pasted_text",
            extracted_content="Text content",
        )

    assert exc_info.value.status_code == 409
    assert "failed to allocate unique source code" in exc_info.value.message.lower()


@pytest.mark.anyio
async def test_create_source_unrelated_database_error_not_retried(mock_supabase):
    """Unrelated database errors (connection failure / syntax) are not retried."""
    repo = SourceRepository()

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "sess-1"}]

    insert_attempts = 0
    mock_sources = MagicMock()
    mock_sources.select.return_value.eq.return_value.execute.return_value.data = []

    def failing_insert():
        nonlocal insert_attempts
        insert_attempts += 1
        raise APIError({"message": "permission denied for table sources", "code": "42501"})

    mock_sources.insert.return_value.execute.side_effect = failing_insert

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        return mock_sources

    mock_supabase.table.side_effect = table_router

    with pytest.raises(ClarityXException) as exc_info:
        await repo.create_source(
            session_id="sess-1",
            user_id="user-1",
            source_type="pasted_text",
            extracted_content="Text content",
        )

    assert exc_info.value.status_code == 400
    assert insert_attempts == 1  # Exactly 1 attempt, zero retries


# =============================================================================
# 4. LISTING, PREVIEW & PAGINATION TESTS
# =============================================================================


def test_make_content_preview_truncation():
    """Preview caps at exactly 250 characters and appends '...' only when longer."""
    # Under 250 characters -> no ellipsis
    short = "This is a brief summary of facts."
    assert make_content_preview(short, max_chars=250) == short

    # Exactly 250 characters -> no ellipsis
    exact = "A" * 250
    assert make_content_preview(exact, max_chars=250) == exact

    # 251 characters -> exactly 250 + '...'
    long_text = ("B" * 250) + "C"
    preview = make_content_preview(long_text, max_chars=250)
    assert len(preview) == 253  # 250 chars + "..."
    assert preview == ("B" * 250) + "..."


@pytest.mark.anyio
async def test_list_sources_strips_full_content_and_generates_preview(mock_supabase):
    """Listing sources strips full extracted_content and generates content_preview."""
    repo = SourceRepository()

    # Mock ownership check
    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "sess-1"}]

    full_text = "Detailed research analysis content. " * 20  # ~720 chars
    mock_sources = MagicMock()
    mock_query = MagicMock()
    mock_sources.select.return_value.eq.return_value.order.return_value.range.return_value = mock_query

    mock_response = MagicMock()
    mock_response.data = [
        {
            "id": str(uuid4()),
            "research_id": "sess-1",
            "source_code": "S1",
            "title": "Lengthy Report",
            "url": "https://example.com",
            "source_type": "website",
            "extracted_content": full_text,
            "published_at": None,
            "accessed_at": datetime.now(timezone.utc).isoformat(),
            "extraction_status": "success",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ]
    mock_response.count = 1
    mock_query.execute.return_value = mock_response

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        return mock_sources

    mock_supabase.table.side_effect = table_router

    result = await repo.list_sources("sess-1", "user-1", limit=10, offset=0)

    assert result["total"] == 1
    assert len(result["sources"]) == 1
    item = result["sources"][0]

    # Crucial assertion: extracted_content must NOT be present in list response
    assert "extracted_content" not in item
    assert "content_preview" in item
    assert item["content_preview"].endswith("...")
    assert len(item["content_preview"]) == 253


@pytest.mark.anyio
async def test_list_sources_unauthorized_session_rejected(mock_supabase):
    """Listing sources of an unauthorized session raises HTTP 404."""
    repo = SourceRepository()

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value = mock_sessions

    with pytest.raises(ClarityXException) as exc_info:
        await repo.list_sources("sess-alien", "user-1")

    assert exc_info.value.status_code == 404


# =============================================================================
# 5. SINGLE SOURCE RETRIEVAL & DELETION TESTS
# =============================================================================


@pytest.mark.anyio
async def test_get_source_by_id_returns_full_content(mock_supabase):
    """get_source_by_id returns full extracted_content when session ownership matches."""
    repo = SourceRepository()

    # Mock ownership check
    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "sess-1"}]

    full_text = "Complete un-truncated source text with all details."
    mock_sources = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [
        {
            "id": "source-100",
            "research_id": "sess-1",
            "source_code": "S1",
            "title": "Complete Source",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": full_text,
            "published_at": None,
            "accessed_at": datetime.now(timezone.utc).isoformat(),
            "extraction_status": "success",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ]
    mock_sources.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_response

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        return mock_sources

    mock_supabase.table.side_effect = table_router

    source = await repo.get_source_by_id("sess-1", "source-100", "user-1")

    assert source is not None
    assert source["id"] == "source-100"
    assert source["extracted_content"] == full_text


@pytest.mark.anyio
async def test_get_source_by_id_cross_session_or_unauthorized_rejected(mock_supabase):
    """Attempting to access a source from another user or wrong session returns None."""
    repo = SourceRepository()

    # 1. Unauthorized session
    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value = mock_sessions

    source = await repo.get_source_by_id("sess-other", "source-1", "user-attacker")
    assert source is None


@pytest.mark.anyio
async def test_delete_source_success(mock_supabase):
    """Deleting a source verifies ownership and deletes by session_id and source_id."""
    repo = SourceRepository()

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "sess-1"}]

    mock_sources = MagicMock()
    # Mock get existing
    mock_sources.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "source-1"}]
    # Mock delete
    mock_sources.delete.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        return mock_sources

    mock_supabase.table.side_effect = table_router

    deleted = await repo.delete_source("sess-1", "source-1", "user-1")
    assert deleted is True


@pytest.mark.anyio
async def test_delete_source_unauthorized_user(mock_supabase):
    """Deleting a source without session ownership returns False."""
    repo = SourceRepository()

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value = mock_sessions

    deleted = await repo.delete_source("sess-other", "source-1", "user-attacker")
    assert deleted is False


# =============================================================================
# 6. PYDANTIC SCHEMA VALIDATION TESTS
# =============================================================================


def test_schema_source_response_and_preview_models():
    """SourceResponse, SourcePreviewResponse, and Envelopes validate structure correctly."""
    now = datetime.now(timezone.utc)
    source_id = uuid4()
    research_id = uuid4()

    # Valid full response
    full_data = {
        "id": source_id,
        "research_id": research_id,
        "source_code": "S1",
        "title": "Overview",
        "url": "https://example.com",
        "source_type": "website",
        "extracted_content": "Extracted text...",
        "published_at": None,
        "accessed_at": now,
        "extraction_status": "success",
        "created_at": now,
    }
    full_model = SourceResponse.model_validate(full_data)
    assert full_model.source_code == "S1"
    assert full_model.extracted_content == "Extracted text..."

    # Envelope validation
    env = SourceEnvelope(data=full_model)
    assert env.success is True
    assert env.data.id == source_id

    # Preview model
    preview_data = {
        "id": source_id,
        "research_id": research_id,
        "source_code": "S2",
        "title": "Document Title",
        "url": None,
        "source_type": "document",
        "content_preview": "A preview of content...",
        "published_at": None,
        "accessed_at": now,
        "extraction_status": "partial",
        "created_at": now,
    }
    preview_model = SourcePreviewResponse.model_validate(preview_data)
    assert preview_model.source_code == "S2"
    assert preview_model.content_preview == "A preview of content..."

    # List envelope
    list_env = SourceListEnvelope(
        data=SourceListResponse(
            sources=[preview_model],
            total=1,
            limit=50,
            offset=0,
        )
    )
    assert list_env.success is True
    assert len(list_env.data.sources) == 1
    assert list_env.data.sources[0].source_type == "document"


# =============================================================================
# 4. CONTENT PREVIEW WHITESPACE PRESERVATION TESTS
# =============================================================================

def test_make_content_preview_preserves_leading_spaces():
    txt = "   leading spaces and text"
    assert make_content_preview(txt) == txt

def test_make_content_preview_preserves_leading_newlines():
    txt = "\n\nFirst line"
    assert make_content_preview(txt) == txt

def test_make_content_preview_preserves_tabs_and_internal_whitespace():
    txt = "\tcol1\tcol2  spaced"
    assert make_content_preview(txt) == txt

def test_make_content_preview_exact_250_chars():
    txt = "X" * 250
    assert make_content_preview(txt) == txt

def test_make_content_preview_251_chars():
    txt = "Y" * 251
    expected = "Y" * 250 + "..."
    assert make_content_preview(txt) == expected

def test_make_content_preview_empty_content():
    assert make_content_preview("") == ""


# =============================================================================
# 6. RAW SOURCE RETRIEVAL TESTS (Phase 6.3.4.1)
# =============================================================================


@pytest.mark.anyio
async def test_get_raw_sources_by_session_success(mock_supabase):
    """Successfully retrieves all raw sources with full extracted_content and required fields."""
    repo = SourceRepository()
    session_id = str(uuid4())
    user_id = str(uuid4())

    # 1. Mock ownership check on research_sessions
    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    raw_data = [
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Source One",
            "url": "https://example.com/one",
            "source_type": "website",
            "extracted_content": "Extracted content for S1. " * 30,
            "published_at": None,
            "accessed_at": datetime.now(timezone.utc).isoformat(),
            "extraction_status": "success",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S2",
            "title": "Source Two",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "Pasted notes for S2. " * 20,
            "published_at": None,
            "accessed_at": datetime.now(timezone.utc).isoformat(),
            "extraction_status": "success",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    ]

    mock_sources = MagicMock()
    mock_order = MagicMock()
    mock_sources.select.return_value.eq.return_value.order.return_value = mock_order
    mock_response = MagicMock()
    mock_response.data = raw_data
    mock_order.execute.return_value = mock_response

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        return mock_sources

    mock_supabase.table.side_effect = table_router

    results = await repo.get_raw_sources_by_session(session_id, user_id)

    assert len(results) == 2
    assert results[0]["source_code"] == "S1"
    assert results[0]["extracted_content"] == raw_data[0]["extracted_content"]
    assert results[1]["source_code"] == "S2"
    assert results[1]["extracted_content"] == raw_data[1]["extracted_content"]
    assert "content_preview" not in results[0]


@pytest.mark.anyio
async def test_get_raw_sources_by_session_ownership_rejection(mock_supabase):
    """Rejects retrieval with HTTP 404 when session ownership verification fails."""
    repo = SourceRepository()
    session_id = str(uuid4())
    user_id = str(uuid4())

    # Mock ownership check failure
    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value = mock_sessions

    with pytest.raises(ClarityXException) as exc_info:
        await repo.get_raw_sources_by_session(session_id, user_id)

    assert exc_info.value.status_code == 404
    assert "not found or unauthorized" in exc_info.value.message.lower()


@pytest.mark.anyio
async def test_get_raw_sources_by_session_empty_list(mock_supabase):
    """Returns an empty list when session has no sources."""
    repo = SourceRepository()
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    mock_sources = MagicMock()
    mock_order = MagicMock()
    mock_sources.select.return_value.eq.return_value.order.return_value = mock_order
    mock_response = MagicMock()
    mock_response.data = []
    mock_order.execute.return_value = mock_response

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        return mock_sources

    mock_supabase.table.side_effect = table_router

    results = await repo.get_raw_sources_by_session(session_id, user_id)

    assert results == []


@pytest.mark.anyio
async def test_get_raw_sources_by_session_deterministic_ordering(mock_supabase):
    """Ensures query orders deterministically by source_code ascending."""
    repo = SourceRepository()
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    mock_sources = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_order = MagicMock()

    mock_sources.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_eq.order.return_value = mock_order
    mock_response = MagicMock()
    mock_response.data = [
        {"source_code": "S1", "extracted_content": "Content 1"},
        {"source_code": "S2", "extracted_content": "Content 2"},
    ]
    mock_order.execute.return_value = mock_response

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        return mock_sources

    mock_supabase.table.side_effect = table_router

    results = await repo.get_raw_sources_by_session(session_id, user_id)

    mock_select.eq.assert_called_once_with("research_id", session_id)
    mock_eq.order.assert_called_once_with("source_code", desc=False)
    assert len(results) == 2
    assert [r["source_code"] for r in results] == ["S1", "S2"]


@pytest.mark.anyio
async def test_get_raw_sources_by_session_extracted_content_available_internally(mock_supabase):
    """Verifies full raw extracted_content is preserved and not truncated to 250 characters."""
    repo = SourceRepository()
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    long_content = "X" * 15000  # Much longer than preview threshold
    mock_sources = MagicMock()
    mock_order = MagicMock()
    mock_sources.select.return_value.eq.return_value.order.return_value = mock_order
    mock_response = MagicMock()
    mock_response.data = [
        {
            "id": str(uuid4()),
            "research_id": session_id,
            "source_code": "S1",
            "title": "Long Source",
            "url": "https://example.com",
            "source_type": "website",
            "extracted_content": long_content,
            "extraction_status": "success",
        }
    ]
    mock_order.execute.return_value = mock_response

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        return mock_sources

    mock_supabase.table.side_effect = table_router

    results = await repo.get_raw_sources_by_session(session_id, user_id)

    assert len(results) == 1
    assert len(results[0]["extracted_content"]) == 15000
    assert results[0]["extracted_content"] == long_content


@pytest.mark.anyio
async def test_get_raw_sources_by_session_database_errors_handled(mock_supabase):
    """Translates database APIError to ClarityXException(400) and connection errors to 503."""
    repo = SourceRepository()
    session_id = str(uuid4())
    user_id = str(uuid4())

    # 1. APIError (e.g. Postgres syntax / schema error)
    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    mock_sources = MagicMock()
    mock_order = MagicMock()
    mock_sources.select.return_value.eq.return_value.order.return_value = mock_order
    mock_order.execute.side_effect = APIError({"message": "relation does not exist", "code": "42P01"})

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        return mock_sources

    mock_supabase.table.side_effect = table_router

    with pytest.raises(ClarityXException) as exc_info:
        await repo.get_raw_sources_by_session(session_id, user_id)

    assert exc_info.value.status_code == 400
    assert "failed during get_raw_sources_by_session" in exc_info.value.message

    # 2. Connection failure -> DatabaseConnectionError (503)
    mock_order.execute.side_effect = ConnectionError("Network unreachable")

    with pytest.raises(DatabaseConnectionError) as exc_info:
        await repo.get_raw_sources_by_session(session_id, user_id)

    assert exc_info.value.status_code == 503
    assert "Unable to complete database operation" in exc_info.value.message


@pytest.mark.anyio
async def test_get_raw_sources_by_session_async_thread_offloaded(mock_supabase):
    """Verifies synchronous database call is offloaded via anyio.to_thread.run_sync."""
    import anyio

    repo = SourceRepository()
    session_id = str(uuid4())
    user_id = str(uuid4())

    mock_sessions = MagicMock()
    mock_sessions.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": session_id}
    ]

    mock_sources = MagicMock()
    mock_order = MagicMock()
    mock_sources.select.return_value.eq.return_value.order.return_value = mock_order
    mock_response = MagicMock()
    mock_response.data = [{"source_code": "S1", "extracted_content": "Content"}]
    mock_order.execute.return_value = mock_response

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_sessions
        return mock_sources

    mock_supabase.table.side_effect = table_router

    with patch("anyio.to_thread.run_sync", wraps=anyio.to_thread.run_sync) as spy_run_sync:
        results = await repo.get_raw_sources_by_session(session_id, user_id)
        assert len(results) == 1
        assert spy_run_sync.called

