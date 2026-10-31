"""Database Repositories for ClarityX.

Provides clean, decoupled database abstractions on top of the Supabase client.
Separates raw database interactions from routes and business services,
standardizing error translation and preventing secret leakage.
"""

import logging
from typing import Any, Dict, List, Optional
from postgrest.exceptions import APIError

from app.core.exceptions import ClarityXException, DatabaseConnectionError
from app.database.supabase import get_supabase_client

logger = logging.getLogger("clarityx.repositories")


class BaseRepository:
    """Base repository handling client access and common error translation."""

    @property
    def client(self):
        """Retrieves the active Supabase client."""
        return get_supabase_client()

    def handle_db_error(self, operation: str, exc: Exception) -> None:
        """Translates PostgREST / database exceptions into clean application errors

        without leaking credentials or internal database traces.
        """
        logger.error(f"Database error during {operation}: {type(exc).__name__}", exc_info=True)
        if isinstance(exc, APIError):
            # APIError from PostgREST: clean status code and user-safe message
            raise ClarityXException(
                message=f"Database operation failed during {operation}.",
                status_code=400,
                detail=exc.message if hasattr(exc, "message") else "A database error occurred.",
            )
        raise DatabaseConnectionError(
            message=f"Unable to complete database operation ({operation}). Please try again later."
        )


class ProfileRepository(BaseRepository):
    """Repository managing user profile operations."""

    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a user profile by ID."""
        try:
            response = self.client.table("profiles").select("*").eq("id", user_id).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as exc:
            self.handle_db_error("get_profile_by_id", exc)
            return None

    async def update_profile(self, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Updates profile attributes for an existing user."""
        try:
            response = (
                self.client.table("profiles")
                .update(updates)
                .eq("id", user_id)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as exc:
            self.handle_db_error("update_profile", exc)
            return None


class ResearchRepository(BaseRepository):
    """Repository managing research sessions and related entities."""

    async def get_session_by_id(self, session_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a research session verifying user ownership."""
        try:
            response = (
                self.client.table("research_sessions")
                .select("*")
                .eq("id", session_id)
                .eq("user_id", user_id)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as exc:
            self.handle_db_error("get_session_by_id", exc)
            return None

    async def list_user_sessions(
        self, user_id: str, limit: int = 10, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Lists research sessions belonging to a user with pagination."""
        try:
            response = (
                self.client.table("research_sessions")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )
            return response.data or []
        except Exception as exc:
            self.handle_db_error("list_user_sessions", exc)
            return []

