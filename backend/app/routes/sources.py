"""Source management routes for ClarityX.

Provides authenticated endpoints for extracting and persisting sources
(websites, pasted text, and uploaded PDF/DOCX documents), as well as
listing, retrieving, and deleting research sources.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.core.config import get_settings
from app.core.exceptions import (
    ClarityXException,
    ContentSizeExceededError,
    ExtractionError,
)
from app.database.repositories import SourceRepository
from app.dependencies.auth import get_current_user
from app.schemas.auth import AuthenticatedUser
from app.schemas.source import (
    PastedTextExtractRequest,
    SourceDeleteResponse,
    SourceEnvelope,
    SourceListEnvelope,
    SourceListResponse,
    SourceResponse,
    WebsiteExtractRequest,
)
from app.services.extraction_service import (
    extract_document,
    extract_pasted_text,
    extract_website_content,
)

logger = logging.getLogger("clarityx.sources.routes")
settings = get_settings()

router = APIRouter(prefix="/api/research/{research_id}/sources", tags=["Sources"])


def get_source_repository() -> SourceRepository:
    """Dependency provider returning a SourceRepository instance."""
    return SourceRepository()


def parse_and_validate_uuid(identifier: str, field_name: str = "research session ID") -> UUID:
    """Validates that a path parameter string is a valid UUID."""
    try:
        return UUID(str(identifier).strip())
    except (ValueError, TypeError):
        raise ClarityXException(
            message=f"Invalid {field_name}",
            status_code=400,
            detail=f"The {field_name.replace(' ', '_')} must be a valid UUID format.",
        )


@router.post(
    "/website",
    response_model=SourceEnvelope,
    status_code=status.HTTP_201_CREATED,
    summary="Add Website Source",
    description="Extracts content from a target website URL and persists it to the research session.",
)
async def add_website_source(
    research_id: str,
    payload: WebsiteExtractRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: SourceRepository = Depends(get_source_repository),
) -> SourceEnvelope:
    """Extracts website content and persists the source record."""
    session_uuid = parse_and_validate_uuid(research_id, "research session ID")
    user_id_str = str(current_user.id)

    # 1. Perform website extraction
    extraction_result = await extract_website_content(str(payload.url))

    # 2. Reject failed or empty extraction
    if (
        extraction_result.extraction_status == "failed"
        or not extraction_result.extracted_content
        or not extraction_result.extracted_content.strip()
    ):
        raise ExtractionError(
            message="Unable to extract meaningful readable content from the requested website.",
            detail=extraction_result.error_message or "Extraction failed to produce usable content.",
            status_code=422,
        )

    # 3. Persist through repository (enforces ownership and sequential code allocation)
    created_source = await repo.create_source(
        session_id=str(session_uuid),
        user_id=user_id_str,
        source_type="website",
        extracted_content=extraction_result.extracted_content,
        title=extraction_result.title or "Untitled Source",
        url=extraction_result.url,
        published_at=extraction_result.published_at,
        extraction_status=extraction_result.extraction_status,
    )

    if not created_source:
        raise ClarityXException(
            message="Failed to persist website source",
            status_code=500,
            detail="The database was unable to create the source record.",
        )

    return SourceEnvelope(
        success=True,
        message="Website source extracted and persisted successfully",
        data=SourceResponse.model_validate(created_source),
    )


@router.post(
    "/pasted-text",
    response_model=SourceEnvelope,
    status_code=status.HTTP_201_CREATED,
    summary="Add Pasted Text Source",
    description="Sanitizes, normalizes, and persists user-submitted text to the research session.",
)
async def add_pasted_text_source(
    research_id: str,
    payload: PastedTextExtractRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: SourceRepository = Depends(get_source_repository),
) -> SourceEnvelope:
    """Extracts pasted text and persists the source record."""
    session_uuid = parse_and_validate_uuid(research_id, "research session ID")
    user_id_str = str(current_user.id)

    # 1. Perform pasted text sanitization and extraction
    extraction_result = extract_pasted_text(payload.text, title=payload.title)

    # 2. Reject failed or empty extraction
    if (
        extraction_result.extraction_status == "failed"
        or not extraction_result.extracted_content
        or not extraction_result.extracted_content.strip()
    ):
        raise ExtractionError(
            message="Unable to process pasted text.",
            detail=extraction_result.error_message or "Pasted text contains no readable content.",
            status_code=422,
        )

    # 3. Persist through repository
    created_source = await repo.create_source(
        session_id=str(session_uuid),
        user_id=user_id_str,
        source_type="pasted_text",
        extracted_content=extraction_result.extracted_content,
        title=extraction_result.title or "Untitled Pasted Text",
        url=None,
        published_at=None,
        extraction_status=extraction_result.extraction_status,
    )

    if not created_source:
        raise ClarityXException(
            message="Failed to persist pasted text source",
            status_code=500,
            detail="The database was unable to create the source record.",
        )

    return SourceEnvelope(
        success=True,
        message="Pasted text source persisted successfully",
        data=SourceResponse.model_validate(created_source),
    )


@router.post(
    "/document",
    response_model=SourceEnvelope,
    status_code=status.HTTP_201_CREATED,
    summary="Add Document Source",
    description="Extracts content from an uploaded PDF or DOCX file and persists it to the research session.",
)
async def add_document_source(
    research_id: str,
    file: UploadFile = File(..., description="PDF or DOCX document file to extract."),
    title: Optional[str] = Form(default=None, description="Optional title override."),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: SourceRepository = Depends(get_source_repository),
) -> SourceEnvelope:
    """Extracts content from an uploaded PDF or DOCX file and persists the source record."""
    session_uuid = parse_and_validate_uuid(research_id, "research session ID")
    user_id_str = str(current_user.id)

    max_size = settings.MAX_DOCUMENT_FILE_SIZE
    chunk_size = 64 * 1024  # 64 KB chunks
    buffer = bytearray()

    # 1. Read uploaded file in chunks and enforce MAX_DOCUMENT_FILE_SIZE on actual bytes read
    try:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            buffer.extend(chunk)
            if len(buffer) > max_size:
                raise ContentSizeExceededError(
                    message=f"Uploaded document exceeds maximum allowable limit of {max_size} bytes (10 MB).",
                    detail=f"Uploaded size exceeded {max_size} bytes limit.",
                )
    finally:
        await file.close()

    file_bytes = bytes(buffer)
    raw_filename = file.filename or "unknown"

    # 2. Perform document extraction
    extraction_result = extract_document(
        file_bytes=file_bytes,
        filename=raw_filename,
        title=title,
    )

    # 3. Reject failed or empty extraction
    if (
        extraction_result.extraction_status == "failed"
        or not extraction_result.extracted_content
        or not extraction_result.extracted_content.strip()
    ):
        raise ExtractionError(
            message="Unable to extract meaningful readable content from the uploaded document.",
            detail=extraction_result.error_message or "Document contains no readable text.",
            status_code=422,
        )

    # 4. Persist through repository
    created_source = await repo.create_source(
        session_id=str(session_uuid),
        user_id=user_id_str,
        source_type="document",
        extracted_content=extraction_result.extracted_content,
        title=extraction_result.title,
        url=None,
        published_at=None,
        extraction_status=extraction_result.extraction_status,
    )

    if not created_source:
        raise ClarityXException(
            message="Failed to persist document source",
            status_code=500,
            detail="The database was unable to create the source record.",
        )

    return SourceEnvelope(
        success=True,
        message="Document source extracted and persisted successfully",
        data=SourceResponse.model_validate(created_source),
    )


@router.get(
    "",
    response_model=SourceListEnvelope,
    summary="List Sources",
    description="Lists sources belonging to a research session with content previews only (never full content).",
)
async def list_sources(
    research_id: str,
    limit: int = Query(default=50, ge=1, le=100, description="Max sources to return."),
    offset: int = Query(default=0, ge=0, description="Sources to skip."),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: SourceRepository = Depends(get_source_repository),
) -> SourceListEnvelope:
    """Lists sources with pagination and content previews."""
    session_uuid = parse_and_validate_uuid(research_id, "research session ID")
    user_id_str = str(current_user.id)

    result = await repo.list_sources(
        session_id=str(session_uuid),
        user_id=user_id_str,
        limit=limit,
        offset=offset,
    )

    return SourceListEnvelope(
        success=True,
        message="Sources retrieved successfully",
        data=SourceListResponse.model_validate(result),
    )


@router.get(
    "/{source_id}",
    response_model=SourceEnvelope,
    summary="Get Source",
    description="Retrieves a single source with its full extracted content, verifying research ownership.",
)
async def get_source(
    research_id: str,
    source_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: SourceRepository = Depends(get_source_repository),
) -> SourceEnvelope:
    """Retrieves a single source by ID including full extracted content."""
    session_uuid = parse_and_validate_uuid(research_id, "research session ID")
    source_uuid = parse_and_validate_uuid(source_id, "source ID")
    user_id_str = str(current_user.id)

    source = await repo.get_source_by_id(
        session_id=str(session_uuid),
        source_id=str(source_uuid),
        user_id=user_id_str,
    )

    if not source:
        raise ClarityXException(
            message="Source not found or unauthorized",
            status_code=404,
            detail="The requested source does not exist or does not belong to the research session.",
        )

    return SourceEnvelope(
        success=True,
        message="Source retrieved successfully",
        data=SourceResponse.model_validate(source),
    )


@router.delete(
    "/{source_id}",
    response_model=SourceDeleteResponse,
    summary="Delete Source",
    description="Deletes a source, verifying research session ownership.",
)
async def delete_source(
    research_id: str,
    source_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: SourceRepository = Depends(get_source_repository),
) -> SourceDeleteResponse:
    """Deletes a source by ID."""
    session_uuid = parse_and_validate_uuid(research_id, "research session ID")
    source_uuid = parse_and_validate_uuid(source_id, "source ID")
    user_id_str = str(current_user.id)

    success = await repo.delete_source(
        session_id=str(session_uuid),
        source_id=str(source_uuid),
        user_id=user_id_str,
    )

    if not success:
        raise ClarityXException(
            message="Source not found or unauthorized",
            status_code=404,
            detail="The requested source does not exist or does not belong to the research session.",
        )

    return SourceDeleteResponse(
        success=True,
        message="Source deleted successfully",
    )

