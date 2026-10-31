"""Database Repositories for ClarityX.

Provides clean, decoupled database abstractions on top of the Supabase client.
Separates raw database interactions from routes and business services,
standardizing error translation and preventing secret leakage.
"""

import logging
import re
from typing import Any, Dict, List, Optional
import anyio
from postgrest.exceptions import APIError

from app.core.exceptions import ClarityXException, DatabaseConnectionError
from app.database.supabase import get_supabase_client
from app.schemas.source import (
    ALLOWED_EXTRACTION_STATUSES,
    ALLOWED_SOURCE_TYPES,
    make_content_preview,
)


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


class SourceRepository(BaseRepository):
    """Repository managing source persistence, sequential numbering, and ownership."""

    async def verify_session_ownership(self, session_id: str, user_id: str) -> bool:
        """Verifies that the target research session exists and belongs to the authenticated user."""
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("research_sessions")
                .select("id")
                .eq("id", session_id)
                .eq("user_id", user_id)
                .execute()
            )
            return bool(response.data and len(response.data) > 0)
        except Exception as exc:
            self.handle_db_error("verify_session_ownership", exc)
            return False

    async def get_next_source_code(self, session_id: str) -> str:
        """Calculates the next available sequential source code (e.g., S1, S2, S3)."""
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("sources")
                .select("source_code")
                .eq("research_id", session_id)
                .execute()
            )
            existing_records = response.data or []
            numbers: List[int] = []
            for row in existing_records:
                code = str(row.get("source_code", "")).strip()
                match = re.match(r"^S([0-9]+)$", code)
                if match:
                    numbers.append(int(match.group(1)))

            next_num = max(numbers) + 1 if numbers else 1
            return f"S{next_num}"
        except Exception as exc:
            self.handle_db_error("get_next_source_code", exc)
            return "S1"

    async def create_source(
        self,
        session_id: str,
        user_id: str,
        source_type: str,
        extracted_content: str,
        title: str = "Untitled Source",
        url: Optional[str] = None,
        published_at: Optional[Any] = None,
        extraction_status: str = "success",
    ) -> Optional[Dict[str, Any]]:
        """Persists an extracted source with ownership verification and duplicate code retry."""
        # 1. Enforce ownership: session must belong to user
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            logger.warning(
                f"Unauthorized source creation attempt: session {session_id} not owned by user {user_id}"
            )
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        # 2. Validate input constraints
        if source_type not in ALLOWED_SOURCE_TYPES:
            raise ClarityXException(
                message=f"Invalid source_type '{source_type}'. Allowed types: {', '.join(sorted(ALLOWED_SOURCE_TYPES))}",
                status_code=400,
            )

        if extraction_status not in ALLOWED_EXTRACTION_STATUSES:
            raise ClarityXException(
                message=f"Invalid extraction_status '{extraction_status}'. Allowed statuses: {', '.join(sorted(ALLOWED_EXTRACTION_STATUSES))}",
                status_code=400,
            )

        safe_title = (title or "Untitled Source").strip()[:255] or "Untitled Source"
        safe_url = url.strip() if url and url.strip() else None
        safe_content = extracted_content or ""
        safe_published_at = (
            published_at.isoformat()
            if hasattr(published_at, "isoformat")
            else published_at
        )

        # 3. Optimistic insertion with bounded retry on unique-constraint conflict
        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES):
            source_code = await self.get_next_source_code(session_id)
            source_data = {
                "research_id": session_id,
                "source_code": source_code,
                "title": safe_title,
                "url": safe_url,
                "source_type": source_type,
                "extracted_content": safe_content,
                "published_at": safe_published_at,
                "extraction_status": extraction_status,
            }

            try:
                response = await anyio.to_thread.run_sync(
                    lambda: self.client.table("sources").insert(source_data).execute()
                )
                if response.data and len(response.data) > 0:
                    return response.data[0]
                return None
            except APIError as exc:
                err_msg = str(getattr(exc, "message", exc)).lower()
                err_code = str(getattr(exc, "code", ""))
                # Only retry actual unique-violation conflicts (SQLSTATE 23505 or constraint name)
                if (
                    err_code == "23505"
                    or "uq_sources_research_code" in err_msg
                    or "unique" in err_msg
                ):
                    logger.info(
                        f"Source code collision on {source_code} for session {session_id} "
                        f"(attempt {attempt + 1}/{MAX_RETRIES}); retrying allocation"
                    )
                    if attempt == MAX_RETRIES - 1:
                        raise ClarityXException(
                            message="Failed to allocate unique source code due to concurrent activity. Please retry.",
                            status_code=409,
                            detail="Exhausted maximum retry attempts to resolve unique source code collision.",
                        )
                    continue
                # Do NOT retry unrelated database errors
                self.handle_db_error("create_source", exc)
                return None
            except Exception as exc:
                self.handle_db_error("create_source", exc)
                return None

        return None

    async def list_sources(
        self,
        session_id: str,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Lists sources belonging to a user's session with truncated content previews (never full content)."""
        # 1. Enforce ownership: session must belong to user
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            logger.warning(
                f"Unauthorized source list attempt: session {session_id} not owned by user {user_id}"
            )
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        try:
            def _build_and_run():
                query = (
                    self.client.table("sources")
                    .select(
                        "id, research_id, source_code, title, url, source_type, extracted_content, published_at, accessed_at, extraction_status, created_at",
                        count="exact",
                    )
                    .eq("research_id", session_id)
                    .order("created_at", desc=False)
                    .range(offset, offset + limit - 1)
                )
                return query.execute()

            response = await anyio.to_thread.run_sync(_build_and_run)
            raw_sources = response.data or []
            total_count = response.count if response.count is not None else len(raw_sources)

            # Strip full extracted_content and replace with content_preview
            preview_sources = []
            for row in raw_sources:
                item = dict(row)
                full_content = item.pop("extracted_content", "") or ""
                item["content_preview"] = make_content_preview(full_content, max_chars=250)
                preview_sources.append(item)

            return {
                "sources": preview_sources,
                "total": total_count,
                "limit": limit,
                "offset": offset,
            }
        except Exception as exc:
            self.handle_db_error("list_sources", exc)
            return {"sources": [], "total": 0, "limit": limit, "offset": offset}

    async def get_source_by_id(
        self,
        session_id: str,
        source_id: str,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a single source (including full extracted_content) verifying session ownership."""
        # 1. Enforce ownership: session must belong to user
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            return None

        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("sources")
                .select("*")
                .eq("id", source_id)
                .eq("research_id", session_id)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as exc:
            self.handle_db_error("get_source_by_id", exc)
            return None

    async def delete_source(
        self,
        session_id: str,
        source_id: str,
        user_id: str,
    ) -> bool:
        """Deletes a source verifying session ownership and scoping to both session_id and source_id."""
        # 1. Enforce ownership: session must belong to user
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            return False

        try:
            existing = await self.get_source_by_id(session_id, source_id, user_id)
            if not existing:
                return False

            await anyio.to_thread.run_sync(
                lambda: self.client.table("sources")
                .delete()
                .eq("id", source_id)
                .eq("research_id", session_id)
                .execute()
            )
            return True
        except Exception as exc:
            self.handle_db_error("delete_source", exc)
            return False

