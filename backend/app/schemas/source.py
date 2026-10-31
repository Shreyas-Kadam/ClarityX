"""Pydantic schemas for source extraction."""

from datetime import datetime
from typing import Literal, Optional
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


