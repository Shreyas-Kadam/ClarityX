"""Pydantic schemas for source extraction and persistence."""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class WebsiteExtractRequest(BaseModel):
    """Request payload for extracting website content."""

    url: str = Field(..., description="Target website URL to extract content from.")

    model_config = ConfigDict(extra="forbid")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("URL must not be empty.")
        return trimmed


class WebsiteExtractionResult(BaseModel):
    """Structured extraction result from website processing."""

    url: str
    title: Optional[str] = None
    extracted_content: str = ""
    published_at: Optional[datetime] = None
    extraction_method: Literal["trafilatura", "jina"] = "trafilatura"
    extraction_status: Literal["success", "partial", "failed"] = "success"
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PastedTextExtractRequest(BaseModel):
    """Request payload for extracting and normalizing user-pasted text."""

    text: str = Field(
        ...,
        max_length=1_048_576,
        description="The raw text content submitted by the user.",
    )
    title: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional title or label for the source.",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Pasted text must not be empty or whitespace only.")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            trimmed = v.strip()
            if not trimmed:
                raise ValueError("Title must not be whitespace only if provided.")
            return trimmed
        return v


class PastedTextExtractionResult(BaseModel):
    """Structured extraction result from pasted text processing."""

    title: str = "Untitled Pasted Text"
    source_type: Literal["pasted_text"] = "pasted_text"
    extracted_content: str
    character_count: int
    word_count: int
    extraction_method: Literal["direct"] = "direct"
    extraction_status: Literal["success"] = "success"
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    def __await__(self):
        async def _identity():
            return self

        return _identity().__await__()


class DocumentExtractionResult(BaseModel):
    """Structured extraction result from document processing (PDF/DOCX)."""

    file_name: str
    file_type: Literal["pdf", "docx"]
    file_size_bytes: int
    title: str = "Untitled Document"
    source_type: Literal["document"] = "document"
    extracted_content: str
    character_count: int
    word_count: int
    page_count: Optional[int] = None
    extraction_method: Literal["pypdf", "python-docx"]
    extraction_status: Literal["success", "partial"] = "success"
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    def __await__(self):
        async def _identity():
            return self

        return _identity().__await__()


# =============================================================================
# PERSISTENCE & API SCHEMAS (Checkpoint 4.4.1)
# =============================================================================

ALLOWED_SOURCE_TYPES = {"website", "pasted_text", "document"}
ALLOWED_EXTRACTION_STATUSES = {"success", "partial", "failed"}


def make_content_preview(content: str, max_chars: int = 250) -> str:
    """Generates a truncated content preview capped at max_chars with '...' if longer.
    Preserves original whitespace, truncating only when necessary.
    """
    if not content:
        return ""
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "..."


class SourceResponse(BaseModel):
    """Full source representation including extracted content."""

    id: UUID
    research_id: UUID
    source_code: str = Field(..., pattern=r"^S[0-9]+$")
    title: str = "Untitled Source"
    url: Optional[str] = None
    source_type: Literal["website", "pasted_text", "document"]
    extracted_content: str = ""
    published_at: Optional[datetime] = None
    accessed_at: datetime
    extraction_status: Literal["success", "partial", "failed"] = "success"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SourcePreviewResponse(BaseModel):
    """Source list item representation exposing only content_preview (never full extracted_content)."""

    id: UUID
    research_id: UUID
    source_code: str = Field(..., pattern=r"^S[0-9]+$")
    title: str = "Untitled Source"
    url: Optional[str] = None
    source_type: Literal["website", "pasted_text", "document"]
    content_preview: str = Field(
        default="",
        description="Truncated preview of extracted content (maximum 250 characters + '...' if truncated).",
    )
    published_at: Optional[datetime] = None
    accessed_at: datetime
    extraction_status: Literal["success", "partial", "failed"] = "success"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SourceListResponse(BaseModel):
    """Schema representing paginated list of sources."""

    sources: List[SourcePreviewResponse]
    total: int
    limit: int = 50
    offset: int = 0

    model_config = ConfigDict(from_attributes=True)


class SourceEnvelope(BaseModel):
    """Standard API envelope for single source responses."""

    success: bool = True
    message: str = "Source retrieved successfully"
    data: SourceResponse


class SourceListEnvelope(BaseModel):
    """Standard API envelope for source listing responses."""

    success: bool = True
    message: str = "Sources retrieved successfully"
    data: SourceListResponse




