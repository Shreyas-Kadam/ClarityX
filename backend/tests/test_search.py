"""Unit tests for app/services/search_service.py (Phase 5.2).

All DDGS network calls are fully mocked – no real search requests are made.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.services.search_service import (
    DuckDuckGoSearchService,
    SearchError,
    SearchResultItem,
    SearchTimeoutError,
    deduplicate_urls,
    is_valid_search_url,
    normalize_url,
)
from app.core.exceptions import SSRFSecurityError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw_result(href="https://example.com", title="Example", body="Snippet"):
    """Build a minimal raw DDGS result dict."""
    return {"href": href, "title": title, "body": body}


def _make_mock_ddgs(raw_results):
    """Return a MagicMock that mimics the DDGS context-manager API."""
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = raw_results

    mock_ddgs_ctx = MagicMock()
    mock_ddgs_ctx.__enter__ = MagicMock(return_value=mock_ddgs_instance)
    mock_ddgs_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ddgs_ctx


# ---------------------------------------------------------------------------
# DuckDuckGoSearchService.search tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_search_success():
    """Returns normalised SearchResultItem list when DDGS succeeds."""
    raw = [_make_raw_result("https://example.com", "Example", "Example snippet")]

    with patch("app.services.search_service.DDGS", return_value=_make_mock_ddgs(raw)):
        service = DuckDuckGoSearchService()
        results = await service.search("test query", max_results=5)

    assert len(results) == 1
    assert isinstance(results[0], SearchResultItem)
    assert results[0].title == "Example"
    assert results[0].url == "https://example.com"
    assert results[0].snippet == "Example snippet"


@pytest.mark.anyio
async def test_search_empty_results():
    """Returns an empty list when DDGS finds nothing."""
    with patch("app.services.search_service.DDGS", return_value=_make_mock_ddgs([])):
        service = DuckDuckGoSearchService()
        results = await service.search("obscure nothing query")

    assert results == []


@pytest.mark.anyio
async def test_search_missing_title():
    """Falls back to 'Untitled' when the title key is absent or empty."""
    raw = [{"href": "https://example.com", "body": "Snippet"}]  # no 'title'

    with patch("app.services.search_service.DDGS", return_value=_make_mock_ddgs(raw)):
        service = DuckDuckGoSearchService()
        results = await service.search("query")

    assert len(results) == 1
    assert results[0].title == "Untitled"


@pytest.mark.anyio
async def test_search_missing_title_empty_string():
    """Falls back to 'Untitled' when title is an empty string."""
    raw = [{"href": "https://example.com", "title": "", "body": "Snippet"}]

    with patch("app.services.search_service.DDGS", return_value=_make_mock_ddgs(raw)):
        service = DuckDuckGoSearchService()
        results = await service.search("query")

    assert results[0].title == "Untitled"


@pytest.mark.anyio
async def test_search_missing_snippet():
    """Sets snippet to empty string when body key is absent."""
    raw = [{"href": "https://example.com", "title": "No body"}]  # no 'body'

    with patch("app.services.search_service.DDGS", return_value=_make_mock_ddgs(raw)):
        service = DuckDuckGoSearchService()
        results = await service.search("query")

    assert results[0].snippet == ""


@pytest.mark.anyio
async def test_search_malformed_result_no_href():
    """Skips results that have no href (or empty href)."""
    raw = [
        {"title": "No URL", "body": "Some body"},       # missing href
        {"href": "", "title": "Empty URL", "body": ""},  # empty href
        _make_raw_result("https://good.com", "Good", "Good snippet"),
    ]

    with patch("app.services.search_service.DDGS", return_value=_make_mock_ddgs(raw)):
        service = DuckDuckGoSearchService()
        results = await service.search("query", max_results=10)

    assert len(results) == 1
    assert results[0].url == "https://good.com"


@pytest.mark.anyio
async def test_search_provider_timeout():
    """Raises SearchTimeoutError when anyio.fail_after cancels the operation."""
    with patch("app.services.search_service.anyio.fail_after") as mock_fail_after:
        # Simulate fail_after raising TimeoutError on __exit__
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=None)
        cm.__exit__ = MagicMock(side_effect=TimeoutError("timed out"))
        mock_fail_after.return_value = cm

        service = DuckDuckGoSearchService()
        with pytest.raises(SearchTimeoutError):
            await service.search("query")


@pytest.mark.anyio
async def test_search_provider_failure():
    """Raises SearchError when DDGS raises an unexpected exception."""
    raw_exc = RuntimeError("network unavailable")

    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.side_effect = raw_exc

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_ddgs_instance)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("app.services.search_service.DDGS", return_value=mock_ctx):
        service = DuckDuckGoSearchService()
        with pytest.raises(SearchError) as exc_info:
            await service.search("query")

    assert exc_info.value.status_code == 503
    assert "RuntimeError" in exc_info.value.detail


@pytest.mark.anyio
async def test_search_result_limit_enforcement():
    """Returns at most max_results items even if DDGS returns more."""
    raw = [_make_raw_result(f"https://example{i}.com", f"Title {i}", f"Body {i}") for i in range(10)]

    with patch("app.services.search_service.DDGS", return_value=_make_mock_ddgs(raw)):
        service = DuckDuckGoSearchService()
        results = await service.search("query", max_results=3)

    assert len(results) == 3


@pytest.mark.anyio
async def test_search_uses_settings_default_limit():
    """Uses MAX_SEARCH_RESULTS_PER_QUERY from settings when max_results is None."""
    raw = [_make_raw_result(f"https://example{i}.com") for i in range(10)]

    with patch("app.services.search_service.DDGS", return_value=_make_mock_ddgs(raw)):
        service = DuckDuckGoSearchService()
        # Default is 5 from settings
        results = await service.search("query")  # no max_results override

    assert len(results) == 5


# ---------------------------------------------------------------------------
# normalize_url tests
# ---------------------------------------------------------------------------

def test_normalize_url_removes_fragment():
    url = "https://example.com/page#section"
    assert normalize_url(url) == "https://example.com/page"


def test_normalize_url_removes_tracking_params():
    url = "https://example.com/article?utm_source=newsletter&id=42"
    result = normalize_url(url)
    assert "utm_source" not in result
    assert "id=42" in result


def test_normalize_url_removes_all_tracking_params():
    url = (
        "https://example.com/page?"
        "utm_source=google&utm_medium=cpc&utm_campaign=brand"
        "&utm_term=kw&utm_content=ad&fbclid=abc&gclid=xyz&ref=home&source=email"
    )
    result = normalize_url(url)
    assert "utm_" not in result
    assert "fbclid" not in result
    assert "gclid" not in result
    assert "ref=" not in result
    assert "source=" not in result


def test_normalize_url_preserves_content_params():
    url = "https://example.com/search?page=2&id=123&q=python"
    result = normalize_url(url)
    assert "page=2" in result
    assert "id=123" in result
    assert "q=python" in result


def test_normalize_url_lowercase_hostname():
    url = "HTTPS://EXAMPLE.COM/Path"
    result = normalize_url(url)
    assert result.startswith("https://example.com/")


def test_normalize_url_preserves_path():
    url = "https://Example.COM/Some/Path"
    result = normalize_url(url)
    assert "/Some/Path" in result


def test_normalize_url_no_fragment_when_none():
    url = "https://example.com/page"
    result = normalize_url(url)
    assert "#" not in result


def test_normalize_url_empty_query_preserved():
    url = "https://example.com/page"
    result = normalize_url(url)
    assert result == "https://example.com/page"


def test_normalize_url_root_path_identical():
    """Empty root path and '/' normalize identically to '/'."""
    assert normalize_url("https://example.com") == normalize_url("https://example.com/") == "https://example.com/"


def test_normalize_url_sorted_query_parameters():
    """Query parameters are sorted deterministically regardless of input order."""
    assert (
        normalize_url("https://example.com?b=2&a=1")
        == normalize_url("https://example.com?a=1&b=2")
        == "https://example.com/?a=1&b=2"
    )


def test_normalize_url_sorted_multi_values():
    """Multiple values for the same key are sorted deterministically."""
    assert (
        normalize_url("https://example.com?tag=math&tag=ai")
        == normalize_url("https://example.com?tag=ai&tag=math")
        == "https://example.com/?tag=ai&tag=math"
    )


# ---------------------------------------------------------------------------
# deduplicate_urls tests
# ---------------------------------------------------------------------------

def test_deduplicate_urls_preserves_order():
    urls = [
        "https://a.com",
        "https://b.com",
        "https://a.com",
        "https://c.com",
        "https://b.com",
    ]
    result = deduplicate_urls(urls)
    assert result == ["https://a.com", "https://b.com", "https://c.com"]


def test_deduplicate_urls_unique():
    urls = ["https://a.com", "https://b.com", "https://c.com"]
    result = deduplicate_urls(urls)
    assert result == urls


def test_deduplicate_urls_all_same():
    urls = ["https://a.com"] * 5
    result = deduplicate_urls(urls)
    assert result == ["https://a.com"]


def test_deduplicate_urls_empty():
    assert deduplicate_urls([]) == []


# ---------------------------------------------------------------------------
# is_valid_search_url tests
# ---------------------------------------------------------------------------

def test_is_valid_search_url_http():
    assert is_valid_search_url("http://example.com") is True


def test_is_valid_search_url_https():
    assert is_valid_search_url("https://example.com") is True


def test_is_valid_search_url_rejects_ftp():
    assert is_valid_search_url("ftp://example.com") is False


def test_is_valid_search_url_rejects_file_scheme():
    assert is_valid_search_url("file:///etc/passwd") is False


def test_is_valid_search_url_rejects_credentials():
    assert is_valid_search_url("https://user:pass@example.com") is False


def test_is_valid_search_url_rejects_private_ip():
    """validate_url_syntax raises SSRFSecurityError for private/internal IPs."""
    with patch(
        "app.services.search_service.validate_url_syntax",
        side_effect=SSRFSecurityError(),
    ):
        assert is_valid_search_url("https://192.168.1.1/page") is False


def test_is_valid_search_url_malformed():
    assert is_valid_search_url("not-a-url") is False


def test_is_valid_search_url_empty_string():
    assert is_valid_search_url("") is False


def test_is_valid_search_url_user_only_credential():
    """URL with only a username (no password) should also be rejected."""
    assert is_valid_search_url("https://user@example.com") is False


# =============================================================================
# PHASE 5.3: SEARCH DISCOVERY ORCHESTRATION TESTS
# =============================================================================

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4
from httpx import ASGITransport, AsyncClient

from app.database.repositories import ResearchRepository, SourceRepository
from app.main import app
from app.routes.sources import get_research_repository, get_source_repository
from app.schemas.search import (
    FailedExtractionResult,
    SearchDiscoveryData,
    SearchSourceEnvelope,
    SearchSourceRequest,
    SkippedSearchResult,
)
from app.schemas.source import WebsiteExtractionResult
from app.services.search_orchestrator import SearchOrchestrationService


@pytest.fixture(autouse=True)
def reset_test_overrides():
    """Ensures FastAPI dependency overrides are cleared after each test."""
    yield
    app.dependency_overrides.clear()


def create_test_auth_user(
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


def make_persisted_source_record(
    session_id: str,
    code: str = "S1",
    title: str = "Discovered Article",
    url: str = "https://example.com/article",
    source_type: str = "website",
    content: str = "Sample extracted content from article.",
    extraction_status: str = "success",
):
    """Helper creating a persisted source database dict."""
    return {
        "id": str(uuid4()),
        "research_id": session_id,
        "source_code": code,
        "title": title,
        "url": url,
        "source_type": source_type,
        "extracted_content": content,
        "published_at": None,
        "accessed_at": datetime.now(timezone.utc),
        "extraction_status": extraction_status,
        "created_at": datetime.now(timezone.utc),
    }


# ---------------------------------------------------------------------------
# Discovery Orchestration Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_discovery_empty_provider_results():
    """Returns 0 attempted/persisted with empty lists when search provider returns no results."""
    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=[])

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.count_sources = AsyncMock(return_value=1)
    mock_repo.get_session_urls = AsyncMock(return_value=[])

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=str(uuid4()),
        user_id="user-123",
        query="no results query",
        max_results=3,
    )

    assert data.total_found == 0
    assert data.attempted_count == 0
    assert data.persisted_count == 0
    assert data.skipped_count == 0
    assert data.failed_count == 0
    assert data.sources == []


@pytest.mark.anyio
async def test_discovery_url_validation_and_filtering():
    """Invalid URLs (credentials, bad scheme, SSRF) are filtered and added to skipped with reason 'invalid_url'."""
    raw_results = [
        SearchResultItem(title="Bad Scheme", url="ftp://example.com/file", snippet=""),
        SearchResultItem(title="Has Creds", url="https://user:pass@example.com/", snippet=""),
        SearchResultItem(title="Valid", url="https://example.com/valid", snippet="Valid snippet"),
    ]

    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=raw_results)

    session_id = str(uuid4())
    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])
    mock_repo.create_source = AsyncMock(
        return_value=make_persisted_source_record(session_id, "S1", url="https://example.com/valid")
    )

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Valid Article",
            extracted_content="Extracted readable text content.",
            extraction_status="success",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="filtering test",
    )

    assert data.total_found == 3
    assert data.attempted_count == 1
    assert data.persisted_count == 1
    assert data.skipped_count == 2
    assert all(s.reason == "invalid_url" for s in data.skipped)


@pytest.mark.anyio
async def test_discovery_duplicate_urls_in_batch():
    """Duplicate URLs in the same search result set are skipped with reason 'duplicate_result'."""
    raw_results = [
        SearchResultItem(title="A 1", url="https://example.com/page#one", snippet=""),
        SearchResultItem(title="A 2", url="https://example.com/page#two", snippet=""),
        SearchResultItem(title="B", url="https://example.com/other", snippet=""),
    ]

    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=raw_results)

    session_id = str(uuid4())
    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])
    mock_repo.create_source = AsyncMock(
        side_effect=[
            make_persisted_source_record(session_id, "S1", url="https://example.com/page"),
            make_persisted_source_record(session_id, "S2", url="https://example.com/other"),
        ]
    )

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Page",
            extracted_content="Content text.",
            extraction_status="success",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="dedup batch test",
    )

    assert data.total_found == 3
    assert data.attempted_count == 2
    assert data.persisted_count == 2
    assert data.skipped_count == 1
    assert data.skipped[0].reason == "duplicate_result"


@pytest.mark.anyio
async def test_discovery_existing_session_url_skipped():
    """URLs already present in the research session are skipped with reason 'already_stored'."""
    raw_results = [
        SearchResultItem(title="Existing", url="https://example.com/already-here", snippet=""),
        SearchResultItem(title="New", url="https://example.com/brand-new", snippet=""),
    ]

    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=raw_results)

    session_id = str(uuid4())
    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.count_sources = AsyncMock(return_value=1)
    mock_repo.get_session_urls = AsyncMock(return_value=["https://example.com/already-here"])
    mock_repo.create_source = AsyncMock(
        return_value=make_persisted_source_record(session_id, "S2", url="https://example.com/brand-new")
    )

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Brand New",
            extracted_content="Content.",
            extraction_status="success",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="existing url test",
    )

    assert data.total_found == 2
    assert data.attempted_count == 1
    assert data.persisted_count == 1
    assert data.skipped_count == 1
    assert data.skipped[0].reason == "already_stored"


@pytest.mark.anyio
async def test_discovery_capacity_remaining_calculation():
    """When remaining capacity is 2 and 4 candidates exist, only 2 are attempted and 2 skipped with capacity_exceeded."""
    raw_results = [
        SearchResultItem(title=f"Page {i}", url=f"https://example.com/page-{i}", snippet="")
        for i in range(1, 5)
    ]

    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=raw_results)

    session_id = str(uuid4())
    mock_repo = MagicMock(spec=SourceRepository)
    # Session already has 3 sources, max capacity is 5 => remaining capacity is 2
    mock_repo.count_sources = AsyncMock(return_value=3)
    mock_repo.get_session_urls = AsyncMock(return_value=[])
    mock_repo.create_source = AsyncMock(
        side_effect=[
            make_persisted_source_record(session_id, "S4", url="https://example.com/page-1"),
            make_persisted_source_record(session_id, "S5", url="https://example.com/page-2"),
        ]
    )

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Page",
            extracted_content="Content.",
            extraction_status="success",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="capacity test",
        max_results=5,
    )

    assert data.total_found == 4
    assert data.attempted_count == 2
    assert data.persisted_count == 2
    assert data.skipped_count == 2
    assert all(s.reason == "capacity_exceeded" for s in data.skipped)


@pytest.mark.anyio
async def test_discovery_provider_failure_propagates():
    """Search provider failure raises SearchError and does not return empty results."""
    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(side_effect=SearchError("Provider unavailable"))

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
    )

    with pytest.raises(SearchError) as exc_info:
        await orchestrator.search_and_persist_sources(
            research_id=str(uuid4()),
            user_id="user-123",
            query="failing provider",
        )
    assert exc_info.value.status_code == 503


@pytest.mark.anyio
async def test_discovery_provider_timeout_propagates():
    """Search provider timeout raises SearchTimeoutError and does not return empty results."""
    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(side_effect=SearchTimeoutError())

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
    )

    with pytest.raises(SearchTimeoutError) as exc_info:
        await orchestrator.search_and_persist_sources(
            research_id=str(uuid4()),
            user_id="user-123",
            query="timing out provider",
        )
    assert exc_info.value.status_code == 504


# ---------------------------------------------------------------------------
# Extraction and Persistence Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_extraction_successful_persisted():
    """Successful website extraction is persisted and returned in the sources list."""
    session_id = str(uuid4())
    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=[
        SearchResultItem(title="Article 1", url="https://example.com/art1", snippet="")
    ])

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])
    mock_repo.create_source = AsyncMock(
        return_value=make_persisted_source_record(
            session_id, "S1", title="Article 1", url="https://example.com/art1", extraction_status="success"
        )
    )

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Article 1",
            extracted_content="Full article content text.",
            extraction_status="success",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="success test",
    )

    assert data.persisted_count == 1
    assert data.failed_count == 0
    assert len(data.sources) == 1
    assert data.sources[0].source_code == "S1"
    assert data.sources[0].extraction_status == "success"
    mock_repo.create_source.assert_awaited_once()


@pytest.mark.anyio
async def test_extraction_partial_persisted():
    """Partial website extraction (e.g. truncated content) is persisted with status 'partial'."""
    session_id = str(uuid4())
    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=[
        SearchResultItem(title="Partial Article", url="https://example.com/partial", snippet="")
    ])

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])
    mock_repo.create_source = AsyncMock(
        return_value=make_persisted_source_record(
            session_id, "S1", title="Partial Article", url="https://example.com/partial", extraction_status="partial"
        )
    )

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Partial Article",
            extracted_content="Partial content extracted.",
            extraction_status="partial",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="partial test",
    )

    assert data.persisted_count == 1
    assert data.sources[0].extraction_status == "partial"
    mock_repo.create_source.assert_awaited_once()


@pytest.mark.anyio
async def test_extraction_failed_not_persisted():
    """Failed extraction is recorded in 'failed' list and never persisted to the database."""
    session_id = str(uuid4())
    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=[
        SearchResultItem(title="Broken Page", url="https://example.com/broken", snippet="")
    ])

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])
    mock_repo.create_source = AsyncMock()

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Broken Page",
            extracted_content="",
            extraction_status="failed",
            error_message="HTTP 404 Not Found",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="failure test",
    )

    assert data.persisted_count == 0
    assert data.failed_count == 1
    assert len(data.failed) == 1
    assert data.failed[0].url == "https://example.com/broken"
    assert "HTTP 404" in data.failed[0].error
    # Must NOT call create_source
    mock_repo.create_source.assert_not_called()


@pytest.mark.anyio
async def test_extraction_correct_source_type():
    """Persisted source records have source_type='website'."""
    session_id = str(uuid4())
    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=[
        SearchResultItem(title="Site", url="https://example.com/site", snippet="")
    ])

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])
    mock_repo.create_source = AsyncMock(
        return_value=make_persisted_source_record(session_id, "S1", source_type="website")
    )

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Site",
            extracted_content="Readable text.",
            extraction_status="success",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="source type test",
    )

    assert data.sources[0].source_type == "website"
    _, kwargs = mock_repo.create_source.call_args
    assert kwargs["source_type"] == "website"


@pytest.mark.anyio
async def test_extraction_sequential_source_codes():
    """Persisted sources receive sequential source codes (e.g., S1, S2, S3)."""
    session_id = str(uuid4())
    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=[
        SearchResultItem(title=f"Page {i}", url=f"https://example.com/{i}", snippet="")
        for i in range(1, 4)
    ])

    allocated = []

    async def mock_create(**kwargs):
        code = f"S{len(allocated) + 1}"
        allocated.append(code)
        return make_persisted_source_record(
            session_id=session_id,
            code=code,
            title=kwargs["title"],
            url=kwargs["url"],
            content=kwargs["extracted_content"],
        )

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])
    mock_repo.create_source = AsyncMock(side_effect=mock_create)

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title=f"Page {url}",
            extracted_content="Content text.",
            extraction_status="success",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="sequential codes test",
    )

    assert len(data.sources) == 3
    assert [s.source_code for s in data.sources] == ["S1", "S2", "S3"]


@pytest.mark.anyio
async def test_extraction_correct_metadata():
    """Persisted sources contain valid publication date and extraction metadata."""
    session_id = str(uuid4())
    pub_date = datetime(2026, 5, 20, 10, 0, 0, tzinfo=timezone.utc)

    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=[
        SearchResultItem(title="Dated Article", url="https://example.com/dated", snippet="")
    ])

    rec = make_persisted_source_record(session_id, "S1", title="Dated Article", url="https://example.com/dated")
    rec["published_at"] = pub_date

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])
    mock_repo.create_source = AsyncMock(return_value=rec)

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Dated Article",
            extracted_content="Article text.",
            published_at=pub_date,
            extraction_status="success",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="metadata test",
    )

    assert data.sources[0].published_at == pub_date
    _, kwargs = mock_repo.create_source.call_args
    assert kwargs["published_at"] == pub_date


@pytest.mark.anyio
async def test_extraction_no_full_content_in_search_response():
    """Full extracted_content is never returned in search response data (content_preview only)."""
    session_id = str(uuid4())
    large_content = "Word " * 200  # 1000 characters

    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=[
        SearchResultItem(title="Big Article", url="https://example.com/big", snippet="")
    ])

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])
    mock_repo.create_source = AsyncMock(
        return_value=make_persisted_source_record(
            session_id, "S1", title="Big Article", url="https://example.com/big", content=large_content
        )
    )

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Big Article",
            extracted_content=large_content,
            extraction_status="success",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="preview test",
    )

    source_preview = data.sources[0]
    # SourcePreviewResponse must not have extracted_content
    assert not hasattr(source_preview, "extracted_content")
    # content_preview is capped at 250 chars + "..."
    assert len(source_preview.content_preview) <= 253
    assert source_preview.content_preview.endswith("...")


@pytest.mark.anyio
async def test_extraction_concurrency_bounded_to_3():
    """Verify that candidate extractions execute concurrently with a bounded limit of 3."""
    active_count = 0
    max_active_count = 0
    lock = asyncio.Lock()

    async def mock_extract(url: str):
        nonlocal active_count, max_active_count
        async with lock:
            active_count += 1
            if active_count > max_active_count:
                max_active_count = active_count

        await asyncio.sleep(0.05)

        async with lock:
            active_count -= 1

        return WebsiteExtractionResult(
            url=url,
            title="Title",
            extracted_content="Extracted text.",
            extraction_status="success",
        )

    session_id = str(uuid4())
    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=[
        SearchResultItem(title=f"T{i}", url=f"https://example.com/{i}", snippet="")
        for i in range(5)
    ])

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])
    mock_repo.create_source = AsyncMock(
        side_effect=lambda **kwargs: make_persisted_source_record(session_id, "S1", url=kwargs["url"])
    )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
        concurrency_limit=3,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="concurrency test",
        max_results=5,
    )

    assert max_active_count <= 3
    assert data.persisted_count == 5


# =============================================================================
# PHASE 5.3: API ROUTE TESTS (POST /api/research/{research_id}/sources/search)
# =============================================================================

TEST_SESSION_ID = "11111111-2222-3333-4444-555555555555"
TEST_USER_ID = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"


@pytest.mark.anyio
async def test_api_search_missing_authentication():
    """POST /search returns HTTP 401 when Authorization header is absent."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/research/{TEST_SESSION_ID}/sources/search",
            json={"query": "test query"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert "Authorization header" in data["message"] or "Authentication required" in data["message"]


@pytest.mark.anyio
async def test_api_search_invalid_authentication():
    """POST /search returns HTTP 401 when Bearer token is invalid or expired."""
    mock_client = MagicMock()
    mock_client.auth.get_user.side_effect = Exception("Token expired")

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{TEST_SESSION_ID}/sources/search",
                headers={"Authorization": "Bearer expired-token"},
                json={"query": "test query"},
            )
            assert response.status_code == 401
            assert response.json()["success"] is False


@pytest.mark.anyio
async def test_api_search_cross_user_access_blocked():
    """POST /search returns HTTP 404 when user attempts to search on another user's session."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_test_auth_user(user_id="99999999-9999-9999-9999-999999999999")

    mock_research_repo = MagicMock(spec=ResearchRepository)
    # Session not found for this user
    mock_research_repo.get_session_by_id = AsyncMock(return_value=None)

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{TEST_SESSION_ID}/sources/search",
                headers={"Authorization": "Bearer valid-token"},
                json={"query": "cross user test"},
            )
            assert response.status_code == 404
            data = response.json()
            assert data["success"] is False
            assert "not found or unauthorized" in data["message"].lower()


@pytest.mark.anyio
async def test_api_search_query_omitted_uses_research_goal():
    """When query is omitted in request body, the research session's research_goal is used."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_test_auth_user(user_id=TEST_USER_ID)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": TEST_SESSION_ID,
        "user_id": TEST_USER_ID,
        "research_goal": "Quantum computing advances in 2026",
    })

    captured_query = None

    async def mock_orchestrator_search(research_id, user_id, query, max_results):
        nonlocal captured_query
        captured_query = query
        return SearchDiscoveryData(
            query=query,
            total_found=0,
            attempted_count=0,
            persisted_count=0,
            skipped_count=0,
            failed_count=0,
            sources=[],
        )

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth),
        patch.object(SearchOrchestrationService, "search_and_persist_sources", side_effect=mock_orchestrator_search),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{TEST_SESSION_ID}/sources/search",
                headers={"Authorization": "Bearer valid-token"},
                json={},  # query omitted
            )
            assert response.status_code == 200
            assert captured_query == "Quantum computing advances in 2026"
            assert response.json()["data"]["query"] == "Quantum computing advances in 2026"


@pytest.mark.anyio
async def test_api_search_custom_query():
    """Custom search query override is used instead of session research_goal."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_test_auth_user(user_id=TEST_USER_ID)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": TEST_SESSION_ID,
        "user_id": TEST_USER_ID,
        "research_goal": "Default Goal",
    })

    captured_query = None

    async def mock_orchestrator_search(research_id, user_id, query, max_results):
        nonlocal captured_query
        captured_query = query
        return SearchDiscoveryData(
            query=query,
            total_found=0,
            attempted_count=0,
            persisted_count=0,
            skipped_count=0,
            failed_count=0,
            sources=[],
        )

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth),
        patch.object(SearchOrchestrationService, "search_and_persist_sources", side_effect=mock_orchestrator_search),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{TEST_SESSION_ID}/sources/search",
                headers={"Authorization": "Bearer valid-token"},
                json={"query": "My Custom Search Query", "max_results": 2},
            )
            assert response.status_code == 200
            assert captured_query == "My Custom Search Query"


@pytest.mark.anyio
async def test_api_search_invalid_max_results():
    """max_results outside 1-5 range is rejected with HTTP 422."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_test_auth_user(user_id=TEST_USER_ID)

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Too high (> 5)
            res_high = await client.post(
                f"/api/research/{TEST_SESSION_ID}/sources/search",
                headers={"Authorization": "Bearer valid-token"},
                json={"max_results": 10},
            )
            assert res_high.status_code == 422

            # Too low (< 1)
            res_low = await client.post(
                f"/api/research/{TEST_SESSION_ID}/sources/search",
                headers={"Authorization": "Bearer valid-token"},
                json={"max_results": 0},
            )
            assert res_low.status_code == 422


@pytest.mark.anyio
async def test_api_search_unexpected_fields_rejected():
    """Unexpected request fields are rejected with HTTP 422 (extra='forbid')."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_test_auth_user(user_id=TEST_USER_ID)

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{TEST_SESSION_ID}/sources/search",
                headers={"Authorization": "Bearer valid-token"},
                json={"query": "test", "unauthorized_extra_field": "injected"},
            )
            assert response.status_code == 422


@pytest.mark.anyio
async def test_api_search_full_source_capacity():
    """Attempting search when research session already has 5 sources returns HTTP 400."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_test_auth_user(user_id=TEST_USER_ID)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": TEST_SESSION_ID,
        "user_id": TEST_USER_ID,
        "research_goal": "Capacity full goal",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    # Session already has 5 sources
    mock_source_repo.count_sources = AsyncMock(return_value=5)

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{TEST_SESSION_ID}/sources/search",
                headers={"Authorization": "Bearer valid-token"},
                json={"query": "try search anyway"},
            )
            assert response.status_code == 400
            data = response.json()
            assert data["success"] is False
            assert "capacity reached" in data["message"].lower()


@pytest.mark.anyio
async def test_api_search_success():
    """Authenticated user successfully searches and persists sources via the API."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_test_auth_user(user_id=TEST_USER_ID)

    mock_research_repo = MagicMock(spec=ResearchRepository)
    mock_research_repo.get_session_by_id = AsyncMock(return_value={
        "id": TEST_SESSION_ID,
        "user_id": TEST_USER_ID,
        "research_goal": "Successful search goal",
    })

    mock_source_repo = MagicMock(spec=SourceRepository)
    mock_source_repo.count_sources = AsyncMock(return_value=0)
    mock_source_repo.get_session_urls = AsyncMock(return_value=[])
    mock_source_repo.create_source = AsyncMock(
        return_value=make_persisted_source_record(
            TEST_SESSION_ID, "S1", title="Discovered Result", url="https://example.com/result"
        )
    )

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Discovered Result",
            extracted_content="Extracted readable text.",
            extraction_status="success",
        )

    mock_ddgs = MagicMock()
    mock_ddgs.text.return_value = [
        {"href": "https://example.com/result", "title": "Discovered Result", "body": "Snippet text"}
    ]
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_ddgs)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    app.dependency_overrides[get_research_repository] = lambda: mock_research_repo
    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth),
        patch("app.services.search_service.DDGS", return_value=mock_ctx),
        patch("app.services.search_orchestrator.extract_website_content", side_effect=mock_extract),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{TEST_SESSION_ID}/sources/search",
                headers={"Authorization": "Bearer valid-token"},
                json={"query": "test query", "max_results": 1},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["message"] == "Search discovery completed successfully"
            result_data = data["data"]
            assert result_data["query"] == "test query"
            assert result_data["total_found"] == 1
            assert result_data["persisted_count"] == 1
            assert len(result_data["sources"]) == 1
            assert result_data["sources"][0]["source_code"] == "S1"
            assert result_data["sources"][0]["url"] == "https://example.com/result"
            assert "content_preview" in result_data["sources"][0]
            assert "extracted_content" not in result_data["sources"][0]


# =============================================================================
# PHASE 5.3.1: SAFETY HARDENING TESTS
# =============================================================================

from app.core.exceptions import ClarityXException, DatabaseConnectionError


@pytest.mark.anyio
async def test_count_sources_propagates_database_error():
    """count_sources raises DatabaseConnectionError/ClarityXException instead of returning 0 on DB error."""
    repo = SourceRepository()
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("DB down")

    with patch.object(SourceRepository, "client", new_callable=lambda: property(lambda self: mock_client)):
        with pytest.raises((DatabaseConnectionError, ClarityXException)):
            await repo.count_sources("11111111-1111-1111-1111-111111111111")


@pytest.mark.anyio
async def test_get_session_urls_propagates_database_error():
    """get_session_urls raises DatabaseConnectionError/ClarityXException instead of returning [] on DB error."""
    repo = SourceRepository()
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("DB down")

    with patch.object(SourceRepository, "client", new_callable=lambda: property(lambda self: mock_client)):
        with pytest.raises((DatabaseConnectionError, ClarityXException)):
            await repo.get_session_urls("11111111-1111-1111-1111-111111111111")


@pytest.mark.anyio
async def test_orchestrator_stops_when_count_query_fails():
    """Orchestrator raises and stops before executing search when count_sources fails."""
    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.verify_session_ownership = AsyncMock(return_value=True)
    mock_repo.count_sources = AsyncMock(side_effect=DatabaseConnectionError("Connection lost"))

    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock()

    orchestrator = SearchOrchestrationService(source_repo=mock_repo, search_service=mock_search)

    with pytest.raises(DatabaseConnectionError):
        await orchestrator.search_and_persist_sources(
            research_id=str(uuid4()),
            user_id="user-123",
            query="test",
        )

    mock_search.search.assert_not_called()


@pytest.mark.anyio
async def test_orchestrator_stops_when_existing_url_retrieval_fails():
    """Orchestrator raises and stops before executing search when get_session_urls fails."""
    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.verify_session_ownership = AsyncMock(return_value=True)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(side_effect=DatabaseConnectionError("Connection lost"))

    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock()

    orchestrator = SearchOrchestrationService(source_repo=mock_repo, search_service=mock_search)

    with pytest.raises(DatabaseConnectionError):
        await orchestrator.search_and_persist_sources(
            research_id=str(uuid4()),
            user_id="user-123",
            query="test",
        )

    mock_search.search.assert_not_called()


@pytest.mark.anyio
async def test_orchestrator_stops_before_search_for_unauthorized_session():
    """Orchestrator verifies ownership and raises 404 before counting sources, getting URLs, or searching."""
    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.verify_session_ownership = AsyncMock(return_value=False)
    mock_repo.count_sources = AsyncMock()
    mock_repo.get_session_urls = AsyncMock()

    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock()

    orchestrator = SearchOrchestrationService(source_repo=mock_repo, search_service=mock_search)

    with pytest.raises(ClarityXException) as exc_info:
        await orchestrator.search_and_persist_sources(
            research_id=str(uuid4()),
            user_id="user-123",
            query="test",
        )

    assert exc_info.value.status_code == 404
    mock_repo.count_sources.assert_not_called()
    mock_repo.get_session_urls.assert_not_called()
    mock_search.search.assert_not_called()


@pytest.mark.anyio
async def test_orchestrator_persistence_failure_reported_accurately_after_success():
    """Candidate 1 succeeds, Candidate 2 fails DB insertion: stats accurately reflect 1 persisted, 1 failed."""
    session_id = str(uuid4())
    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.verify_session_ownership = AsyncMock(return_value=True)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])

    record1 = make_persisted_source_record(session_id, "S1", title="Article 1", url="https://example.com/1")

    async def mock_create(**kwargs):
        if kwargs["url"] == "https://example.com/1":
            return record1
        raise ClarityXException(message="Database write timeout", status_code=500)

    mock_repo.create_source = AsyncMock(side_effect=mock_create)

    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=[
        SearchResultItem(title="Article 1", url="https://example.com/1", snippet=""),
        SearchResultItem(title="Article 2", url="https://example.com/2", snippet=""),
    ])

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Article",
            extracted_content="Content text.",
            extraction_status="success",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="test query",
    )

    assert data.total_found == 2
    assert data.attempted_count == 2
    assert data.persisted_count == 1
    assert data.failed_count == 1
    assert len(data.sources) == 1
    assert data.sources[0].url == "https://example.com/1"
    assert len(data.failed) == 1
    assert data.failed[0].url == "https://example.com/2"
    assert "Database persistence failed" in data.failed[0].error


@pytest.mark.anyio
async def test_create_source_enforces_capacity_limit():
    """create_source directly enforces MAX_SOURCES_PER_SESSION=5 before attempting insertion."""
    repo = SourceRepository()
    session_id = str(uuid4())
    user_id = str(uuid4())

    with (
        patch.object(repo, "verify_session_ownership", new_callable=AsyncMock) as mock_owner,
        patch.object(repo, "count_sources", new_callable=AsyncMock) as mock_count,
    ):
        mock_owner.return_value = True
        mock_count.return_value = 5  # Already has 5 sources

        with pytest.raises(ClarityXException) as exc_info:
            await repo.create_source(
                session_id=session_id,
                user_id=user_id,
                source_type="website",
                extracted_content="Test content",
            )

        assert exc_info.value.status_code == 400
        assert "capacity reached" in exc_info.value.message.lower()


@pytest.mark.anyio
async def test_orchestrator_sequential_capacity_cutoff():
    """When session has 4 sources and 2 candidates are extracted, candidate 1 persists and candidate 2 is skipped with capacity_exceeded."""
    session_id = str(uuid4())
    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.verify_session_ownership = AsyncMock(return_value=True)

    # Initial count is 4. When candidate 1 persists, count becomes 5.
    count_call_count = 0
    async def mock_count_sources(sid):
        nonlocal count_call_count
        count_call_count += 1
        # Initial pre-search check returns 4; persistence check 1 returns 4; persistence check 2 returns 5
        if count_call_count <= 2:
            return 4
        return 5

    mock_repo.count_sources = AsyncMock(side_effect=mock_count_sources)
    mock_repo.get_session_urls = AsyncMock(return_value=[])

    record1 = make_persisted_source_record(session_id, "S5", title="Article 1", url="https://example.com/1")
    mock_repo.create_source = AsyncMock(return_value=record1)

    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=[
        SearchResultItem(title="Article 1", url="https://example.com/1", snippet=""),
        SearchResultItem(title="Article 2", url="https://example.com/2", snippet=""),
    ])

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Article",
            extracted_content="Content text.",
            extraction_status="success",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="test query",
        max_results=5,
    )

    # Candidate 1 was persisted, candidate 2 was cut off by capacity check
    assert data.persisted_count == 1
    assert data.skipped_count == 1
    assert data.skipped[0].reason == "capacity_exceeded"


@pytest.mark.anyio
async def test_orchestrator_handles_database_connection_error_during_persistence():
    """DatabaseConnectionError during create_source is caught and reported as sanitized persistence failure."""
    session_id = str(uuid4())
    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.verify_session_ownership = AsyncMock(return_value=True)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])
    mock_repo.create_source = AsyncMock(
        side_effect=DatabaseConnectionError("Unable to connect to the database")
    )

    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=[
        SearchResultItem(title="Article 1", url="https://example.com/1", snippet=""),
    ])

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Article",
            extracted_content="Content text.",
            extraction_status="success",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    data = await orchestrator.search_and_persist_sources(
        research_id=session_id,
        user_id="user-123",
        query="test query",
    )

    assert data.persisted_count == 0
    assert data.failed_count == 1
    assert len(data.failed) == 1
    assert "Database persistence failed" in data.failed[0].error
    assert "Unable to connect to the database" in data.failed[0].error


@pytest.mark.anyio
async def test_orchestrator_raises_unexpected_exception_during_persistence():
    """Unexpected programming error (e.g. RuntimeError) during persistence is re-raised to reach centralized handling."""
    session_id = str(uuid4())
    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.verify_session_ownership = AsyncMock(return_value=True)
    mock_repo.count_sources = AsyncMock(return_value=0)
    mock_repo.get_session_urls = AsyncMock(return_value=[])
    mock_repo.create_source = AsyncMock(
        side_effect=RuntimeError("Unexpected serialization crash")
    )

    mock_search = MagicMock(spec=DuckDuckGoSearchService)
    mock_search.search = AsyncMock(return_value=[
        SearchResultItem(title="Article 1", url="https://example.com/1", snippet=""),
    ])

    async def mock_extract(url: str):
        return WebsiteExtractionResult(
            url=url,
            title="Article",
            extracted_content="Content text.",
            extraction_status="success",
        )

    orchestrator = SearchOrchestrationService(
        source_repo=mock_repo,
        search_service=mock_search,
        extraction_fn=mock_extract,
    )

    with pytest.raises(RuntimeError) as exc_info:
        await orchestrator.search_and_persist_sources(
            research_id=session_id,
            user_id="user-123",
            query="test query",
        )

    assert "Unexpected serialization crash" in str(exc_info.value)




