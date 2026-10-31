"""Database Repositories for ClarityX.

Provides clean, decoupled database abstractions on top of the Supabase client.
Separates raw database interactions from routes and business services,
standardizing error translation and preventing secret leakage.
"""

import logging
from typing import Any, Dict, List, Optional
import anyio
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
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("profiles").select("*").eq("id", user_id).execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as exc:
            self.handle_db_error("get_profile_by_id", exc)
            return None

    async def create_profile(
        self, user_id: str, email: str = "", full_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Creates a new user profile record."""
        try:
            profile_data = {
                "id": user_id,
                "email": email or "",
                "full_name": full_name or "",
            }
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("profiles").insert(profile_data).execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as exc:
            self.handle_db_error("create_profile", exc)
            return None

    async def get_or_create_profile(
        self, user_id: str, email: str = "", full_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a user profile, safely creating it if absent.

        Handles concurrent creation conflicts by retrying retrieval.
        """
        # 1. Attempt to retrieve the existing profile
        profile = await self.get_by_id(user_id)
        if profile is not None:
            return profile

        # 2. If missing, attempt creation
        try:
            profile = await self.create_profile(
                user_id=user_id, email=email, full_name=full_name
            )
            if profile is not None:
                return profile
        except DatabaseConnectionError:
            raise
        except ClarityXException as exc:
            # Possible duplicate key conflict from concurrent creation / trigger
            logger.info(
                f"Profile creation conflict for user {user_id}: {exc.message}; retrying retrieval"
            )
        except Exception as exc:
            logger.warning(
                f"Unexpected error during profile creation for {user_id}: {type(exc).__name__}; retrying retrieval"
            )

        # 3. Retrieve again to handle concurrent creation
        return await self.get_by_id(user_id)

    async def update_profile(self, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Updates profile attributes for an existing user."""
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("profiles")
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

    async def create_session(
        self, user_id: str, research_goal: str
    ) -> Optional[Dict[str, Any]]:
        """Creates a new research session assigned strictly to the authenticated user."""
        try:
            session_data = {
                "user_id": user_id,
                "research_goal": research_goal.strip(),
                "status": "pending",
                "summary": "",
            }
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("research_sessions")
                .insert(session_data)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as exc:
            self.handle_db_error("create_session", exc)
            return None

    async def get_session_by_id(self, session_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a research session verifying user ownership."""
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("research_sessions")
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
        self,
        user_id: str,
        limit: int = 10,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lists research sessions belonging to a user with pagination and optional status filter."""
        try:
            def _build_and_run():
                query = (
                    self.client.table("research_sessions")
                    .select("*")
                    .eq("user_id", user_id)
                )
                if status:
                    query = query.eq("status", status)
                query = query.order("created_at", desc=True).range(
                    offset, offset + limit - 1
                )
                return query.execute()

            response = await anyio.to_thread.run_sync(_build_and_run)
            return response.data or []
        except Exception as exc:
            self.handle_db_error("list_user_sessions", exc)
            return []

    async def count_user_sessions(
        self, user_id: str, status: Optional[str] = None
    ) -> int:
        """Counts total research sessions belonging to a user with optional status filter."""
        try:
            def _build_and_run():
                query = (
                    self.client.table("research_sessions")
                    .select("id", count="exact")
                    .eq("user_id", user_id)
                )
                if status:
                    query = query.eq("status", status)
                return query.execute()

            response = await anyio.to_thread.run_sync(_build_and_run)
            return response.count or 0
        except Exception as exc:
            logger.warning(f"Error counting user sessions: {type(exc).__name__}")
            return 0

    async def update_session(
        self, session_id: str, user_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Updates a research session verifying user ownership."""
        try:
            existing = await self.get_session_by_id(session_id, user_id)
            if not existing:
                return None

            safe_updates = {
                k: v
                for k, v in updates.items()
                if k in ("research_goal", "status", "summary") and v is not None
            }
            if not safe_updates:
                return existing

            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("research_sessions")
                .update(safe_updates)
                .eq("id", session_id)
                .eq("user_id", user_id)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
            return await self.get_session_by_id(session_id, user_id)
        except Exception as exc:
            self.handle_db_error("update_session", exc)
            return None

    async def delete_session(self, session_id: str, user_id: str) -> bool:
        """Deletes a research session verifying user ownership."""
        try:
            existing = await self.get_session_by_id(session_id, user_id)
            if not existing:
                return False

            await anyio.to_thread.run_sync(
                lambda: self.client.table("research_sessions")
                .delete()
                .eq("id", session_id)
                .eq("user_id", user_id)
                .execute()
            )
            return True
        except Exception as exc:
            self.handle_db_error("delete_session", exc)
            return False
