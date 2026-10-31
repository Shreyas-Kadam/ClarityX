"""Authentication routes for ClarityX.

Provides endpoints for authenticated user profile retrieval and session management.
"""

import logging
from fastapi import APIRouter, Depends

from app.core.exceptions import ClarityXException
from app.database.repositories import ProfileRepository
from app.dependencies.auth import get_current_user
from app.schemas.auth import AuthenticatedUser, UserProfileResponse

logger = logging.getLogger("clarityx.auth.routes")

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def get_profile_repository() -> ProfileRepository:
    """Dependency provider returning a ProfileRepository instance."""
    return ProfileRepository()


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get Current User Profile",
    description="Retrieves the public profile belonging to the currently authenticated user.",
)
async def get_current_user_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> UserProfileResponse:
    """Returns the verified profile for the currently authenticated user.

    Identity is derived exclusively from the authenticated Supabase user session.
    No user ID can be injected via query parameters, request body, or arbitrary headers.

    If the user's profile record is missing from the database, it is automatically
    initialized from verified account metadata.
    """
    user_id_str = str(current_user.id)

    profile_data = await profile_repo.get_or_create_profile(
        user_id=user_id_str,
        email=current_user.email or "",
        full_name=current_user.full_name or "",
    )

    if profile_data is None:
        logger.error(f"Failed to retrieve or initialize profile for user {user_id_str}")
        raise ClarityXException(
            message="User profile not found",
            status_code=404,
            detail="The profile for the authenticated user could not be found or initialized.",
        )

    return UserProfileResponse.model_validate(profile_data)

