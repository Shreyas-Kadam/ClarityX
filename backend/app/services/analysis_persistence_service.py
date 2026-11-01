"""Analysis persistence service for ClarityX (Phase 6.3.3).

Orchestrates atomic persistence of AI-generated analysis findings,
evidence references, and verification items using the PostgreSQL RPC function
`save_analysis_results`.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import anyio
from postgrest.exceptions import APIError
from supabase import Client

from app.core.exceptions import ClarityXException, DatabaseConnectionError
from app.database.repositories import map_verification_to_finding_id
from app.database.supabase import get_supabase_client
from app.schemas.analysis import LLMAnalysisResponse
from app.schemas.research import ResearchReportData

logger = logging.getLogger("clarityx.analysis_persistence")


def parse_uuid(value: str, name: str = "identifier") -> UUID:
    """Validates and parses a string into a UUID, raising ClarityXException(400) if invalid."""
    try:
        return UUID(str(value).strip())
    except (ValueError, TypeError, AttributeError) as exc:
        raise ClarityXException(
            message=f"Invalid {name}",
            status_code=400,
            detail=f"The {name} must be a valid UUID format.",
        ) from exc


class AnalysisPersistenceService:
    """Service orchestrating atomic persistence of research analysis results."""

    def __init__(self, client: Optional[Client] = None):
        self._client = client

    @property
    def client(self) -> Client:
        """Retrieves the Supabase client, using injected client if present."""
        if self._client is not None:
            return self._client
        return get_supabase_client()

    def handle_rpc_error(self, exc: Exception, session_id: str, user_id: str) -> None:
        """Translates PostgREST / database exceptions into clean, user-safe application errors.

        Maps PostgreSQL SQLSTATEs and error messages to appropriate HTTP status codes:
        - no_data_found (P0002) / session not found -> 404
        - insufficient_privilege (42501) / unauthorized -> 403
        - foreign_key_violation (23503) / unknown source code -> 400
        - check_violation (23514) / invalid data -> 400
        - Connection / network errors -> DatabaseConnectionError (503)
        - Unexpected errors -> ClarityXException (500)
        """
        logger.error(
            "RPC error during save_analysis_results for session %s, user %s: %s",
            session_id,
            user_id,
            type(exc).__name__,
            exc_info=True,
        )

        if isinstance(exc, APIError):
            err_msg = str(getattr(exc, "message", exc) or "").strip()
            err_code = str(getattr(exc, "code", "") or "").strip()
            lower_msg = err_msg.lower()

            # Session not found (SQLSTATE P0002 or explicit message)
            if err_code == "P0002" or "not found" in lower_msg:
                raise ClarityXException(
                    message="Research session not found",
                    status_code=404,
                    detail="The specified research session does not exist.",
                )

            # Ownership mismatch (SQLSTATE 42501 or explicit unauthorized message)
            if err_code == "42501" or "unauthorized" in lower_msg or "does not belong" in lower_msg:
                raise ClarityXException(
                    message="Unauthorized access to research session",
                    status_code=403,
                    detail="The research session does not belong to the authenticated user.",
                )

            # Unknown source code or foreign key failure (SQLSTATE 23503)
            if err_code == "23503" or "unknown or invalid source code" in lower_msg:
                raise ClarityXException(
                    message="Invalid evidence reference in analysis",
                    status_code=400,
                    detail="One or more evidence citations reference an unknown or invalid source code.",
                )

            # Constraint / check violations / invalid parameters (SQLSTATE 23514, 23502, 22000, 22003, 22023, 22P02)
            if (
                err_code in ("23514", "23502", "22000", "22003", "22023", "22P02")
                or "check_violation" in lower_msg
                or "invalid_parameter_value" in lower_msg
            ):
                raise ClarityXException(
                    message="Analysis data violates schema constraints",
                    status_code=400,
                    detail="Analysis findings or verification tasks failed database validation constraints.",
                )

            # General PostgREST APIError: clean message without leaking SQL internals
            raise ClarityXException(
                message="Failed to persist analysis results.",
                status_code=400,
                detail="The database was unable to complete atomic analysis persistence.",
            )

        # Network / Connection / Timeout exceptions
        if any(err_name in type(exc).__name__ for err_name in ("Connect", "Network", "Timeout", "Socket", "HTTP")):
            raise DatabaseConnectionError(
                message="Unable to connect to the database to persist analysis results. Please try again later."
            )

        # Unexpected server errors
        raise ClarityXException(
            message="An unexpected error occurred while persisting analysis results.",
            status_code=500,
            detail="Internal analysis persistence failure.",
        )

    async def persist_analysis(
        self,
        session_id: str,
        user_id: str,
        analysis: LLMAnalysisResponse,
    ) -> ResearchReportData:
        """Atomically persists findings, evidence references, and verification items.

        Parameters:
            session_id: UUID of the target research session.
            user_id: UUID of the authenticated user (derived strictly from auth context).
            analysis: Validated and grounded LLMAnalysisResponse from AIService.

        Returns:
            ResearchReportData: Sanitized report data containing findings, evidence references,
                                unresolved questions, verification items, and source previews.
        """
        # 1. Validate identifiers
        session_uuid = parse_uuid(session_id, "research_id")
        user_uuid = parse_uuid(user_id, "user_id")

        session_id_str = str(session_uuid)
        user_id_str = str(user_uuid)

        # 2. Pre-generate finding UUIDs and build findings payload
        findings_payload: List[Dict[str, Any]] = []
        evidence_payload: List[Dict[str, Any]] = []

        for finding in analysis.findings:
            f_uuid = str(uuid4())
            findings_payload.append({
                "id": f_uuid,
                "category": finding.category,
                "title": (finding.title or "").strip(),
                "description": finding.description or "",
                "severity": finding.severity,
                "confidence": finding.confidence,
                "recommended_action": finding.recommended_action or "",
            })

            # Map nested evidence: quote -> evidence_text, attach generated finding_id
            for ev in finding.evidence:
                evidence_payload.append({
                    "id": str(uuid4()),
                    "finding_id": f_uuid,
                    "source_code": (ev.source_code or "").strip(),
                    "evidence_text": (ev.quote or "").strip(),
                    "evidence_type": ev.evidence_type,
                })

        # 3. Pre-flight verification title mapping
        # Ambiguous (duplicate) or unmatched titles raise ClarityXException(400) immediately.
        # Explicit general questions resolve strictly to finding_id = None.
        verification_payload: List[Dict[str, Any]] = []
        for item in analysis.verification_checklist:
            resolved_finding_id = map_verification_to_finding_id(item, findings_payload)
            verification_payload.append({
                "id": str(uuid4()),
                "finding_id": resolved_finding_id,
                "task": (item.task or "").strip(),
                "status": "pending",
            })

        for item in getattr(analysis, "unresolved_questions", []):
            task_text = (item.task or "").strip()
            if any(v["finding_id"] is None and v["task"] == task_text for v in verification_payload):
                continue
            verification_payload.append({
                "id": str(uuid4()),
                "finding_id": None,
                "task": task_text,
                "status": "pending",
            })

        # 4. Construct RPC payload
        rpc_payload = {
            "p_session_id": session_id_str,
            "p_user_id": user_id_str,
            "p_summary": analysis.summary or "",
            "p_findings": findings_payload,
            "p_evidence_references": evidence_payload,
            "p_verification_items": verification_payload,
        }

        # 5. Offload synchronous Supabase RPC call to worker thread
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self.client.rpc("save_analysis_results", rpc_payload).execute()
            )
        except Exception as exc:
            self.handle_rpc_error(exc, session_id_str, user_id_str)
            # handle_rpc_error always raises, but return for static analysis
            raise

        if not response.data:
            logger.error("RPC save_analysis_results returned empty data for session %s", session_id_str)
            raise ClarityXException(
                message="Failed to persist analysis results.",
                status_code=500,
                detail="Database RPC execution completed without returning report data.",
            )

        # 6. Parse and return sanitized ResearchReportData
        try:
            return ResearchReportData.model_validate(response.data)
        except Exception as exc:
            logger.error(
                "Failed to parse RPC response data into ResearchReportData: %s",
                exc,
                exc_info=True,
            )
            raise ClarityXException(
                message="Analysis completed but failed to format report response.",
                status_code=500,
                detail="The database persisted analysis results, but the returned structure failed validation.",
            ) from exc

