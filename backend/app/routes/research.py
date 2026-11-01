"""Research session management routes for ClarityX.

Provides authenticated CRUD operations for user research sessions.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.exceptions import AIProviderError, ClarityXException
from app.database.repositories import ResearchRepository, SourceRepository
from app.dependencies.auth import get_current_user
from app.schemas.analysis import SourceAnalysisInput
from app.schemas.auth import AuthenticatedUser
from app.schemas.research import (
    ALLOWED_RESEARCH_STATUSES,
    DeleteResponse,
    ResearchReportEnvelope,
    ResearchSessionCreate,
    ResearchSessionEnvelope,
    ResearchSessionListEnvelope,
    ResearchSessionListResponse,
    ResearchSessionResponse,
    ResearchSessionUpdate,
)
from app.services.ai_service import AIService
from app.services.analysis_persistence_service import AnalysisPersistenceService

logger = logging.getLogger("clarityx.research.routes")

router = APIRouter(prefix="/api/research", tags=["Research Sessions"])


def get_research_repository() -> ResearchRepository:
    """Dependency provider returning a ResearchRepository instance."""
    return ResearchRepository()


def get_source_repository() -> SourceRepository:
    """Dependency provider returning a SourceRepository instance."""
    return SourceRepository()


def get_ai_service() -> AIService:
    """Dependency provider returning an AIService instance."""
    return AIService()


def get_analysis_persistence_service() -> AnalysisPersistenceService:
    """Dependency provider returning an AnalysisPersistenceService instance."""
    return AnalysisPersistenceService()


def parse_and_validate_uuid(identifier: str) -> UUID:
    """Validates that a path parameter string is a valid UUID."""
    try:
        return UUID(str(identifier).strip())
    except (ValueError, TypeError):
        raise ClarityXException(
            message="Invalid research session ID",
            status_code=400,
            detail="The research_id must be a valid UUID format.",
        )


@router.post(
    "",
    response_model=ResearchSessionEnvelope,
    status_code=status.HTTP_201_CREATED,
    summary="Create Research Session",
    description="Creates a new research session assigned strictly to the authenticated user.",
)
async def create_research_session(
    payload: ResearchSessionCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: ResearchRepository = Depends(get_research_repository),
) -> ResearchSessionEnvelope:
    """Creates a new research session.

    The user_id is assigned exclusively from the verified auth session.
    """
    user_id_str = str(current_user.id)
    session = await repo.create_session(
        user_id=user_id_str,
        research_goal=payload.research_goal,
    )

    if not session:
        logger.error(f"Failed to create research session for user {user_id_str}")
        raise ClarityXException(
            message="Failed to create research session",
            status_code=500,
            detail="The database was unable to initialize the research session.",
        )

    return ResearchSessionEnvelope(
        success=True,
        message="Research session created successfully",
        data=ResearchSessionResponse.model_validate(session),
    )


@router.get(
    "",
    response_model=ResearchSessionListEnvelope,
    summary="List Research Sessions",
    description="Lists previous research sessions belonging to the authenticated user.",
)
async def list_research_sessions(
    limit: int = Query(default=10, ge=1, le=100, description="Max records to return."),
    offset: int = Query(default=0, ge=0, description="Records to skip."),
    status: Optional[str] = Query(default=None, description="Optional status filter."),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: ResearchRepository = Depends(get_research_repository),
) -> ResearchSessionListEnvelope:
    """Lists research sessions with pagination, strictly scoped to the authenticated user."""
    if status and status not in ALLOWED_RESEARCH_STATUSES:
        raise ClarityXException(
            message="Invalid status filter",
            status_code=400,
            detail=f"Status filter must be one of: {', '.join(sorted(ALLOWED_RESEARCH_STATUSES))}",
        )

    user_id_str = str(current_user.id)
    sessions = await repo.list_user_sessions(
        user_id=user_id_str,
        limit=limit,
        offset=offset,
        status=status,
    )
    total = await repo.count_user_sessions(
        user_id=user_id_str,
        status=status,
    )

    return ResearchSessionListEnvelope(
        success=True,
        data=ResearchSessionListResponse(
            research_sessions=[ResearchSessionResponse.model_validate(s) for s in sessions],
            total=total,
            limit=limit,
            offset=offset,
        ),
    )


@router.get(
    "/{research_id}",
    response_model=ResearchReportEnvelope,
    summary="Get Research Report",
    description="Retrieves the complete research report including findings, evidence, verification items, unresolved questions, and sources, verifying user ownership.",
)
async def get_research_session(
    research_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: ResearchRepository = Depends(get_research_repository),
) -> ResearchReportEnvelope:
    """Retrieves a complete research report by research ID.

    If the session does not exist or belongs to another user, returns HTTP 404.
    """
    session_uuid = parse_and_validate_uuid(research_id)
    user_id_str = str(current_user.id)

    report_data = await repo.get_research_report(
        session_id=str(session_uuid),
        user_id=user_id_str,
    )

    if not report_data:
        raise ClarityXException(
            message="Research session not found",
            status_code=404,
            detail="The requested research session was not found.",
        )

    return ResearchReportEnvelope(
        success=True,
        data=report_data,
    )


@router.patch(
    "/{research_id}",
    response_model=ResearchSessionEnvelope,
    summary="Update Research Session",
    description="Updates a research session verifying user ownership.",
)
async def update_research_session(
    research_id: str,
    payload: ResearchSessionUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: ResearchRepository = Depends(get_research_repository),
) -> ResearchSessionEnvelope:
    """Updates research session fields (research_goal, status, summary).

    If the session does not exist or belongs to another user, returns HTTP 404.
    """
    session_uuid = parse_and_validate_uuid(research_id)
    user_id_str = str(current_user.id)

    updated = await repo.update_session(
        session_id=str(session_uuid),
        user_id=user_id_str,
        updates=payload.model_dump(exclude_unset=True),
    )

    if not updated:
        raise ClarityXException(
            message="Research session not found",
            status_code=404,
            detail="The requested research session was not found.",
        )

    return ResearchSessionEnvelope(
        success=True,
        message="Research session updated successfully",
        data=ResearchSessionResponse.model_validate(updated),
    )


@router.delete(
    "/{research_id}",
    response_model=DeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete Research Session",
    description="Deletes a research session and its dependent records verifying ownership.",
)
async def delete_research_session(
    research_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: ResearchRepository = Depends(get_research_repository),
) -> DeleteResponse:
    """Deletes a research session.

    If the session does not exist or belongs to another user, returns HTTP 404.
    """
    session_uuid = parse_and_validate_uuid(research_id)
    user_id_str = str(current_user.id)

    deleted = await repo.delete_session(
        session_id=str(session_uuid),
        user_id=user_id_str,
    )

    if not deleted:
        raise ClarityXException(
            message="Research session not found",
            status_code=404,
            detail="The requested research session was not found.",
        )

    return DeleteResponse(
        success=True,
        message="Research deleted successfully",
    )


@router.post(
    "/{research_id}/analyze",
    response_model=ResearchReportEnvelope,
    status_code=status.HTTP_200_OK,
    summary="Analyze Research Session",
    description="Executes AI information gap analysis on research session sources and atomically persists findings.",
)
async def analyze_research_session(
    research_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    research_repo: ResearchRepository = Depends(get_research_repository),
    source_repo: SourceRepository = Depends(get_source_repository),
    ai_service: AIService = Depends(get_ai_service),
    persistence_service: AnalysisPersistenceService = Depends(get_analysis_persistence_service),
) -> ResearchReportEnvelope:
    """Orchestrates AI analysis and atomic persistence for a research session."""
    # 1. Validate research_id UUID
    session_uuid = parse_and_validate_uuid(research_id)
    session_id_str = str(session_uuid)
    user_id_str = str(current_user.id)

    # 2. Retrieve research session verifying user ownership
    session = await research_repo.get_session_by_id(
        session_id=session_id_str,
        user_id=user_id_str,
    )
    if not session:
        raise ClarityXException(
            message="Research session not found",
            status_code=404,
            detail="The requested research session was not found.",
        )

    # 3. Check AI service configuration upfront
    if not ai_service.settings.is_ai_configured or not getattr(ai_service, "client", None):
        raise AIProviderError(
            message="AI service is not configured. OPENROUTER_API_KEY is required.",
            status_code=503,
            detail="OpenRouter credentials are missing or empty in configuration.",
        )

    # 4. Retrieve raw sources with full extracted content
    raw_sources = await source_repo.get_raw_sources_by_session(
        session_id=session_id_str,
        user_id=user_id_str,
    )

    # 5. Filter usable sources (non-failed extraction, non-empty content)
    usable_sources = [
        s
        for s in raw_sources
        if s.get("extraction_status") != "failed" and bool((s.get("extracted_content") or "").strip())
    ]

    if not usable_sources:
        if not raw_sources:
            detail_msg = "The research session has no sources. Add at least one source before running analysis."
        else:
            detail_msg = "All sources in this session failed extraction or have empty content. Add at least one valid source with readable content before running analysis."
        raise ClarityXException(
            message="Insufficient source content for analysis",
            status_code=400,
            detail=detail_msg,
        )

    # 6. Convert to SourceAnalysisInput schema (preserving source_code, title, url, extracted_content)
    sources_input = [
        SourceAnalysisInput(
            source_code=s["source_code"],
            title=s.get("title") or "Untitled Source",
            source_type=s.get("source_type", "website"),
            url=s.get("url"),
            extracted_content=s.get("extracted_content") or "",
        )
        for s in usable_sources
    ]

    # 7. Execute AI analysis (includes prompt-injection boundary and evidence grounding)
    research_goal = (session.get("research_goal") or "").strip()
    analysis_result = await ai_service.analyze(
        research_goal=research_goal,
        sources=sources_input,
    )

    # 8. Atomically persist findings, evidence, and verification checklist
    report_data = await persistence_service.persist_analysis(
        session_id=session_id_str,
        user_id=user_id_str,
        analysis=analysis_result,
    )

    # 9. Return complete envelope
    return ResearchReportEnvelope(
        success=True,
        message="Research analysis completed successfully",
        data=report_data,
    )

