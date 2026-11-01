"""Verification checklist management routes for ClarityX.

Provides authenticated endpoints for updating verification checklist items.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.exceptions import ClarityXException
from app.database.repositories import VerificationRepository
from app.dependencies.auth import get_current_user
from app.schemas.auth import AuthenticatedUser
from app.schemas.research import (
    VerificationItemEnvelope,
    VerificationItemResponse,
    VerificationStatusUpdate,
)

logger = logging.getLogger("clarityx.verification.routes")

router = APIRouter(prefix="/api/verification", tags=["Verification"])


def get_verification_repository() -> VerificationRepository:
    """Dependency provider returning a VerificationRepository instance."""
    return VerificationRepository()


def parse_and_validate_uuid(identifier: str, field_name: str = "verification item ID") -> UUID:
    """Validates that a path parameter string is a valid UUID."""
    try:
        return UUID(str(identifier).strip())
    except (ValueError, TypeError):
        raise ClarityXException(
            message=f"Invalid {field_name}",
            status_code=400,
            detail=f"The {field_name.replace(' ', '_')} must be a valid UUID format.",
        )


@router.patch(
    "/{item_id}",
    response_model=VerificationItemEnvelope,
    status_code=status.HTTP_200_OK,
    summary="Update Verification Item Status",
    description="Updates the completion status of a verification item, verifying session ownership.",
)
async def update_verification_item(
    item_id: str,
    payload: VerificationStatusUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: VerificationRepository = Depends(get_verification_repository),
) -> VerificationItemEnvelope:
    """Update the completion status of a verification item for the authenticated user.

    Validates item UUID, verifies session ownership, and updates status to
    'pending' or 'completed' while updating completed_at appropriately.
    """
    item_uuid = parse_and_validate_uuid(item_id)
    user_id_str = str(current_user.id)

    updated = await repo.update_item_status(
        item_id=str(item_uuid),
        user_id=user_id_str,
        status=payload.status,
    )

    if not updated:
        raise ClarityXException(
            message="Verification item not found",
            status_code=404,
            detail="The requested verification item was not found.",
        )

    return VerificationItemEnvelope(
        success=True,
        message="Verification item updated successfully",
        data=VerificationItemResponse.model_validate(updated),
    )

