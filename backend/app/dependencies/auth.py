"""Authentication dependencies for ClarityX.

Provides token extraction and verification via Supabase Auth.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import Depends, Header

from app.core.exceptions import AuthenticationError
from app.database.supabase import get_supabase_client
from app.schemas.auth import AuthenticatedUser

logger = logging.getLogger("clarityx.auth")


def get_token_header(authorization: Optional[str] = Header(default=None)) -> str:
    """Extracts and validates the Bearer token from the Authorization header.

    Raises:
        AuthenticationError: If the header is missing, malformed, or empty.
    """
    if not authorization:
        raise AuthenticationError(
            message="Missing Authorization header",
            detail="Authorization header with Bearer token is required.",
        )

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AuthenticationError(
            message="Malformed Authorization header",
            detail="Authorization header must follow the 'Bearer <token>' format.",
        )

    return parts[1].strip()


def get_current_user(
    token: str = Depends(get_token_header),
) -> AuthenticatedUser:
    """Verifies a Supabase access token and returns the AuthenticatedUser model.

    Uses the official Supabase Auth client to verify the token directly against
    Supabase rather than decoding an unverified JWT locally.

    Raises:
        AuthenticationError: If the token is invalid, expired, or rejected.
    """
    client = get_supabase_client()

    try:
        user_response = client.auth.get_user(token)
    except Exception as exc:
        # Never log or expose the raw token or internal exception details
        logger.warning(
            f"Supabase auth token verification rejected: {type(exc).__name__}"
        )
        raise AuthenticationError(
            message="Invalid or expired authentication token",
            detail="The provided authentication token could not be verified.",
        ) from None

    if not user_response or not getattr(user_response, "user", None):
        logger.warning("Supabase auth returned empty user object")
        raise AuthenticationError(
            message="Invalid or expired authentication token",
            detail="The provided authentication token is invalid.",
        )

    user = user_response.user
    user_id = getattr(user, "id", None)
    if not user_id:
        logger.warning("Supabase user record missing id")
        raise AuthenticationError(
            message="Invalid authentication token",
            detail="User identifier missing from authenticated token.",
        )

    try:
        user_uuid = UUID(str(user_id))
    except (ValueError, TypeError):
        logger.warning("Supabase user id is not a valid UUID")
        raise AuthenticationError(
            message="Invalid user identifier",
            detail="User identifier in authentication token is not a valid UUID.",
        )

    user_metadata = getattr(user, "user_metadata", {}) or {}
    email = getattr(user, "email", None)
    full_name = user_metadata.get("full_name") or user_metadata.get("name") or None

    return AuthenticatedUser(
        id=user_uuid,
        email=email,
        full_name=full_name,
        metadata=user_metadata,
    )

