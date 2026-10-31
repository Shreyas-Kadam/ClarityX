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

