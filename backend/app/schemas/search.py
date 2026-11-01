"""Pydantic schemas for web search source discovery and integration (Phase 5.3)."""

from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.source import SourcePreviewResponse


class SearchSourceRequest(BaseModel):
    """Request payload for discovering and adding sources via web search."""

    query: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
        description="Optional search query override. Defaults to the session research goal if omitted.",
    )
    max_results: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Maximum number of search results to discover and process (1 to 5).",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            trimmed = v.strip()
            if not trimmed:
                raise ValueError("Query must not be empty or whitespace only when supplied.")
            return trimmed
        return v


class SkippedSearchResult(BaseModel):
    """Details of a candidate URL that was skipped during search discovery."""

    url: str
    title: Optional[str] = None
    reason: Literal[
        "invalid_url",
        "duplicate_result",
        "already_stored",
        "capacity_exceeded",
    ]

    model_config = ConfigDict(from_attributes=True)


class FailedExtractionResult(BaseModel):
    """Details of a candidate URL whose content extraction could not produce usable content."""

    url: str
    title: Optional[str] = None
    error: str = "Extraction failed to produce usable content."

    model_config = ConfigDict(from_attributes=True)


class SearchDiscoveryData(BaseModel):
    """Structured search discovery statistics and persisted source previews."""

    query: str
    total_found: int = 0
    attempted_count: int = 0
    persisted_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    sources: List[SourcePreviewResponse] = Field(default_factory=list)
    skipped: List[SkippedSearchResult] = Field(default_factory=list)
    failed: List[FailedExtractionResult] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# Alias for consistent naming with other API resources
SearchSourceResponse = SearchDiscoveryData


class SearchSourceEnvelope(BaseModel):
    """Standard API response envelope for search discovery operations."""

    success: bool = True
    message: str = "Search discovery completed successfully"
    data: SearchDiscoveryData

