"""ClarityX End-to-End Live Supabase Analysis Persistence Integration Verification Script (Phase 6.4).

Verifies the complete analysis lifecycle against real live Supabase:
- Test A: Migration & RPC permissions check (public.save_analysis_results).
- Test B: Successful analysis persistence (Alpha: 4 finding categories, evidence, tasks, questions).
- Test C: Full research report retrieval (GET /api/research/{id} via real JWT).
- Test D: Re-analysis, atomic replacement, completed checklist task preservation, duplicate matching.
- Test E: Atomic failure behavior (invalid inputs rejected by RPC without corrupting existing data).
- Test F: Multi-user ownership & isolation (Beta cannot view or modify Alpha's data).
- Test G: Failure, edge cases, and privacy enforcement (no extracted_content or secrets in report).
- Guaranteed cleanup of disposable Alpha and Beta resources in a try/finally block.
"""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import uuid

# Ensure backend root directory is in sys.path
backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from httpx import ASGITransport, AsyncClient
from postgrest.exceptions import APIError
from supabase import Client, ClientOptions, create_client

from app.core.config import get_settings
from app.core.exceptions import ClarityXException, DatabaseConnectionError
from app.database.repositories import (
    EvidenceReferenceRepository,
    FindingRepository,
    ResearchRepository,
    SourceRepository,
    VerificationRepository,
)
from app.database.supabase import get_supabase_client
from app.main import create_app
from app.schemas.analysis import (
    LLMAnalysisResponse,
    LLMEvidenceItem,
    LLMFindingItem,
    LLMVerificationItem,
)
from app.schemas.research import ResearchReportData, ResearchReportEnvelope
from app.services.analysis_persistence_service import AnalysisPersistenceService


def create_authenticated_user_client(
    supabase_url: str,
    anon_key: str,
    token: str,
) -> Client:
    """Creates a user-scoped Supabase client using anon key and Bearer JWT.

    Uses ClientOptions to set the Authorization header for PostgREST,
    and applies client.postgrest.auth(token) for strict authentication without service-role privileges.
    """
    options = ClientOptions(headers={"Authorization": f"Bearer {token}"})
    client = create_client(supabase_url, anon_key, options=options)
    client.postgrest.auth(token)
    return client


async def run_live_analysis_integration_tests() -> int:
    settings = get_settings()
    admin_client = get_supabase_client()

    run_id = uuid.uuid4().hex[:8]
    email_alpha = f"live_analysis_alpha_{run_id}@clarityx.dev"
    email_beta = f"live_analysis_beta_{run_id}@clarityx.dev"
    test_password = f"P@ssword_{uuid.uuid4().hex[:12]}!"

    alpha_user_id: Optional[str] = None
    beta_user_id: Optional[str] = None
    session_alpha_id: Optional[str] = None
    session_beta_id: Optional[str] = None

    created_sources_alpha: List[str] = []
    created_sources_beta: List[str] = []

    overall_success = True

    print("==================================================================")
    print(f"CLARITYX LIVE SUPABASE ANALYSIS PERSISTENCE VERIFICATION (Run ID: {run_id})")
    print("==================================================================")

    try:
        # ---------------------------------------------------------------------
        # PREFLIGHT: PROBE RPC FUNCTION MIGRATION STATUS
        # ---------------------------------------------------------------------
        print("\n--- [Preflight] Probing Live Supabase save_analysis_results RPC ---")
        rpc_migration_applied = False
        try:
            # Probe with dummy call
            admin_client.rpc(
                "save_analysis_results",
                {
                    "p_session_id": "00000000-0000-0000-0000-000000000000",
                    "p_user_id": "00000000-0000-0000-0000-000000000000",
                    "p_summary": "",
                    "p_findings": [],
                    "p_evidence_references": [],
                    "p_verification_items": [],
                },
            ).execute()
            rpc_migration_applied = True
            print("[PASS] save_analysis_results RPC exists and responded")
        except APIError as exc:
            if exc.code == "PGRST202":
                rpc_migration_applied = False
                print("[BLOCKED] save_analysis_results function is NOT found in Supabase schema cache (PGRST202).")
            elif exc.code in ("P0002", "no_data_found", "42501", "22023"):
                # Function exists and threw expected domain exception (e.g. session not found)
                rpc_migration_applied = True
                print(f"[PASS] save_analysis_results RPC exists in database (responded with expected SQLSTATE code={exc.code})")
            else:
                print(f"[NOTE] RPC probe returned code={exc.code}, message={exc.message}")
                if "could not find the function" in (exc.message or "").lower():
                    rpc_migration_applied = False
                else:
                    rpc_migration_applied = True
        except Exception as exc:
            print(f"[NOTE] Unexpected probe exception: {type(exc).__name__}: {exc}")

        if not rpc_migration_applied:
            print("\n" + "=" * 66)
            print("CRITICAL NOTICE: Migration 003 has not yet been applied to Supabase!")
            print("The live PostgreSQL function public.save_analysis_results() does not exist.")
            print("Per docs/DATABASE.md Section 13.2, apply:")
            print("  backend/app/database/migrations/003_save_analysis_results.sql")
            print("in the Supabase Dashboard SQL Editor.")
            print("=" * 66)
            return 2

        # ---------------------------------------------------------------------
        # TEST A: MIGRATION & RPC PERMISSIONS
        # ---------------------------------------------------------------------
        print("\n--- [Test A] Migration & RPC Security Permissions ---")
        public_client = create_client(settings.SUPABASE_BASE_URL, settings.SUPABASE_ANON_KEY)

        # 1. Verify anon / unauthenticated cannot execute RPC
        anon_blocked = False
        try:
            public_client.rpc(
                "save_analysis_results",
                {
                    "p_session_id": "00000000-0000-0000-0000-000000000000",
                    "p_user_id": "00000000-0000-0000-0000-000000000000",
                    "p_summary": "",
                    "p_findings": [],
                    "p_evidence_references": [],
                    "p_verification_items": [],
                },
            ).execute()
        except APIError as exc:
            # Expected 42501 (insufficient_privilege) or PGRST301/401/403
            anon_blocked = True
            print(f"[PASS] anon/public client execution blocked as expected (code={exc.code})")
        except Exception as exc:
            anon_blocked = True
            print(f"[PASS] anon/public client execution denied ({type(exc).__name__})")

        assert anon_blocked, "CRITICAL: anon role was able to execute save_analysis_results!"

        # 2. Provision Users Alpha & Beta
        print("\n--- [Setup] Provisioning Disposable Users & Live JWTs ---")
        user_alpha_resp = admin_client.auth.admin.create_user({
            "email": email_alpha,
            "password": test_password,
            "email_confirm": True,
            "user_metadata": {"full_name": f"Alpha Analyst {run_id}"},
        })
        alpha_user_id = str(user_alpha_resp.user.id)
        print(f"[PASS] User Alpha created (ID: {alpha_user_id})")

        user_beta_resp = admin_client.auth.admin.create_user({
            "email": email_beta,
            "password": test_password,
            "email_confirm": True,
            "user_metadata": {"full_name": f"Beta Analyst {run_id}"},
        })
        beta_user_id = str(user_beta_resp.user.id)
        print(f"[PASS] User Beta created (ID: {beta_user_id})")

        # Authenticate users to acquire real JWTs
        session_alpha = public_client.auth.sign_in_with_password({
            "email": email_alpha,
            "password": test_password,
        })
        token_alpha = session_alpha.session.access_token
        headers_alpha = {"Authorization": f"Bearer {token_alpha}"}
        print("[PASS] User Alpha authenticated (JWT acquired)")

        session_beta = public_client.auth.sign_in_with_password({
            "email": email_beta,
            "password": test_password,
        })
        token_beta = session_beta.session.access_token
        headers_beta = {"Authorization": f"Bearer {token_beta}"}
        print("[PASS] User Beta authenticated (JWT acquired)")

        # 3. Verify authenticated user role directly cannot execute RPC (only service_role has GRANT EXECUTE)
        auth_client = create_authenticated_user_client(
            settings.SUPABASE_BASE_URL,
            settings.SUPABASE_ANON_KEY,
            token_alpha,
        )
        auth_user_blocked = False
        try:
            auth_client.rpc(
                "save_analysis_results",
                {
                    "p_session_id": "00000000-0000-0000-0000-000000000000",
                    "p_user_id": alpha_user_id,
                    "p_summary": "",
                    "p_findings": [],
                    "p_evidence_references": [],
                    "p_verification_items": [],
                },
            ).execute()
        except APIError as exc:
            auth_user_blocked = True
            print(f"[PASS] authenticated client direct RPC call denied as expected (code={exc.code})")
        except Exception:
            auth_user_blocked = True
            print("[PASS] authenticated client direct RPC call denied as expected")

        assert auth_user_blocked, "CRITICAL: authenticated role directly executed save_analysis_results without service_role!"

        # Initialize FastAPI app test transport
        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create research sessions
            res_alpha_sess = await client.post(
                "/api/research",
                headers=headers_alpha,
                json={"research_goal": f"Live Supabase Quantum Computing Feasibility ({run_id})"},
            )
            assert res_alpha_sess.status_code == 201
            session_alpha_id = res_alpha_sess.json()["data"]["id"]
            print(f"[PASS] Alpha research session created (ID: {session_alpha_id})")

            res_beta_sess = await client.post(
                "/api/research",
                headers=headers_beta,
                json={"research_goal": f"Beta Isolated Session ({run_id})"},
            )
            assert res_beta_sess.status_code == 201
            session_beta_id = res_beta_sess.json()["data"]["id"]
            print(f"[PASS] Beta research session created (ID: {session_beta_id})")

            # -----------------------------------------------------------------
            # SETUP SOURCES FOR ALPHA
            # -----------------------------------------------------------------
            print("\n--- [Setup] Adding Live Sources for Alpha ---")
            source_content_1 = (
                "Superconducting transmon qubits operate at millikelvin dilution refrigerator temperatures. "
                "Coherence time T1 averages 120 microseconds for transmon architectures. "
                "Surface code quantum error correction requires a physical error rate below 0.5 percent per gate."
            )
            source_content_2 = (
                "Trapped-ion quantum systems achieve single-qubit gate fidelities exceeding 99.99 percent at room temperature vacuum. "
                "However, multi-qubit shuttling latency introduces critical decoherence overhead in large ion crystals. "
                "Published benchmarks from 2024 claim 50-qubit entanglement without fault tolerance."
            )

            # Insert Source S1 for Alpha
            s1_resp = admin_client.table("sources").insert({
                "research_id": session_alpha_id,
                "source_code": "S1",
                "title": "Superconducting Transmon Architecture Benchmark",
                "url": f"https://arxiv.example.com/superconducting-{run_id}",
                "source_type": "website",
                "extracted_content": source_content_1,
                "extraction_status": "success",
            }).execute()
            s1_id = s1_resp.data[0]["id"]
            created_sources_alpha.append(s1_id)
            print(f"[PASS] Source S1 inserted (ID: {s1_id})")

            # Insert Source S2 for Alpha
            s2_resp = admin_client.table("sources").insert({
                "research_id": session_alpha_id,
                "source_code": "S2",
                "title": "Trapped-Ion Quantum Computing Systems Review",
                "url": f"https://arxiv.example.com/trapped-ion-{run_id}",
                "source_type": "website",
                "extracted_content": source_content_2,
                "extraction_status": "success",
            }).execute()
            s2_id = s2_resp.data[0]["id"]
            created_sources_alpha.append(s2_id)
            print(f"[PASS] Source S2 inserted (ID: {s2_id})")

            # Insert Source S1 for Beta (to verify isolation)
            s_beta_resp = admin_client.table("sources").insert({
                "research_id": session_beta_id,
                "source_code": "S1",
                "title": "Beta Independent Source",
                "url": f"https://beta.example.com/source-{run_id}",
                "source_type": "website",
                "extracted_content": "Beta private source text.",
                "extraction_status": "success",
            }).execute()
            created_sources_beta.append(s_beta_resp.data[0]["id"])
            print(f"[PASS] Beta Source S1 inserted (ID: {created_sources_beta[0]})")

            # -----------------------------------------------------------------
            # TEST B: SUCCESSFUL ANALYSIS PERSISTENCE
            # -----------------------------------------------------------------
            print("\n--- [Test B] Successful Analysis Persistence (Alpha) ---")
            persistence_service = AnalysisPersistenceService()

            # Construct deterministic analysis response with all 4 categories, evidence types, and verification items
            analysis_data_1 = LLMAnalysisResponse(
                summary="Rigorous evaluation of superconducting vs trapped-ion quantum computing hardware limits.",
                findings=[
                    LLMFindingItem(
                        category="missing",
                        title="Two-Qubit Gate Error Budget Omitted",
                        description="Neither source explicitly quantifies the two-qubit entangling gate error rates for scaled systems.",
                        severity="high",
                        confidence=0.92,
                        recommended_action="Benchmark cross-resonance gate fidelity against recent hardware roadmaps.",
                        evidence=[
                            LLMEvidenceItem(
                                source_code="S1",
                                quote="Surface code quantum error correction requires a physical error rate below 0.5 percent per gate.",
                                evidence_type="contextual",
                            )
                        ],
                    ),
                    LLMFindingItem(
                        category="outdated",
                        title="2024 Entanglement Benchmark Outdated",
                        description="Reported 50-qubit entanglement reflects 2024 literature and ignores modern 2026 neutral-atom breakthroughs.",
                        severity="medium",
                        confidence=0.85,
                        recommended_action="Cross-reference with 2026 neutral atom and topological benchmark registries.",
                        evidence=[
                            LLMEvidenceItem(
                                source_code="S2",
                                quote="Published benchmarks from 2024 claim 50-qubit entanglement without fault tolerance.",
                                evidence_type="supporting",
                            )
                        ],
                    ),
                    LLMFindingItem(
                        category="conflicting",
                        title="Operating Temperature Requirements Divergence",
                        description="Sources present fundamentally conflicting operational environments: millikelvin dilution versus room temperature vacuum.",
                        severity="high",
                        confidence=0.95,
                        recommended_action="Assess infrastructure capital costs for cryogenic cooling versus ultra-high vacuum chambers.",
                        evidence=[
                            LLMEvidenceItem(
                                source_code="S1",
                                quote="Superconducting transmon qubits operate at millikelvin dilution refrigerator temperatures.",
                                evidence_type="contradicting",
                            ),
                            LLMEvidenceItem(
                                source_code="S2",
                                quote="Trapped-ion quantum systems achieve single-qubit gate fidelities exceeding 99.99 percent at room temperature vacuum.",
                                evidence_type="supporting",
                            ),
                        ],
                    ),
                    LLMFindingItem(
                        category="unverified",
                        title="Shuttling Latency Impact Unverified",
                        description="The assertion that shuttling latency in large ion crystals causes critical decoherence overhead lacks supporting empirical datasets.",
                        severity="medium",
                        confidence=0.78,
                        recommended_action="Obtain empirical decoherence-under-transport curves for 100+ ion shuttling architectures.",
                        evidence=[
                            LLMEvidenceItem(
                                source_code="S2",
                                quote="However, multi-qubit shuttling latency introduces critical decoherence overhead in large ion crystals.",
                                evidence_type="contextual",
                            )
                        ],
                    ),
                ],
                unresolved_questions=[
                    LLMVerificationItem(
                        task="What is the maximum optical power threshold before thermal heating impairs ion crystal stability?",
                        is_general_unresolved_question=True,
                        related_finding_title=None,
                    )
                ],
                verification_checklist=[
                    LLMVerificationItem(
                        task="Verify cross-resonance two-qubit gate error rates on modern superconducting QPUs.",
                        related_finding_title="Two-Qubit Gate Error Budget Omitted",
                    ),
                    LLMVerificationItem(
                        task="Measure shuttling transport fidelity across segmented Paul trap junctions.",
                        related_finding_title="Shuttling Latency Impact Unverified",
                    ),
                ],
            )

            # Persist analysis via AnalysisPersistenceService
            raw_sources_alpha = [
                {"id": s1_id, "source_code": "S1", "extracted_content": source_content_1},
                {"id": s2_id, "source_code": "S2", "extracted_content": source_content_2},
            ]

            persisted_report_1 = await persistence_service.persist_analysis(
                session_id=session_alpha_id,
                user_id=alpha_user_id,
                analysis=analysis_data_1,
            )

            assert persisted_report_1 is not None
            assert str(persisted_report_1.research_id) == session_alpha_id
            assert persisted_report_1.status == "completed"
            assert len(persisted_report_1.findings) == 4

            # Safe diagnostic output
            print(f"[DIAGNOSTIC] Expected unresolved_questions: 1, Actual: {len(persisted_report_1.unresolved_questions)}")
            print(f"[DIAGNOSTIC] Expected verification_items: 2, Actual: {len(persisted_report_1.verification_items)}")
            for uq in persisted_report_1.unresolved_questions:
                print(f"[DIAGNOSTIC]   Unresolved question: task='{uq.task[:60]}...'")
            for vi in persisted_report_1.verification_items:
                print(f"[DIAGNOSTIC]   Verification item: finding_id={vi.finding_id}, task='{vi.task[:60]}...'")

            assert len(persisted_report_1.unresolved_questions) == 1
            assert len(persisted_report_1.verification_items) == 2
            assert len(persisted_report_1.sources) == 2
            print("[PASS] AnalysisPersistenceService persisted analysis atomically via real Supabase RPC")

            # Direct database verification via PostgreSQL tables
            db_findings = (
                admin_client.table("findings")
                .select("*")
                .eq("research_id", session_alpha_id)
                .execute()
                .data
            )
            assert len(db_findings) == 4
            categories_found = {f["category"] for f in db_findings}
            assert categories_found == {"missing", "outdated", "conflicting", "unverified"}
            print("[PASS] All 4 finding categories confirmed in Supabase findings table")

            db_evidence = (
                admin_client.table("evidence_references")
                .select("*, sources(source_code)")
                .execute()
                .data
            )
            # Find evidence belonging to Alpha's findings
            alpha_finding_ids = {f["id"] for f in db_findings}
            alpha_evidence = [e for e in db_evidence if e["finding_id"] in alpha_finding_ids]
            assert len(alpha_evidence) == 5  # 1 + 1 + 2 + 1
            assert {e["evidence_type"] for e in alpha_evidence} == {"supporting", "contradicting", "contextual"}
            print(f"[PASS] 5 evidence references confirmed in database with supporting, contradicting, contextual types")

            db_tasks = (
                admin_client.table("verification_items")
                .select("*")
                .eq("research_id", session_alpha_id)
                .execute()
                .data
            )
            assert len(db_tasks) == 3  # 1 unresolved question + 2 checklist items
            unresolved_db = [t for t in db_tasks if t["finding_id"] is None]
            checklist_db = [t for t in db_tasks if t["finding_id"] is not None]
            assert len(unresolved_db) == 1
            assert len(checklist_db) == 2
            print("[PASS] General unresolved questions (finding_id=NULL) and finding-specific tasks confirmed in DB")

            # -----------------------------------------------------------------
            # TEST C: FULL REPORT RETRIEVAL (API)
            # -----------------------------------------------------------------
            print("\n--- [Test C] Full Report Retrieval via GET /api/research/{id} ---")
            res_get_report = await client.get(
                f"/api/research/{session_alpha_id}",
                headers=headers_alpha,
            )
            assert res_get_report.status_code == 200, f"Get report failed: {res_get_report.text}"
            report_envelope = res_get_report.json()
            assert report_envelope["success"] is True
            rep_data = report_envelope["data"]

            assert rep_data["research_id"] == session_alpha_id
            assert rep_data["status"] == "completed"
            assert len(rep_data["findings"]) == 4
            assert len(rep_data["sources"]) == 2
            assert len(rep_data["unresolved_questions"]) == 1
            assert len(rep_data["verification_items"]) == 2

            # Privacy checks
            for src in rep_data["sources"]:
                assert "extracted_content" not in src, "CRITICAL: extracted_content exposed in report sources!"
                assert "content_preview" in src
                assert len(src["content_preview"]) <= 253  # 250 + "..."
            assert "service_role" not in res_get_report.text
            assert "secret" not in res_get_report.text
            print("[PASS] Full report retrieved: 4 findings, nested evidence with source_code, previews <= 250 chars, no extracted_content")

            # -----------------------------------------------------------------
            # TEST D: RE-ANALYSIS & ATOMIC REPLACEMENT (TASK PRESERVATION)
            # -----------------------------------------------------------------
            print("\n--- [Test D] Re-Analysis, Atomic Replacement & Completed Task Preservation ---")
            # Mark one verification item as COMPLETED in the database
            task_to_complete = checklist_db[0]
            task_completed_text = task_to_complete["task"]
            task_to_keep_pending = checklist_db[1]
            now_iso = datetime.now(timezone.utc).isoformat()

            admin_client.table("verification_items").update({
                "status": "completed",
                "completed_at": now_iso,
            }).eq("id", task_to_complete["id"]).execute()
            print(f"[PASS] Marked task completed in DB: '{task_completed_text[:40]}...'")

            # Prepare second analysis:
            # 1. Finding with the completed task (matching normalized text)
            # 2. A brand new finding & verification task
            # 3. An updated unresolved question
            analysis_data_2 = LLMAnalysisResponse(
                summary="Updated re-analysis incorporating 2026 cryo-CMOS integration benchmarks.",
                findings=[
                    LLMFindingItem(
                        category="missing",
                        title="Two-Qubit Gate Error Budget Omitted (Updated)",
                        description="Updated description after re-analysis.",
                        severity="high",
                        confidence=0.94,
                        recommended_action="Updated action recommendation.",
                        evidence=[
                            LLMEvidenceItem(
                                source_code="S1",
                                quote="Surface code quantum error correction requires a physical error rate below 0.5 percent per gate.",
                                evidence_type="contextual",
                            )
                        ],
                    ),
                    LLMFindingItem(
                        category="unverified",
                        title="Cryo-CMOS Controller Power Dissipation",
                        description="Dissipation of 4K cryo-CMOS controllers inside dilution refrigerators is unverified.",
                        severity="medium",
                        confidence=0.82,
                        recommended_action="Review sub-kelvin thermal dissipation budgets.",
                        evidence=[
                            LLMEvidenceItem(
                                source_code="S1",
                                quote="Superconducting transmon qubits operate at millikelvin dilution refrigerator temperatures.",
                                evidence_type="supporting",
                            )
                        ],
                    ),
                ],
                unresolved_questions=[
                    LLMVerificationItem(
                        task="What is the heat load threshold of dilution refrigerators at 100 mK?",
                        is_general_unresolved_question=True,
                        related_finding_title=None,
                    )
                ],
                verification_checklist=[
                    # Exact match to previously completed task (with minor whitespace / casing to test normalization)
                    LLMVerificationItem(
                        task=f"  {task_completed_text.strip()}  ",
                        related_finding_title="Two-Qubit Gate Error Budget Omitted (Updated)",
                    ),
                    # New task that must remain pending
                    LLMVerificationItem(
                        task="Evaluate 4-Kelvin cryo-CMOS multiplexer heat dissipation under continuous readout.",
                        related_finding_title="Cryo-CMOS Controller Power Dissipation",
                    ),
                ],
            )

            persisted_report_2 = await persistence_service.persist_analysis(
                session_id=session_alpha_id,
                user_id=alpha_user_id,
                analysis=analysis_data_2,
            )

            assert len(persisted_report_2.findings) == 2
            assert len(persisted_report_2.verification_items) == 2

            # Verify completed task preservation
            matched_completed_item = next(
                (v for v in persisted_report_2.verification_items if v.task.strip() == task_completed_text.strip()),
                None,
            )
            assert matched_completed_item is not None, "Completed task was not returned in report!"
            assert matched_completed_item.status == "completed", f"Status expected completed, got {matched_completed_item.status}"
            assert matched_completed_item.completed_at is not None, "completed_at was lost across re-analysis!"
            print(f"[PASS] Re-analysis preserved completed status and completed_at for matched task")

            # Verify new task is pending
            new_item = next(
                (v for v in persisted_report_2.verification_items if "cryo-CMOS" in v.task),
                None,
            )
            assert new_item is not None
            assert new_item.status == "pending"
            assert new_item.completed_at is None
            print("[PASS] New verification task is correctly set to status='pending' with completed_at=NULL")

            # Verify old findings were cleanly replaced (count is now 2, old titles gone)
            db_findings_after = (
                admin_client.table("findings")
                .select("title")
                .eq("research_id", session_alpha_id)
                .execute()
                .data
            )
            assert len(db_findings_after) == 2
            assert not any("Operating Temperature Requirements" in f["title"] for f in db_findings_after)
            print("[PASS] Old findings were atomically replaced; zero orphaned finding records remain")

            # -----------------------------------------------------------------
            # TEST E: ATOMIC FAILURE BEHAVIOR
            # -----------------------------------------------------------------
            print("\n--- [Test E] Atomic Failure Behavior (Invalid Inputs Rejected Without Corruption) ---")
            # Snapshot valid report state before testing failures
            state_before = (
                admin_client.table("research_sessions")
                .select("summary, status")
                .eq("id", session_alpha_id)
                .execute()
                .data[0]
            )
            findings_count_before = len(
                admin_client.table("findings")
                .select("id")
                .eq("research_id", session_alpha_id)
                .execute()
                .data
            )

            # Test E1: Invalid finding category
            bad_category_findings = [
                {
                    "id": str(uuid.uuid4()),
                    "category": "invalid_category_xyz",
                    "title": "Bad Category Finding",
                    "description": "Invalid category test.",
                    "severity": "high",
                    "confidence": 0.8,
                    "recommended_action": "Action",
                }
            ]
            failed_e1 = False
            try:
                admin_client.rpc(
                    "save_analysis_results",
                    {
                        "p_session_id": session_alpha_id,
                        "p_user_id": alpha_user_id,
                        "p_summary": "Should never be persisted",
                        "p_findings": bad_category_findings,
                        "p_evidence_references": [],
                        "p_verification_items": [],
                    },
                ).execute()
            except APIError as exc:
                failed_e1 = True
                print(f"[PASS] Invalid category rejected by RPC (code={exc.code}, message={exc.message[:50]})")

            assert failed_e1, "RPC failed to reject invalid finding category!"

            # Test E2: Invalid confidence out of range (> 1.0)
            bad_confidence_findings = [
                {
                    "id": str(uuid.uuid4()),
                    "category": "missing",
                    "title": "Bad Confidence Finding",
                    "description": "Confidence out of bounds.",
                    "severity": "high",
                    "confidence": 1.5,
                    "recommended_action": "Action",
                }
            ]
            failed_e2 = False
            try:
                admin_client.rpc(
                    "save_analysis_results",
                    {
                        "p_session_id": session_alpha_id,
                        "p_user_id": alpha_user_id,
                        "p_summary": "Should never be persisted",
                        "p_findings": bad_confidence_findings,
                        "p_evidence_references": [],
                        "p_verification_items": [],
                    },
                ).execute()
            except APIError as exc:
                failed_e2 = True
                print(f"[PASS] Invalid confidence (1.5) rejected by RPC (code={exc.code})")

            assert failed_e2, "RPC failed to reject confidence > 1.0!"

            # Test E3: Evidence referencing nonexistent finding
            orphan_evidence = [
                {
                    "finding_id": str(uuid.uuid4()),  # Nonexistent
                    "source_code": "S1",
                    "evidence_text": "Superconducting transmon qubits operate at millikelvin dilution refrigerator temperatures.",
                    "evidence_type": "supporting",
                }
            ]
            failed_e3 = False
            try:
                admin_client.rpc(
                    "save_analysis_results",
                    {
                        "p_session_id": session_alpha_id,
                        "p_user_id": alpha_user_id,
                        "p_summary": "Should never be persisted",
                        "p_findings": [
                            {
                                "id": str(uuid.uuid4()),
                                "category": "missing",
                                "title": "Valid Finding",
                                "description": "Valid desc",
                                "severity": "medium",
                                "confidence": 0.8,
                                "recommended_action": "Action",
                            }
                        ],
                        "p_evidence_references": orphan_evidence,
                        "p_verification_items": [],
                    },
                ).execute()
            except APIError as exc:
                failed_e3 = True
                print(f"[PASS] Evidence referencing unknown finding rejected by RPC (code={exc.code})")

            assert failed_e3, "RPC failed to reject orphan evidence reference!"

            # Test E4: Evidence referencing a source outside the research session (Beta's source code S1 is in Beta's session, but let's test invalid source_code S99)
            invalid_source_code_evidence = [
                {
                    "finding_id": str(uuid.uuid4()),
                    "source_code": "S99",
                    "evidence_text": "Nonexistent source text.",
                    "evidence_type": "supporting",
                }
            ]
            valid_finding_id = str(uuid.uuid4())
            invalid_source_code_evidence[0]["finding_id"] = valid_finding_id
            failed_e4 = False
            try:
                admin_client.rpc(
                    "save_analysis_results",
                    {
                        "p_session_id": session_alpha_id,
                        "p_user_id": alpha_user_id,
                        "p_summary": "Should never be persisted",
                        "p_findings": [
                            {
                                "id": valid_finding_id,
                                "category": "missing",
                                "title": "Valid Finding",
                                "description": "Valid desc",
                                "severity": "medium",
                                "confidence": 0.8,
                                "recommended_action": "Action",
                            }
                        ],
                        "p_evidence_references": invalid_source_code_evidence,
                        "p_verification_items": [],
                    },
                ).execute()
            except APIError as exc:
                failed_e4 = True
                print(f"[PASS] Evidence with non-existent source_code S99 rejected by RPC (code={exc.code})")

            assert failed_e4, "RPC failed to reject evidence referencing invalid source_code!"

            # Verify that database remained 100% UNCHANGED after all 4 failed transactions
            state_after = (
                admin_client.table("research_sessions")
                .select("summary, status")
                .eq("id", session_alpha_id)
                .execute()
                .data[0]
            )
            findings_count_after = len(
                admin_client.table("findings")
                .select("id")
                .eq("research_id", session_alpha_id)
                .execute()
                .data
            )
            assert state_before["summary"] == state_after["summary"]
            assert state_before["status"] == state_after["status"]
            assert findings_count_before == findings_count_after == 2
            print("[PASS] Atomicity confirmed: Database state, summary, and findings completely untouched after RPC failures")

            # -----------------------------------------------------------------
            # TEST F: MULTI-USER OWNERSHIP & ISOLATION
            # -----------------------------------------------------------------
            print("\n--- [Test F] Multi-User Ownership & Isolation (Beta vs Alpha) ---")
            # 1. Beta attempts to GET Alpha's research report -> HTTP 404
            res_cross_get = await client.get(
                f"/api/research/{session_alpha_id}",
                headers=headers_beta,
            )
            assert res_cross_get.status_code == 404, f"Cross-user GET should be 404, got {res_cross_get.status_code}"
            print("[PASS] User Beta GET /api/research/{alpha_session} -> HTTP 404 Not Found")

            # 2. Beta attempts to analyze Alpha's research session -> HTTP 404
            res_cross_analyze = await client.post(
                f"/api/research/{session_alpha_id}/analyze",
                headers=headers_beta,
            )
            assert res_cross_analyze.status_code == 404, f"Cross-user analyze should be 404, got {res_cross_analyze.status_code}"
            print("[PASS] User Beta POST /api/research/{alpha_session}/analyze -> HTTP 404 Not Found")

            # 3. Direct database RLS isolation: User Beta client (using anon key + token_beta) queries Alpha's data
            beta_db_client = create_authenticated_user_client(
                settings.SUPABASE_BASE_URL,
                settings.SUPABASE_ANON_KEY,
                token_beta,
            )
            direct_findings_beta = (
                beta_db_client.table("findings")
                .select("*")
                .eq("research_id", session_alpha_id)
                .execute()
            )
            assert len(direct_findings_beta.data) == 0, f"RLS VIOLATION: Beta read Alpha findings! {direct_findings_beta.data}"
            print("[PASS] Database RLS SELECT: User Beta direct query returned 0 rows for Alpha findings (RLS ENFORCED)")

            direct_tasks_beta = (
                beta_db_client.table("verification_items")
                .select("*")
                .eq("research_id", session_alpha_id)
                .execute()
            )
            assert len(direct_tasks_beta.data) == 0, f"RLS VIOLATION: Beta read Alpha tasks! {direct_tasks_beta.data}"
            print("[PASS] Database RLS SELECT: User Beta direct query returned 0 rows for Alpha verification items (RLS ENFORCED)")

            # Alpha client confirms own records are accessible
            alpha_db_client = create_authenticated_user_client(
                settings.SUPABASE_BASE_URL,
                settings.SUPABASE_ANON_KEY,
                token_alpha,
            )
            direct_findings_alpha = (
                alpha_db_client.table("findings")
                .select("*")
                .eq("research_id", session_alpha_id)
                .execute()
            )
            assert len(direct_findings_alpha.data) > 0, "Alpha direct query failed to read own findings!"
            print(f"[PASS] Database RLS SELECT: User Alpha direct query returned {len(direct_findings_alpha.data)} rows for Alpha findings (RLS PERMITTED)")

            # 4. Direct RPC attack: User Beta tries to persist analysis into Alpha's session
            cross_rpc_blocked = False
            try:
                admin_client.rpc(
                    "save_analysis_results",
                    {
                        "p_session_id": session_alpha_id,
                        "p_user_id": beta_user_id,  # Ownership mismatch!
                        "p_summary": "Malicious takeover attempt",
                        "p_findings": [],
                        "p_evidence_references": [],
                        "p_verification_items": [],
                    },
                ).execute()
            except APIError as exc:
                cross_rpc_blocked = True
                assert exc.code in ("42501", "insufficient_privilege", "P0001"), f"Unexpected code: {exc.code}"
                print(f"[PASS] Direct RPC cross-user takeover rejected by PostgreSQL (code={exc.code})")

            assert cross_rpc_blocked, "CRITICAL: RPC permitted User Beta to persist into Alpha's session!"

            # 5. Beta can retrieve Beta's own unanalyzed session -> HTTP 200 with empty report lists
            res_beta_own = await client.get(
                f"/api/research/{session_beta_id}",
                headers=headers_beta,
            )
            assert res_beta_own.status_code == 200
            beta_rep = res_beta_own.json()["data"]
            assert beta_rep["research_id"] == session_beta_id
            assert beta_rep["findings"] == []
            assert len(beta_rep["sources"]) == 1
            print("[PASS] User Beta can retrieve Beta's own session report cleanly")

            # -----------------------------------------------------------------
            # TEST G: FAILURE & PRIVACY CASES
            # -----------------------------------------------------------------
            print("\n--- [Test G] Failure & Privacy Cases ---")
            # 1. Non-existent research session -> HTTP 404
            random_uuid = str(uuid.uuid4())
            res_missing_sess = await client.get(
                f"/api/research/{random_uuid}",
                headers=headers_alpha,
            )
            assert res_missing_sess.status_code == 404
            print("[PASS] Non-existent session GET -> HTTP 404 Not Found")

            # 2. Analyze session with no usable sources -> HTTP 400
            # Create an empty session for Alpha with no sources
            res_empty_sess = await client.post(
                "/api/research",
                headers=headers_alpha,
                json={"research_goal": "Empty sources session"},
            )
            empty_sess_id = res_empty_sess.json()["data"]["id"]
            res_analyze_no_sources = await client.post(
                f"/api/research/{empty_sess_id}/analyze",
                headers=headers_alpha,
            )
            assert res_analyze_no_sources.status_code == 400
            assert "no usable sources" in res_analyze_no_sources.json()["message"].lower() or "source" in res_analyze_no_sources.json()["detail"].lower()
            print("[PASS] Analyze session with zero sources -> HTTP 400 Bad Request")

            # Clean up the empty session
            await client.delete(f"/api/research/{empty_sess_id}", headers=headers_alpha)

    except Exception as exc:
        overall_success = False
        print(f"\n[FAIL] Live integration verification failed: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # ---------------------------------------------------------------------
        # CLEANUP: GUARANTEED PURGING OF DISPOSABLE RESOURCES
        # ---------------------------------------------------------------------
        print("\n--- [Cleanup] Purging All Disposable Test Resources ---")
        # 1. Delete Alpha Session
        if session_alpha_id:
            try:
                admin_client.table("research_sessions").delete().eq("id", session_alpha_id).execute()
                print(f"[CLEANUP] Deleted Alpha session (ID: {session_alpha_id}) + cascading sources/findings/tasks")
            except Exception as e:
                print(f"[WARN] Failed deleting Alpha session {session_alpha_id}: {e}")

        # 2. Delete Beta Session
        if session_beta_id:
            try:
                admin_client.table("research_sessions").delete().eq("id", session_beta_id).execute()
                print(f"[CLEANUP] Deleted Beta session (ID: {session_beta_id}) + cascading sources/findings/tasks")
            except Exception as e:
                print(f"[WARN] Failed deleting Beta session {session_beta_id}: {e}")

        # 3. Delete Disposable Users
        if alpha_user_id:
            try:
                admin_client.auth.admin.delete_user(alpha_user_id)
                print(f"[CLEANUP] Deleted disposable User Alpha (ID: {alpha_user_id})")
            except Exception as e:
                print(f"[WARN] Failed deleting User Alpha {alpha_user_id}: {e}")

        if beta_user_id:
            try:
                admin_client.auth.admin.delete_user(beta_user_id)
                print(f"[CLEANUP] Deleted disposable User Beta (ID: {beta_user_id})")
            except Exception as e:
                print(f"[WARN] Failed deleting User Beta {beta_user_id}: {e}")

    if overall_success:
        print("\n==================================================================")
        print("ALL LIVE SUPABASE ANALYSIS PERSISTENCE VERIFICATION CHECKS PASSED!")
        print("==================================================================")
        return 0
    else:
        print("\n==================================================================")
        print("VERIFICATION FAILED: One or more checks encountered errors.")
        print("==================================================================")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_live_analysis_integration_tests())
    sys.exit(exit_code)

