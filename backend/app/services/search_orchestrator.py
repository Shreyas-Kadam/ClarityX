"""Search discovery and source persistence orchestration for ClarityX (Phase 5.3).

Coordinates:
1. Research session capacity validation.
2. Search query execution via DuckDuckGoSearchService.
3. Candidate URL validation (SSRF and scheme checks).
4. URL normalization and deduplication (against current batch and existing session sources).
5. Bounded concurrent website content extraction (concurrency limit = 3).
6. Sequential persistence into the sources repository in ranking order.
7. Aggregation of discovery statistics (total_found, attempted, persisted, skipped, failed).
"""

import asyncio
import logging
from typing import Callable, List, Optional, Set

from app.core.config import Settings, get_settings
from app.core.exceptions import ClarityXException
from app.database.repositories import SourceRepository
from app.schemas.search import (
    FailedExtractionResult,
    SearchDiscoveryData,
    SkippedSearchResult,
)
from app.schemas.source import SourcePreviewResponse, make_content_preview
from app.services.extraction_service import extract_website_content
from app.services.search_service import (
    DuckDuckGoSearchService,
    SearchResultItem,
    is_valid_search_url,
    normalize_url,
)

logger = logging.getLogger("clarityx.search.orchestrator")


class SearchOrchestrationService:
    """Orchestrates search discovery, URL filtering, website extraction, and persistence."""

    def __init__(
        self,
        source_repo: Optional[SourceRepository] = None,
        search_service: Optional[DuckDuckGoSearchService] = None,
        settings: Optional[Settings] = None,
        extraction_fn: Optional[Callable] = None,
        concurrency_limit: int = 3,
    ) -> None:
        self.source_repo = source_repo or SourceRepository()
        self.search_service = search_service or DuckDuckGoSearchService()
        self.settings = settings or get_settings()
        self.extract_fn = extraction_fn or extract_website_content
        self.concurrency_limit = concurrency_limit

    async def search_and_persist_sources(
        self,
        research_id: str,
        user_id: str,
        query: str,
        max_results: int = 3,
    ) -> SearchDiscoveryData:
        """Executes search discovery and persists eligible sources to the session."""
        max_capacity = self.settings.MAX_SOURCES_PER_SESSION

        # 1. Enforce session source capacity before making external search requests
        existing_count = await self.source_repo.count_sources(research_id)
        if existing_count >= max_capacity:
            raise ClarityXException(
                message="Source capacity reached",
                status_code=400,
                detail=f"Research session has reached the maximum capacity of {max_capacity} sources.",
            )

        remaining_capacity = max_capacity - existing_count

        # 2. Fetch existing session URLs for deduplication
        existing_raw_urls = await self.source_repo.get_session_urls(research_id)
        stored_normalized_urls: Set[str] = {
            normalize_url(u) for u in existing_raw_urls if u
        }

        # 3. Execute search provider (propagates SearchTimeoutError / SearchError)
        raw_results: List[SearchResultItem] = await self.search_service.search(
            query=query,
            max_results=max_results,
        )

        total_found = len(raw_results)
        candidates: List[SearchResultItem] = []
        skipped: List[SkippedSearchResult] = []
        seen_batch_urls: Set[str] = set()

        # 4. Filter, validate, and deduplicate candidates
        for item in raw_results:
            if not is_valid_search_url(item.url):
                skipped.append(
                    SkippedSearchResult(
                        url=item.url,
                        title=item.title,
                        reason="invalid_url",
                    )
                )
                continue

            norm_url = normalize_url(item.url)

            if norm_url in seen_batch_urls:
                skipped.append(
                    SkippedSearchResult(
                        url=item.url,
                        title=item.title,
                        reason="duplicate_result",
                    )
                )
                continue

            if norm_url in stored_normalized_urls:
                skipped.append(
                    SkippedSearchResult(
                        url=item.url,
                        title=item.title,
                        reason="already_stored",
                    )
                )
                continue

            if len(candidates) >= remaining_capacity:
                skipped.append(
                    SkippedSearchResult(
                        url=item.url,
                        title=item.title,
                        reason="capacity_exceeded",
                    )
                )
                continue

            seen_batch_urls.add(norm_url)
            candidates.append(item)

        if not candidates:
            return SearchDiscoveryData(
                query=query,
                total_found=total_found,
                attempted_count=0,
                persisted_count=0,
                skipped_count=len(skipped),
                failed_count=0,
                sources=[],
                skipped=skipped,
                failed=[],
            )

        # 5. Bounded concurrent extraction (concurrency limit = 3)
        semaphore = asyncio.Semaphore(self.concurrency_limit)

        async def _extract_candidate(candidate: SearchResultItem):
            async with semaphore:
                try:
                    result = await self.extract_fn(candidate.url)
                    return candidate, result, None
                except Exception as exc:
                    logger.warning(
                        "Extraction failed for candidate %s: %s",
                        candidate.url,
                        type(exc).__name__,
                    )
                    return candidate, None, exc

        extraction_results = await asyncio.gather(
            *[_extract_candidate(c) for c in candidates]
        )

        # 6. Sequential persistence in original search-result ordering
        persisted_sources: List[SourcePreviewResponse] = []
        failed: List[FailedExtractionResult] = []

        for candidate, result, exc in extraction_results:
            # Re-check capacity before each persistence
            current_count = await self.source_repo.count_sources(research_id)
            if current_count >= max_capacity:
                skipped.append(
                    SkippedSearchResult(
                        url=candidate.url,
                        title=candidate.title,
                        reason="capacity_exceeded",
                    )
                )
                continue

            # Verify extraction succeeded or produced partial usable content
            if exc is not None:
                failed.append(
                    FailedExtractionResult(
                        url=candidate.url,
                        title=candidate.title,
                        error="Extraction failed to produce usable content.",
                    )
                )
                continue

            if (
                result is None
                or result.extraction_status == "failed"
                or not result.extracted_content
                or not result.extracted_content.strip()
            ):
                err = (
                    result.error_message
                    if (result and result.error_message)
                    else "Extraction failed to produce usable content."
                )
                failed.append(
                    FailedExtractionResult(
                        url=candidate.url,
                        title=candidate.title,
                        error=err,
                    )
                )
                continue

            # Persist source (only for success and partial statuses)
            created = await self.source_repo.create_source(
                session_id=research_id,
                user_id=user_id,
                source_type="website",
                extracted_content=result.extracted_content,
                title=result.title or candidate.title or "Untitled Source",
                url=result.url or candidate.url,
                published_at=result.published_at,
                extraction_status=result.extraction_status,
            )

            if not created:
                failed.append(
                    FailedExtractionResult(
                        url=candidate.url,
                        title=candidate.title,
                        error="Database failed to persist source.",
                    )
                )
                continue

            # Format preview response (never return full extracted_content)
            source_dict = dict(created)
            full_content = source_dict.pop("extracted_content", "") or ""
            source_dict["content_preview"] = make_content_preview(
                full_content, max_chars=250
            )
            persisted_sources.append(
                SourcePreviewResponse.model_validate(source_dict)
            )
            stored_normalized_urls.add(
                normalize_url(result.url or candidate.url)
            )

        return SearchDiscoveryData(
            query=query,
            total_found=total_found,
            attempted_count=len(candidates),
            persisted_count=len(persisted_sources),
            skipped_count=len(skipped),
            failed_count=len(failed),
            sources=persisted_sources,
            skipped=skipped,
            failed=failed,
        )

