"""Pydantic schemas for research sessions."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.source import SourcePreviewResponse

ALLOWED_RESEARCH_STATUSES = {"pending", "processing", "completed", "failed"}


class ResearchSessionCreate(BaseModel):
    """Payload to create a new research session."""

    research_goal: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="The user's research objective or question.",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("research_goal")
    @classmethod
    def validate_research_goal(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Research goal must not be empty or whitespace only.")
        return trimmed


class ResearchSessionUpdate(BaseModel):
    """Payload to update an existing research session."""

    research_goal: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=5000,
        description="Updated research objective or question.",
    )
    status: Optional[str] = Field(
        default=None,
        description="Updated status: pending, processing, completed, or failed.",
    )
    summary: Optional[str] = Field(
        default=None,
        description="Summary of the analysed research session.",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("research_goal")
    @classmethod
    def validate_research_goal(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            trimmed = v.strip()
            if not trimmed:
                raise ValueError("Research goal must not be empty or whitespace only.")
            return trimmed
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if v not in ALLOWED_RESEARCH_STATUSES:
                raise ValueError(
                    f"Invalid status '{v}'. Allowed values: {', '.join(sorted(ALLOWED_RESEARCH_STATUSES))}"
                )
        return v


class ResearchSessionResponse(BaseModel):
    """Schema representing a research session record."""

    id: UUID
    user_id: UUID
    research_goal: str
    status: str
    summary: str = ""
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResearchSessionListResponse(BaseModel):
    """Schema representing paginated list of research sessions."""

    research_sessions: List[ResearchSessionResponse]
    total: int
    limit: int = 10
    offset: int = 0

    model_config = ConfigDict(from_attributes=True)


class ResearchSessionEnvelope(BaseModel):
    """Standard API envelope for single research session responses."""

    success: bool = True
    message: Optional[str] = None
    data: ResearchSessionResponse


class ResearchSessionListEnvelope(BaseModel):
    """Standard API envelope for list research session responses."""

    success: bool = True
    data: ResearchSessionListResponse


class DeleteResponse(BaseModel):
    """Standard API envelope for research deletion."""

    success: bool = True
    message: str = "Research deleted successfully"


class EvidenceReferenceResponse(BaseModel):
    """Schema representing a verified evidence quotation referencing a source."""

    id: UUID
    finding_id: Optional[UUID] = None
    source_id: UUID
    source_code: Optional[str] = None
    evidence_text: str
    evidence_type: str = "supporting"
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FindingResponse(BaseModel):
    """Schema representing an information gap finding with attached evidence references."""

    id: UUID
    research_id: Optional[UUID] = None
    category: str
    title: str
    description: str
    severity: str
    confidence: Optional[float] = None
    recommended_action: str = ""
    evidence_references: List[EvidenceReferenceResponse] = Field(default_factory=list)
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class VerificationItemResponse(BaseModel):
    """Schema representing an actionable verification task."""

    id: UUID
    research_id: Optional[UUID] = None
    finding_id: Optional[UUID] = None
    task: str
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UnresolvedQuestionResponse(BaseModel):
    """Schema representing a broad unresolved research question (finding_id = NULL)."""

    id: UUID
    task: str
    status: str = "pending"
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class VerificationStatusUpdate(BaseModel):
    """Payload to update the completion status of a verification item."""

    status: Literal["pending", "completed"]

    model_config = ConfigDict(extra="forbid")


class ResearchReportData(BaseModel):
    """Payload container for complete research report data."""

    research_id: UUID
    research_goal: str
    status: str
    summary: str = ""
    findings: List[FindingResponse] = Field(default_factory=list)
    sources: List[SourcePreviewResponse] = Field(default_factory=list)
    unresolved_questions: List[UnresolvedQuestionResponse] = Field(default_factory=list)
    verification_items: List[VerificationItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ResearchReportEnvelope(BaseModel):
    """Standard API envelope for complete research report."""

    success: bool = True
    message: Optional[str] = None
    data: ResearchReportData


class VerificationItemEnvelope(BaseModel):
    """Standard API envelope for single verification item responses."""

    success: bool = True
    message: Optional[str] = "Verification item updated successfully"
    data: VerificationItemResponse

