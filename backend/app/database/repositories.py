"""Database Repositories for ClarityX.

Provides clean, decoupled database abstractions on top of the Supabase client.
Separates raw database interactions from routes and business services,
standardizing error translation and preventing secret leakage.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import anyio
from postgrest.exceptions import APIError

from app.core.exceptions import ClarityXException, DatabaseConnectionError
from app.database.supabase import get_supabase_client
from app.schemas.analysis import (
    ALLOWED_EVIDENCE_TYPES,
    ALLOWED_FINDING_CATEGORIES,
    ALLOWED_SEVERITIES,
    LLMVerificationItem,
)
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

    async def count_sources(self, session_id: str) -> int:
        """Counts total sources associated with a research session."""
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("sources")
                .select("id", count="exact")
                .eq("research_id", session_id)
                .execute()
            )
            if response.count is not None and isinstance(response.count, int):
                return response.count
            data = getattr(response, "data", None)
            return len(data) if data and isinstance(data, list) else 0
        except Exception as exc:
            self.handle_db_error("count_sources", exc)
            return 0

    async def get_session_urls(self, session_id: str) -> List[str]:
        """Retrieves all non-null source URLs associated with a research session."""
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("sources")
                .select("url")
                .eq("research_id", session_id)
                .execute()
            )
            rows = response.data or []
            return [str(row["url"]).strip() for row in rows if row.get("url")]
        except Exception as exc:
            self.handle_db_error("get_session_urls", exc)
            return []

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

        # 2. Enforce session source capacity (hard limit: 5 sources per research session)
        current_count = await self.count_sources(session_id)
        if current_count >= 5:
            raise ClarityXException(
                message="Source capacity reached",
                status_code=400,
                detail="Research session has reached the maximum capacity of 5 sources.",
            )

        # 3. Validate input constraints
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

                if "source capacity limit reached" in err_msg:
                    raise ClarityXException(
                        message="Source capacity reached",
                        status_code=400,
                        detail="Research session has reached the maximum capacity of 5 sources.",
                    )

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

    async def get_raw_sources_by_session(
        self,
        session_id: str,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """Retrieves raw sources including full extracted_content for AI analysis,
        verifying session ownership and ordering deterministically by source_code ascending.
        """
        # 1. Enforce ownership: session must belong to user
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            logger.warning(
                f"Unauthorized raw source access attempt: session {session_id} not owned by user {user_id}"
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
                        "id, research_id, source_code, title, url, source_type, "
                        "extracted_content, published_at, accessed_at, extraction_status, created_at"
                    )
                    .eq("research_id", session_id)
                    .order("source_code", desc=False)
                )
                return query.execute()

            response = await anyio.to_thread.run_sync(_build_and_run)
            return response.data or []
        except Exception as exc:
            self.handle_db_error("get_raw_sources_by_session", exc)
            return []


class FindingRepository(BaseRepository):
    """Repository managing information gap findings."""

    async def create_finding(
        self,
        session_id: str,
        user_id: str,
        category: str,
        title: str,
        description: str,
        severity: str = "medium",
        confidence: Optional[float] = None,
        recommended_action: str = "",
    ) -> Dict[str, Any]:
        """Creates a single finding verifying session ownership and schema constraints."""
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            logger.warning(
                "Unauthorized finding creation attempt for session %s by user %s",
                session_id,
                user_id,
            )
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        if category not in ALLOWED_FINDING_CATEGORIES:
            raise ClarityXException(
                message=f"Invalid category '{category}'. Allowed categories: {', '.join(sorted(ALLOWED_FINDING_CATEGORIES))}",
                status_code=400,
            )

        if severity not in ALLOWED_SEVERITIES:
            raise ClarityXException(
                message=f"Invalid severity '{severity}'. Allowed severities: {', '.join(sorted(ALLOWED_SEVERITIES))}",
                status_code=400,
            )

        clean_title = (title or "").strip()
        if not clean_title:
            raise ClarityXException(
                message="Finding title cannot be empty or whitespace only.",
                status_code=400,
            )
        if len(clean_title) > 255:
            raise ClarityXException(
                message="Finding title must not exceed 255 characters.",
                status_code=400,
            )

        if confidence is not None:
            if not (0.0 <= confidence <= 1.0):
                raise ClarityXException(
                    message="Confidence must be between 0.0 and 1.0 when provided.",
                    status_code=400,
                )

        finding_data = {
            "research_id": session_id,
            "category": category,
            "title": clean_title,
            "description": description or "",
            "severity": severity,
            "confidence": confidence,
            "recommended_action": recommended_action or "",
        }

        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("findings").insert(finding_data).execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
            raise ClarityXException("Failed to persist finding record.", status_code=500)
        except Exception as exc:
            self.handle_db_error("create_finding", exc)
            return {}

    async def create_findings_bulk(
        self,
        session_id: str,
        user_id: str,
        findings_data: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Persists multiple findings in a single operation verifying session ownership."""
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            logger.warning(
                "Unauthorized bulk findings creation for session %s by user %s",
                session_id,
                user_id,
            )
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        if not findings_data:
            return []

        prepared_records = []
        for f in findings_data:
            cat = f.get("category", "")
            if cat not in ALLOWED_FINDING_CATEGORIES:
                raise ClarityXException(
                    message=f"Invalid category '{cat}'. Allowed: {', '.join(sorted(ALLOWED_FINDING_CATEGORIES))}",
                    status_code=400,
                )

            sev = f.get("severity", "medium")
            if sev not in ALLOWED_SEVERITIES:
                raise ClarityXException(
                    message=f"Invalid severity '{sev}'. Allowed: {', '.join(sorted(ALLOWED_SEVERITIES))}",
                    status_code=400,
                )

            clean_title = str(f.get("title", "")).strip()
            if not clean_title:
                raise ClarityXException(
                    "Finding title cannot be empty or whitespace only.",
                    status_code=400,
                )
            if len(clean_title) > 255:
                raise ClarityXException(
                    "Finding title must not exceed 255 characters.",
                    status_code=400,
                )

            conf = f.get("confidence")
            if conf is not None and not (0.0 <= float(conf) <= 1.0):
                raise ClarityXException(
                    "Confidence must be between 0.0 and 1.0.",
                    status_code=400,
                )

            prepared_records.append({
                "research_id": session_id,
                "category": cat,
                "title": clean_title,
                "description": f.get("description", "") or "",
                "severity": sev,
                "confidence": conf,
                "recommended_action": f.get("recommended_action", "") or "",
            })

        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("findings").insert(prepared_records).execute()
            )
            return response.data or []
        except Exception as exc:
            self.handle_db_error("create_findings_bulk", exc)
            return []

    async def get_findings_by_session(
        self, session_id: str, user_id: str
    ) -> List[Dict[str, Any]]:
        """Retrieves all findings for a session verifying user ownership."""
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("findings")
                .select("*")
                .eq("research_id", session_id)
                .order("created_at", desc=False)
                .execute()
            )
            return response.data or []
        except Exception as exc:
            self.handle_db_error("get_findings_by_session", exc)
            return []

    async def get_finding_by_id(
        self, finding_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a single finding verifying that its parent session belongs to the user."""
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("findings")
                .select("*")
                .eq("id", finding_id)
                .execute()
            )
            if not response.data or len(response.data) == 0:
                return None

            finding = response.data[0]
            session_id = finding.get("research_id")
            is_owner = await self.verify_session_ownership(session_id, user_id)
            if not is_owner:
                return None
            return finding
        except Exception as exc:
            self.handle_db_error("get_finding_by_id", exc)
            return None

    async def delete_findings_by_session(
        self, session_id: str, user_id: str
    ) -> int:
        """Deletes all findings belonging to a research session verifying ownership."""
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("findings")
                .delete()
                .eq("research_id", session_id)
                .execute()
            )
            return len(response.data or [])
        except Exception as exc:
            self.handle_db_error("delete_findings_by_session", exc)
            return 0


class EvidenceReferenceRepository(BaseRepository):
    """Repository managing evidence quotations linking findings to sources."""

    async def create_evidence_reference(
        self,
        session_id: str,
        user_id: str,
        finding_id: str,
        source_id: str,
        evidence_text: str,
        evidence_type: str = "supporting",
    ) -> Dict[str, Any]:
        """Creates an evidence reference verifying session ownership of finding and source."""
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        if evidence_type not in ALLOWED_EVIDENCE_TYPES:
            raise ClarityXException(
                message=f"Invalid evidence_type '{evidence_type}'. Allowed types: {', '.join(sorted(ALLOWED_EVIDENCE_TYPES))}",
                status_code=400,
            )

        clean_text = (evidence_text or "").strip()
        if not clean_text:
            raise ClarityXException(
                "Evidence text cannot be empty or whitespace only.",
                status_code=400,
            )

        # Verify finding belongs to session
        finding_resp = await anyio.to_thread.run_sync(
            lambda: self.client.table("findings")
            .select("id")
            .eq("id", finding_id)
            .eq("research_id", session_id)
            .execute()
        )
        if not finding_resp.data:
            raise ClarityXException(
                message="Referenced finding does not belong to this research session.",
                status_code=400,
            )

        # Verify source belongs to session
        source_resp = await anyio.to_thread.run_sync(
            lambda: self.client.table("sources")
            .select("id")
            .eq("id", source_id)
            .eq("research_id", session_id)
            .execute()
        )
        if not source_resp.data:
            raise ClarityXException(
                message="Referenced source does not belong to this research session.",
                status_code=400,
            )

        evidence_data = {
            "finding_id": finding_id,
            "source_id": source_id,
            "evidence_text": clean_text,
            "evidence_type": evidence_type,
        }

        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("evidence_references").insert(evidence_data).execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
            raise ClarityXException("Failed to persist evidence reference.", status_code=500)
        except Exception as exc:
            self.handle_db_error("create_evidence_reference", exc)
            return {}

    async def create_evidence_references_bulk(
        self,
        session_id: str,
        user_id: str,
        evidence_items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Persists multiple evidence references verifying session ownership of findings and sources."""
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        if not evidence_items:
            return []

        # Retrieve valid finding IDs and source IDs for this session
        findings_resp = await anyio.to_thread.run_sync(
            lambda: self.client.table("findings").select("id").eq("research_id", session_id).execute()
        )
        valid_finding_ids = {str(row["id"]) for row in (findings_resp.data or [])}

        sources_resp = await anyio.to_thread.run_sync(
            lambda: self.client.table("sources").select("id").eq("research_id", session_id).execute()
        )
        valid_source_ids = {str(row["id"]) for row in (sources_resp.data or [])}

        prepared_records = []
        for item in evidence_items:
            f_id = str(item.get("finding_id", ""))
            s_id = str(item.get("source_id", ""))
            ev_type = item.get("evidence_type", "supporting")
            ev_text = str(item.get("evidence_text", "")).strip()

            if f_id not in valid_finding_ids:
                raise ClarityXException(
                    message=f"Referenced finding '{f_id}' does not belong to this research session.",
                    status_code=400,
                )
            if s_id not in valid_source_ids:
                raise ClarityXException(
                    message=f"Referenced source '{s_id}' does not belong to this research session.",
                    status_code=400,
                )
            if ev_type not in ALLOWED_EVIDENCE_TYPES:
                raise ClarityXException(
                    message=f"Invalid evidence_type '{ev_type}'. Allowed types: {', '.join(sorted(ALLOWED_EVIDENCE_TYPES))}",
                    status_code=400,
                )
            if not ev_text:
                raise ClarityXException(
                    "Evidence text cannot be empty or whitespace only.",
                    status_code=400,
                )

            prepared_records.append({
                "finding_id": f_id,
                "source_id": s_id,
                "evidence_text": ev_text,
                "evidence_type": ev_type,
            })

        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("evidence_references").insert(prepared_records).execute()
            )
            return response.data or []
        except Exception as exc:
            self.handle_db_error("create_evidence_references_bulk", exc)
            return []

    async def get_evidence_for_findings(
        self,
        finding_ids: List[str],
        session_id: str,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """Retrieves evidence references for specific findings verifying session ownership."""
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        if not finding_ids:
            return []

        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("evidence_references")
                .select("id, finding_id, source_id, evidence_text, evidence_type, created_at, sources(source_code)")
                .in_("finding_id", finding_ids)
                .order("created_at", desc=False)
                .execute()
            )
            results = []
            for row in (response.data or []):
                item = dict(row)
                src = item.pop("sources", None)
                if isinstance(src, dict) and "source_code" in src:
                    item["source_code"] = src["source_code"]
                elif isinstance(src, list) and src and "source_code" in src[0]:
                    item["source_code"] = src[0]["source_code"]
                results.append(item)
            return results
        except Exception as exc:
            self.handle_db_error("get_evidence_for_findings", exc)
            return []

    async def get_evidence_by_session(
        self, session_id: str, user_id: str
    ) -> List[Dict[str, Any]]:
        """Retrieves all evidence references associated with a session's findings."""
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        findings_resp = await anyio.to_thread.run_sync(
            lambda: self.client.table("findings").select("id").eq("research_id", session_id).execute()
        )
        finding_ids = [str(r["id"]) for r in (findings_resp.data or [])]
        return await self.get_evidence_for_findings(finding_ids, session_id, user_id)

    async def delete_evidence_by_session(
        self, session_id: str, user_id: str
    ) -> int:
        """Explicitly deletes all evidence references for a session verifying ownership."""
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        findings_resp = await anyio.to_thread.run_sync(
            lambda: self.client.table("findings").select("id").eq("research_id", session_id).execute()
        )
        finding_ids = [str(r["id"]) for r in (findings_resp.data or [])]
        if not finding_ids:
            return 0

        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("evidence_references")
                .delete()
                .in_("finding_id", finding_ids)
                .execute()
            )
            return len(response.data or [])
        except Exception as exc:
            self.handle_db_error("delete_evidence_by_session", exc)
            return 0


ALLOWED_VERIFICATION_STATUSES = ("pending", "completed")


class VerificationRepository(BaseRepository):
    """Repository managing verification tasks and unresolved research questions."""

    async def create_verification_item(
        self,
        session_id: str,
        user_id: str,
        task: str,
        finding_id: Optional[str] = None,
        status: str = "pending",
    ) -> Dict[str, Any]:
        """Creates a verification item verifying session ownership and finding relationship."""
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        clean_task = (task or "").strip()
        if not clean_task:
            raise ClarityXException(
                "Verification task cannot be empty or whitespace only.",
                status_code=400,
            )

        if status not in ALLOWED_VERIFICATION_STATUSES:
            raise ClarityXException(
                message=f"Invalid status '{status}'. Allowed statuses: {', '.join(sorted(ALLOWED_VERIFICATION_STATUSES))}",
                status_code=400,
            )

        # If finding_id is specified, verify it belongs to this research session
        if finding_id is not None:
            finding_resp = await anyio.to_thread.run_sync(
                lambda: self.client.table("findings")
                .select("id")
                .eq("id", finding_id)
                .eq("research_id", session_id)
                .execute()
            )
            if not finding_resp.data:
                raise ClarityXException(
                    message="Referenced finding does not belong to this research session.",
                    status_code=400,
                )

        now_utc = datetime.now(timezone.utc).isoformat()
        item_data = {
            "research_id": session_id,
            "finding_id": finding_id,
            "task": clean_task,
            "status": status,
            "created_at": now_utc,
            "updated_at": now_utc,
            "completed_at": now_utc if status == "completed" else None,
        }

        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("verification_items").insert(item_data).execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
            raise ClarityXException("Failed to persist verification item.", status_code=500)
        except Exception as exc:
            self.handle_db_error("create_verification_item", exc)
            return {}

    async def create_verification_items_bulk(
        self,
        session_id: str,
        user_id: str,
        items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Persists multiple verification items in bulk verifying session ownership."""
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        if not items:
            return []

        # Fetch valid findings for this session to validate non-null finding_ids
        findings_resp = await anyio.to_thread.run_sync(
            lambda: self.client.table("findings").select("id").eq("research_id", session_id).execute()
        )
        valid_finding_ids = {str(row["id"]) for row in (findings_resp.data or [])}

        now_utc = datetime.now(timezone.utc).isoformat()
        prepared_records = []
        for item in items:
            task = str(item.get("task", "")).strip()
            if not task:
                raise ClarityXException(
                    "Verification task cannot be empty or whitespace only.",
                    status_code=400,
                )

            f_id = item.get("finding_id")
            if f_id is not None:
                f_id_str = str(f_id)
                if f_id_str not in valid_finding_ids:
                    raise ClarityXException(
                        message=f"Referenced finding '{f_id_str}' does not belong to this research session.",
                        status_code=400,
                    )
            else:
                f_id_str = None

            stat = item.get("status", "pending")
            if stat not in ALLOWED_VERIFICATION_STATUSES:
                raise ClarityXException(
                    message=f"Invalid status '{stat}'. Allowed: {', '.join(sorted(ALLOWED_VERIFICATION_STATUSES))}",
                    status_code=400,
                )

            prepared_records.append({
                "research_id": session_id,
                "finding_id": f_id_str,
                "task": task,
                "status": stat,
                "created_at": now_utc,
                "updated_at": now_utc,
                "completed_at": now_utc if stat == "completed" else None,
            })

        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("verification_items").insert(prepared_records).execute()
            )
            return response.data or []
        except Exception as exc:
            self.handle_db_error("create_verification_items_bulk", exc)
            return []

    async def list_items_by_session(
        self, session_id: str, user_id: str
    ) -> List[Dict[str, Any]]:
        """Retrieves all verification items for a session verifying user ownership."""
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("verification_items")
                .select("*")
                .eq("research_id", session_id)
                .order("created_at", desc=False)
                .execute()
            )
            return response.data or []
        except Exception as exc:
            self.handle_db_error("list_items_by_session", exc)
            return []

    async def get_item_by_id(
        self, item_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieves an individual verification item verifying session ownership."""
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("verification_items")
                .select("*")
                .eq("id", item_id)
                .execute()
            )
            if not response.data or len(response.data) == 0:
                return None

            item = response.data[0]
            session_id = item.get("research_id")
            is_owner = await self.verify_session_ownership(session_id, user_id)
            if not is_owner:
                logger.warning(
                    "Unauthorized access to verification item %s by user %s",
                    item_id,
                    user_id,
                )
                return None
            return item
        except Exception as exc:
            self.handle_db_error("get_item_by_id", exc)
            return None

    async def update_item_status(
        self, item_id: str, user_id: str, status: str
    ) -> Optional[Dict[str, Any]]:
        """Updates the status of a verification item with strict field isolation and timestamps."""
        if status not in ALLOWED_VERIFICATION_STATUSES:
            raise ClarityXException(
                message=f"Invalid verification status '{status}'. Allowed values: {', '.join(sorted(ALLOWED_VERIFICATION_STATUSES))}",
                status_code=400,
            )

        existing = await self.get_item_by_id(item_id, user_id)
        if not existing:
            return None

        now_utc = datetime.now(timezone.utc).isoformat()
        completed_at = now_utc if status == "completed" else None

        # Strictly isolate updated fields: research_id, finding_id, task can NEVER be altered
        update_data = {
            "status": status,
            "completed_at": completed_at,
            "updated_at": now_utc,
        }

        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("verification_items")
                .update(update_data)
                .eq("id", item_id)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as exc:
            self.handle_db_error("update_item_status", exc)
            return None

    async def delete_items_by_session(
        self, session_id: str, user_id: str
    ) -> int:
        """Deletes all verification items for a session verifying ownership."""
        is_owner = await self.verify_session_ownership(session_id, user_id)
        if not is_owner:
            raise ClarityXException(
                message="Research session not found or unauthorized",
                status_code=404,
                detail="The specified research session does not exist or does not belong to the authenticated user.",
            )

        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.table("verification_items")
                .delete()
                .eq("research_id", session_id)
                .execute()
            )
            return len(response.data or [])
        except Exception as exc:
            self.handle_db_error("delete_items_by_session", exc)
            return 0


def map_verification_to_finding_id(
    item: LLMVerificationItem,
    persisted_findings: List[Dict[str, Any]],
) -> Optional[str]:
    """Resolves an LLM verification item's related finding title to a persisted finding UUID.

    Rules:
    1. If `item.is_general_unresolved_question` is True:
       - Must resolve to None (finding_id = NULL).
    2. If `item.is_general_unresolved_question` is False:
       - `item.related_finding_title` must be provided and non-empty.
       - The normalized title must match EXACTLY ONE persisted finding.
       - If multiple persisted findings share the same normalized title, raises ClarityXException(400).
       - If no persisted finding matches the normalized title, raises ClarityXException(400).
       - Never silently converts a finding-specific task into a general question.
    """
    if item.is_general_unresolved_question:
        return None

    title_str = (item.related_finding_title or "").strip()
    if not title_str:
        raise ClarityXException(
            message="Finding-specific verification item must specify a related finding title.",
            status_code=400,
            detail=f"Verification task '{item.task}' is marked finding-specific but lacks related_finding_title.",
        )

    norm_target = " ".join(title_str.split()).lower()

    # Build normalized title to finding IDs index
    matches: List[str] = []
    for f in persisted_findings:
        f_title = str(f.get("title", "")).strip()
        if " ".join(f_title.split()).lower() == norm_target:
            matches.append(str(f["id"]))

    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        raise ClarityXException(
            message=f"Ambiguous finding title '{title_str}'. Multiple findings share this title.",
            status_code=400,
            detail=f"Found {len(matches)} findings matching title '{title_str}'.",
        )
    else:
        raise ClarityXException(
            message=f"Unmatched finding title '{title_str}'. No finding found with this title.",
            status_code=400,
            detail=f"Verification task '{item.task}' references non-existent finding title '{title_str}'.",
        )

