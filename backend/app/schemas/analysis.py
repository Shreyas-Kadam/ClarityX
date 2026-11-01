"""Pydantic schemas for AI-assisted information gap detection (Phase 6).

Defines structured models for OpenRouter AI structured output parsing,
evidence grounding, and prompt construction.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

# Constants for strict domain validation
ALLOWED_FINDING_CATEGORIES = ("missing", "outdated", "conflicting", "unverified")
ALLOWED_EVIDENCE_TYPES = ("supporting", "contradicting", "contextual")
ALLOWED_SEVERITIES = ("low", "medium", "high")


class SourceAnalysisInput(BaseModel):
    """Source input payload supplied to the AI analysis service."""

    source_code: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Unique sequential source code (e.g. S1, S2).",
    )
    title: str = Field(
        default="Untitled Source",
        max_length=255,
        description="Title or heading of the source.",
    )
    source_type: str = Field(
        ...,
        description="Source type: website, pasted_text, or document.",
    )
    url: Optional[str] = Field(
        default=None,
        max_length=2048,
        description="Source URL when available.",
    )
    extracted_content: str = Field(
        default="",
        description="Raw extracted text content from the source.",
    )

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class LLMEvidenceItem(BaseModel):
    """Evidence citation connecting a finding to a source excerpt."""

    source_code: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Source code identifier (e.g. S1, S2) corresponding to the cited source.",
    )
    quote: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Verbatim text quotation from the source extracted content.",
    )
    evidence_type: Literal["supporting", "contradicting", "contextual"] = Field(
        default="supporting",
        description="Role of this evidence excerpt relative to the finding.",
    )

    model_config = ConfigDict(extra="ignore")


class LLMFindingItem(BaseModel):
    """An information gap finding detected by the AI model."""

    category: Literal["missing", "outdated", "conflicting", "unverified"] = Field(
        ...,
        description="Strict classification of the information gap.",
    )
    title: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Short, descriptive title of the information gap.",
    )
    description: str = Field(
        ...,
        min_length=5,
        max_length=4000,
        description="Detailed analytical explanation of what was found or missing.",
    )
    severity: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Assessed severity impact of this information gap.",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Model self-reported confidence score between 0.0 and 1.0 (nullable).",
    )
    recommended_action: str = Field(
        default="",
        max_length=2000,
        description="Analytical advice on what the user should verify or investigate next.",
    )
    evidence: List[LLMEvidenceItem] = Field(
        default_factory=list,
        max_length=10,
        description="List of verified source quotations supporting or contradicting this finding.",
    )

    model_config = ConfigDict(extra="ignore")


class LLMVerificationItem(BaseModel):
    """A checklist task or broader unresolved research question."""

    task: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Actionable verification task or research question.",
    )
    is_general_unresolved_question: bool = Field(
        default=False,
        description="True if general unresolved question (finding_id=NULL); False if tied to a specific finding.",
    )
    related_finding_title: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional title of the related finding if this task is finding-specific.",
    )

    model_config = ConfigDict(extra="ignore")


class LLMAnalysisResponse(BaseModel):
    """Complete structured response produced by the AI analysis service."""

    summary: str = Field(
        ...,
        min_length=10,
        max_length=8000,
        description="Executive summary of the research goal, findings, and information gaps.",
    )
    findings: List[LLMFindingItem] = Field(
        default_factory=list,
        max_length=30,
        description="List of detected information gaps across the four categories.",
    )
    unresolved_questions: List[LLMVerificationItem] = Field(
        default_factory=list,
        max_length=30,
        description="General unresolved research questions not tied to a specific finding.",
    )
    verification_checklist: List[LLMVerificationItem] = Field(
        default_factory=list,
        max_length=30,
        description="Interactive checklist items and unresolved research questions.",
    )

    model_config = ConfigDict(extra="ignore")

