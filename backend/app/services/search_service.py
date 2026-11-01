"""Web search service for ClarityX using DuckDuckGo Search (DDGS).

Provides:
- DuckDuckGoSearchService: Executes DDGS text search in a thread pool with a
  hard anyio timeout. Normalises results to SearchResultItem models.
  Raises SearchTimeoutError on timeout; raises SearchError on provider failure.
- URL normalisation: normalize_url() — lowercase hostname, fragment removal,
  tracking-parameter stripping.
- URL deduplication: deduplicate_urls() — order-preserving.
- URL validation: is_valid_search_url() — scheme, credentials, and SSRF check.
"""

import logging
from typing import List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import anyio
from ddgs import DDGS
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.exceptions import ClarityXException, SSRFSecurityError
from app.services.ssrf_service import validate_url_syntax

logger = logging.getLogger("clarityx.search")

# Query parameters that carry only tracking information and should be stripped.
# Content-identifying parameters (page, id, q, …) are intentionally preserved.
TRACKING_PARAMS = frozenset({
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "ref",
    "source",
})


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class SearchError(ClarityXException):
    """Raised when the search provider returns an error or becomes unavailable."""

    def __init__(
        self,
        message: str = "Web search provider is currently unavailable.",
        detail: str = "",
    ) -> None:
        super().__init__(message=message, status_code=503, detail=detail or message)


class SearchTimeoutError(ClarityXException):
    """Raised when a search query exceeds the configured timeout."""

    def __init__(self, message: str = "Search request timed out.") -> None:
        super().__init__(message=message, status_code=504, detail=message)


# ---------------------------------------------------------------------------
# Internal data model
# ---------------------------------------------------------------------------

class SearchResultItem(BaseModel):
    """Normalised internal model for a single search result.

    This is an internal provider model – it is NOT exposed directly through
    the public API (that is the responsibility of Phase 5.3 schemas).
    """

    title: str
    url: str
    snippet: str


# ---------------------------------------------------------------------------
# Search service
# ---------------------------------------------------------------------------

class DuckDuckGoSearchService:
    """Wraps DDGS text search with async support, timeout enforcement, and
    result normalisation."""

    def __init__(self) -> None:
        self._settings = get_settings()

    async def search(
        self,
        query: str,
        max_results: Optional[int] = None,
    ) -> List[SearchResultItem]:
        """Execute a DDGS text search and return normalised results.

        The synchronous DDGS call is dispatched to a thread pool via
        ``anyio.to_thread.run_sync`` and wrapped with ``anyio.fail_after``
        to enforce the configured timeout without blocking the event loop.

        Args:
            query: The search query string.
            max_results: Override the default result cap for this call.

        Returns:
            A list of :class:`SearchResultItem` instances (at most *max_results*
            items long).

        Raises:
            SearchTimeoutError: If the search exceeds the configured timeout.
            SearchError: If the provider raises any other error.
        """
        limit = max_results if max_results is not None else self._settings.MAX_SEARCH_RESULTS_PER_QUERY
        timeout = self._settings.SEARCH_TIMEOUT

        def _run_search() -> list:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=limit))

        try:
            with anyio.fail_after(timeout):
                raw_results = await anyio.to_thread.run_sync(_run_search)
        except TimeoutError:
            logger.warning(
                "DuckDuckGo search timed out after %.1fs for query: %.80s",
                timeout,
                query,
            )
            raise SearchTimeoutError()
        except (SearchTimeoutError, SearchError):
            raise
        except Exception as exc:
            logger.warning(
                "DuckDuckGo search failed: %s – %s",
                type(exc).__name__,
                str(exc)[:120],
            )
            raise SearchError(
                message="Web search provider is currently unavailable.",
                detail=f"Provider error: {type(exc).__name__}",
            ) from exc

        results: List[SearchResultItem] = []
        for item in raw_results:
            url = (item.get("href") or "").strip()
            if not url:
                # Skip results with no URL – they cannot be used as sources.
                continue
            title = (item.get("title") or "").strip() or "Untitled"
            snippet = (item.get("body") or "").strip()
            results.append(SearchResultItem(title=title, url=url, snippet=snippet))

        return results[:limit]


# ---------------------------------------------------------------------------
# URL utilities
# ---------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    """Return a normalised form of *url*.

    Normalisations applied:
    - Scheme is lowercased.
    - Hostname is lowercased.
    - Standard ports (80 for http, 443 for https) are omitted; non-standard ports are kept.
    - Root path is normalized consistently: empty path '' and '/' both become '/'.
    - Fragment component is removed.
    - Tracking-only query parameters (see :data:`TRACKING_PARAMS`) are stripped.
    - Retained query parameters and multi-values are sorted deterministically.
    - Content-identifying query parameters are preserved.

    This function does **not** perform SSRF validation – use
    :func:`is_valid_search_url` for that.

    Args:
        url: The URL string to normalise.

    Returns:
        The normalised URL string.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    # Build a normalised netloc with lowercased hostname and stripped standard ports.
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    if port is not None:
        if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
            normalised_netloc = hostname
        else:
            normalised_netloc = f"{hostname}:{port}"
    else:
        normalised_netloc = hostname

    # Normalize empty root path and '/' consistently to '/'
    path = parsed.path
    if not path or path == "/":
        normalized_path = "/"
    else:
        normalized_path = path

    # Strip tracking-only query parameters, sort retained keys and values deterministically.
    if parsed.query:
        qs = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: sorted(v) for k, v in qs.items() if k.lower() not in TRACKING_PARAMS}
        sorted_items = sorted(filtered.items())
        new_query = urlencode(sorted_items, doseq=True)
    else:
        new_query = ""

    return urlunparse((
        scheme,
        normalised_netloc,
        normalized_path,
        parsed.params,
        new_query,
        "",  # fragment intentionally removed
    ))


def is_valid_search_url(url: str) -> bool:
    """Return ``True`` if *url* is safe to use as a search-discovered source.

    Checks performed:
    1. Scheme must be ``http`` or ``https``.
    2. URL must not contain embedded credentials (user:pass@).
    3. URL must pass :func:`~app.services.ssrf_service.validate_url_syntax`
       (rejects private ranges, loopback, cloud-metadata endpoints, etc.).

    Args:
        url: The URL string to validate.

    Returns:
        ``True`` if the URL is safe; ``False`` otherwise.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        if parsed.username or parsed.password:
            return False
        validate_url_syntax(url)
        return True
    except (SSRFSecurityError, Exception):
        return False


def deduplicate_urls(urls: List[str]) -> List[str]:
    """Return *urls* with duplicates removed while preserving the original order.

    Args:
        urls: A sequence of URL strings, potentially containing duplicates.

    Returns:
        A new list containing only the first occurrence of each URL.
    """
    seen: set = set()
    result: List[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result
