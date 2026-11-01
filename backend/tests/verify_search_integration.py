"""ClarityX End-to-End Live Supabase Search Integration & Capacity Verification Script (Phase 5.4).

Tests the complete search discovery, deduplication, partial failure, multi-user isolation,
and database trigger capacity enforcement lifecycle against real live Supabase:
1. Disposable test users (Alpha and Beta) created via Supabase Admin API.
2. Real user authentication & JWT acquisition via public client.
3. Scenario A: Successful search discovery and persistence (sequential source codes S1, preview truncation, no content leak).
4. Scenario B: Deduplication (both cross-batch and in-batch duplicate URLs correctly skipped).
5. Scenario C: Partial failure handling (resilience when extraction fails for a candidate).
6. Scenario D: Multi-user isolation & authentication (unauthorized access returns 401, cross-user search returns 404).
7. Scenario E: Hard source capacity enforcement (API-level 400 rejection and direct Supabase database trigger check violation on 6th source).
8. Scenario F: Cascade deletion and guaranteed cleanup in finally block.
"""

import asyncio
from datetime import datetime, timezone
import io
from pathlib import Path
import sys
import uuid
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, patch

# Ensure backend root directory is in sys.path for direct script execution
backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from httpx import ASGITransport, AsyncClient
from postgrest.exceptions import APIError
from supabase import create_client

from app.core.config import get_settings
from app.database.supabase import get_supabase_client
from app.main import create_app
from app.schemas.source import WebsiteExtractionResult
from app.services.search_service import DuckDuckGoSearchService, SearchResultItem


async def run_search_integration_tests() -> int:
    settings = get_settings()
    admin_client = get_supabase_client()

    # Generate unique run ID and disposable credentials
    run_id = uuid.uuid4().hex[:8]
    email_alpha = f"audit_search_alpha_{run_id}@clarityx.dev"
    email_beta = f"audit_search_beta_{run_id}@clarityx.dev"
    test_password = f"P@ssword_{uuid.uuid4().hex[:12]}!"

    alpha_user_id: Optional[str] = None
    beta_user_id: Optional[str] = None
    session_alpha_id: Optional[str] = None
    session_beta_id: Optional[str] = None

    overall_success = True
    cleanup_success = True

    print("==================================================================")
    print(f"CLARITYX LIVE SUPABASE SEARCH INTEGRATION TEST (Run ID: {run_id})")
    print("==================================================================")

    try:
        # ---------------------------------------------------------------------
        # STAGE 1: PROVISION DISPOSABLE TEST USERS & SESSIONS
        # ---------------------------------------------------------------------
        print("\n--- [Stage 1] Provisioning Disposable Test Users & Real JWTs ---")
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

        # Authenticate both users via public client using SUPABASE_ANON_KEY to obtain real JWTs
        public_client = create_client(settings.SUPABASE_BASE_URL, settings.SUPABASE_ANON_KEY)

        session_alpha = public_client.auth.sign_in_with_password({
            "email": email_alpha,
            "password": test_password,
        })
        token_alpha = session_alpha.session.access_token
        assert token_alpha and len(token_alpha) > 20
        print("[PASS] User Alpha authenticated via public client (JWT acquired)")

        session_beta = public_client.auth.sign_in_with_password({
            "email": email_beta,
            "password": test_password,
        })
        token_beta = session_beta.session.access_token
        assert token_beta and len(token_beta) > 20
        print("[PASS] User Beta authenticated via public client (JWT acquired)")

        headers_alpha = {"Authorization": f"Bearer {token_alpha}"}
        headers_beta = {"Authorization": f"Bearer {token_beta}"}

        # Initialize FastAPI ASGI client
        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create research sessions
            res_alpha_sess = await client.post(
                "/api/research",
                headers=headers_alpha,
                json={"research_goal": f"Quantum Computing Fault Tolerance ({run_id})"},
            )
            assert res_alpha_sess.status_code == 201, f"Failed creating Alpha session: {res_alpha_sess.text}"
            session_alpha_id = res_alpha_sess.json()["data"]["id"]
            print(f"[PASS] Alpha research session created (ID: {session_alpha_id})")

            res_beta_sess = await client.post(
                "/api/research",
                headers=headers_beta,
                json={"research_goal": f"Isolation Session for Beta ({run_id})"},
            )
            assert res_beta_sess.status_code == 201, f"Failed creating Beta session: {res_beta_sess.text}"
            session_beta_id = res_beta_sess.json()["data"]["id"]
            print(f"[PASS] Beta research session created (ID: {session_beta_id})")

            # -----------------------------------------------------------------
            # SCENARIO A: SUCCESSFUL SEARCH DISCOVERY & PERSISTENCE
            # -----------------------------------------------------------------
            print("\n--- [Scenario A] Successful Search Discovery & Persistence ---")
            url_a1 = f"https://search-alpha-{run_id}.example.com/quantum-optics"
            long_content_a1 = (
                f"Extracted content for Quantum Optics ({run_id}). "
                "Detailed discussion of entangled photon sources, squeezed states of light, and Bell inequality violations. "
                "The research demonstrates continuous variable quantum key distribution across free-space optical links. "
                "Experimental coherence times exceeded theoretical expectations under ambient turbulence conditions."
            )

            mock_search_results_a = [
                SearchResultItem(
                    title="Quantum Optics in 2026",
                    url=url_a1,
                    snippet="Entangled photon sources and free-space quantum key distribution.",
                ),
            ]

            async def mock_extract_a(target_url: str) -> WebsiteExtractionResult:
                return WebsiteExtractionResult(
                    url=target_url,
                    title="Quantum Optics in 2026",
                    extracted_content=long_content_a1,
                    extraction_method="trafilatura",
                    extraction_status="success",
                )

            with (
                patch.object(DuckDuckGoSearchService, "search", new_callable=AsyncMock) as mock_ddgs,
                patch("app.services.search_orchestrator.extract_website_content", new_callable=AsyncMock) as mock_extract,
            ):
                mock_ddgs.return_value = mock_search_results_a
                mock_extract.side_effect = mock_extract_a

                res_search_a = await client.post(
                    f"/api/research/{session_alpha_id}/sources/search",
                    headers=headers_alpha,
                    json={"query": "quantum optics", "max_results": 2},
                )

            assert res_search_a.status_code == 200, f"Search failed: {res_search_a.text}"
            data_a = res_search_a.json()["data"]
            assert data_a["total_found"] == 1
            assert data_a["attempted_count"] == 1
            assert data_a["persisted_count"] == 1
            assert data_a["skipped_count"] == 0
            assert data_a["failed_count"] == 0
            assert len(data_a["sources"]) == 1

            persisted_s1 = data_a["sources"][0]
            assert persisted_s1["source_code"] == "S1"
            assert persisted_s1["url"] == url_a1
            assert persisted_s1["source_type"] == "website"
            assert "content_preview" in persisted_s1
            assert "extracted_content" not in persisted_s1, "Full extracted_content leaked in search preview!"
            assert len(persisted_s1["content_preview"]) <= 253
            print(f"[PASS] Scenario A API: S1 persisted with code={persisted_s1['source_code']}, preview length={len(persisted_s1['content_preview'])}")

            # Direct Supabase database verification
            db_query_a = (
                admin_client.table("sources")
                .select("id, source_code, url, source_type, extracted_content, extraction_status")
                .eq("research_id", session_alpha_id)
                .execute()
            )
            assert len(db_query_a.data) == 1
            assert db_query_a.data[0]["source_code"] == "S1"
            assert db_query_a.data[0]["extracted_content"] == long_content_a1
            print(f"[PASS] Scenario A DB: Source S1 verified directly in Supabase table (ID: {db_query_a.data[0]['id']})")

            # -----------------------------------------------------------------
            # SCENARIO B: DEDUPLICATION (IN-SESSION & IN-BATCH)
            # -----------------------------------------------------------------
            print("\n--- [Scenario B] Deduplication (In-Session & In-Batch) ---")
            url_b_dup_session = url_a1  # Already in session (S1)
            url_b_topological = f"https://search-alpha-{run_id}.example.com/topological-matter"
            url_b_topological_tracking = f"https://search-alpha-{run_id}.example.com/topological-matter?utm_source=twitter&ref=feed#abstract"
            url_b_cryogenic = f"https://search-alpha-{run_id}.example.com/cryogenic-control"

            mock_search_results_b = [
                SearchResultItem(title="Quantum Optics Duplicate", url=url_b_dup_session, snippet="Duplicate snippet"),
                SearchResultItem(title="Topological Matter With Params", url=url_b_topological_tracking, snippet="Topological 1"),
                SearchResultItem(title="Topological Matter Clean", url=url_b_topological, snippet="Topological 2 (duplicate of item above)"),
                SearchResultItem(title="Cryogenic Control", url=url_b_cryogenic, snippet="Cryogenic microwave controllers"),
            ]

            async def mock_extract_b(target_url: str) -> WebsiteExtractionResult:
                title = "Topological Matter" if "topological" in target_url else "Cryogenic Control"
                return WebsiteExtractionResult(
                    url=target_url,
                    title=title,
                    extracted_content=f"Extracted content for {title} ({run_id}). Benchmark metrics and decoherence bounds.",
                    extraction_method="trafilatura",
                    extraction_status="success",
                )

            with (
                patch.object(DuckDuckGoSearchService, "search", new_callable=AsyncMock) as mock_ddgs,
                patch("app.services.search_orchestrator.extract_website_content", new_callable=AsyncMock) as mock_extract,
            ):
                mock_ddgs.return_value = mock_search_results_b
                mock_extract.side_effect = mock_extract_b

                res_search_b = await client.post(
                    f"/api/research/{session_alpha_id}/sources/search",
                    headers=headers_alpha,
                    json={"query": "topological quantum", "max_results": 4},
                )

            assert res_search_b.status_code == 200, f"Deduplication search failed: {res_search_b.text}"
            data_b = res_search_b.json()["data"]
            assert data_b["total_found"] == 4
            assert data_b["skipped_count"] == 2
            assert data_b["persisted_count"] == 2

            skipped_reasons = {item["reason"] for item in data_b["skipped"]}
            assert "already_stored" in skipped_reasons, f"Expected 'already_stored' in skipped reasons: {skipped_reasons}"
            assert "duplicate_result" in skipped_reasons, f"Expected 'duplicate_result' in skipped reasons: {skipped_reasons}"

            b_codes = [s["source_code"] for s in data_b["sources"]]
            assert b_codes == ["S2", "S3"], f"Expected sequential codes ['S2', 'S3'], got {b_codes}"
            print(f"[PASS] Scenario B API: 2 duplicates correctly skipped ({skipped_reasons}), new sources persisted as {b_codes}")

            # Direct Supabase database verification
            db_query_b = (
                admin_client.table("sources")
                .select("source_code, url")
                .eq("research_id", session_alpha_id)
                .order("source_code")
                .execute()
            )
            all_b_codes = [r["source_code"] for r in db_query_b.data]
            assert all_b_codes == ["S1", "S2", "S3"], f"DB records mismatch: expected ['S1', 'S2', 'S3'], got {all_b_codes}"
            print(f"[PASS] Scenario B DB: Database strictly contains sequential sources {all_b_codes} with zero duplicate insertions")

            # -----------------------------------------------------------------
            # SCENARIO C: PARTIAL FAILURE HANDLING
            # -----------------------------------------------------------------
            print("\n--- [Scenario C] Partial Failure Handling (Extraction Errors) ---")
            url_c_good = f"https://search-alpha-{run_id}.example.com/trapped-ions"
            url_c_bad = f"https://search-alpha-{run_id}.example.com/broken-page"

            mock_search_results_c = [
                SearchResultItem(title="Trapped Ions Computing", url=url_c_good, snippet="High fidelity two-qubit gates"),
                SearchResultItem(title="Broken Page Link", url=url_c_bad, snippet="Scraper error snippet"),
            ]

            async def mock_extract_c(target_url: str) -> WebsiteExtractionResult:
                if target_url == url_c_good:
                    return WebsiteExtractionResult(
                        url=target_url,
                        title="Trapped Ions Computing",
                        extracted_content=f"Extracted content for Trapped Ions ({run_id}). High fidelity two-qubit gates.",
                        extraction_method="trafilatura",
                        extraction_status="success",
                    )
                # Simulate extraction failure
                return WebsiteExtractionResult(
                    url=target_url,
                    title="Broken Page Link",
                    extracted_content="",
                    extraction_method="trafilatura",
                    extraction_status="failed",
                    error_message="HTTP 502 Bad Gateway from target website.",
                )

            with (
                patch.object(DuckDuckGoSearchService, "search", new_callable=AsyncMock) as mock_ddgs,
                patch("app.services.search_orchestrator.extract_website_content", new_callable=AsyncMock) as mock_extract,
            ):
                mock_ddgs.return_value = mock_search_results_c
                mock_extract.side_effect = mock_extract_c

                res_search_c = await client.post(
                    f"/api/research/{session_alpha_id}/sources/search",
                    headers=headers_alpha,
                    json={"query": "trapped ions", "max_results": 2},
                )

            assert res_search_c.status_code == 200, f"Partial failure search failed: {res_search_c.text}"
            data_c = res_search_c.json()["data"]
            assert data_c["total_found"] == 2
            assert data_c["attempted_count"] == 2
            assert data_c["persisted_count"] == 1
            assert data_c["failed_count"] == 1
            assert len(data_c["sources"]) == 1
            assert data_c["sources"][0]["source_code"] == "S4"
            assert data_c["sources"][0]["url"] == url_c_good

            assert len(data_c["failed"]) == 1
            assert data_c["failed"][0]["url"] == url_c_bad
            assert "HTTP 502 Bad Gateway" in data_c["failed"][0]["error"]
            print(f"[PASS] Scenario C API: Good candidate persisted as S4; failed candidate accurately reported in failed[]")

            # Direct Supabase database verification
            db_query_c = (
                admin_client.table("sources")
                .select("source_code, url")
                .eq("research_id", session_alpha_id)
                .order("source_code")
                .execute()
            )
            all_c_codes = [r["source_code"] for r in db_query_c.data]
            assert all_c_codes == ["S1", "S2", "S3", "S4"], f"Expected ['S1', 'S2', 'S3', 'S4'], got {all_c_codes}"
            print(f"[PASS] Scenario C DB: Supabase records confirmed {all_c_codes}; failed extraction was not persisted")

            # -----------------------------------------------------------------
            # SCENARIO D: AUTHENTICATION AND MULTI-USER ISOLATION
            # -----------------------------------------------------------------
            print("\n--- [Scenario D] Authentication & Multi-User Ownership Isolation ---")

            # 1. Unauthenticated request -> HTTP 401
            res_unauth = await client.post(
                f"/api/research/{session_alpha_id}/sources/search",
                json={"query": "unauthenticated attack"},
            )
            assert res_unauth.status_code == 401, f"Expected 401 for unauthenticated search, got {res_unauth.status_code}"
            print("[PASS] Unauthenticated search request rejected with HTTP 401 Unauthorized")

            # 2. User Beta attempts search on User Alpha's session -> HTTP 404
            res_beta_search = await client.post(
                f"/api/research/{session_alpha_id}/sources/search",
                headers=headers_beta,
                json={"query": "cross user attack"},
            )
            assert res_beta_search.status_code == 404, f"Expected 404 for Beta search on Alpha session, got {res_beta_search.status_code}"
            print("[PASS] User Beta POST /api/research/{alpha_session}/sources/search -> HTTP 404 Not Found")

            # 3. User Beta attempts listing Alpha's sources -> HTTP 404
            res_beta_list = await client.get(
                f"/api/research/{session_alpha_id}/sources",
                headers=headers_beta,
            )
            assert res_beta_list.status_code == 404, f"Expected 404 for Beta listing Alpha sources, got {res_beta_list.status_code}"
            print("[PASS] User Beta GET /api/research/{alpha_session}/sources -> HTTP 404 Not Found")

            # 4. User Beta attempts retrieving Alpha's S1 source detail -> HTTP 404
            s1_id = db_query_a.data[0]["id"]
            res_beta_detail = await client.get(
                f"/api/research/{session_alpha_id}/sources/{s1_id}",
                headers=headers_beta,
            )
            assert res_beta_detail.status_code == 404, f"Expected 404 for Beta accessing Alpha source detail, got {res_beta_detail.status_code}"
            print("[PASS] User Beta GET /api/research/{alpha_session}/sources/{s1_id} -> HTTP 404 Not Found")

            # 5. User Beta performs search on own session -> HTTP 200, persists as Beta's S1
            url_beta_item = f"https://search-beta-{run_id}.example.com/beta-article"
            with (
                patch.object(DuckDuckGoSearchService, "search", new_callable=AsyncMock) as mock_ddgs,
                patch("app.services.search_orchestrator.extract_website_content", new_callable=AsyncMock) as mock_extract,
            ):
                mock_ddgs.return_value = [
                    SearchResultItem(title="Beta Topic", url=url_beta_item, snippet="Beta snippet")
                ]
                mock_extract.return_value = WebsiteExtractionResult(
                    url=url_beta_item,
                    title="Beta Topic",
                    extracted_content="Beta specific research content.",
                    extraction_method="trafilatura",
                    extraction_status="success",
                )

                res_beta_own_search = await client.post(
                    f"/api/research/{session_beta_id}/sources/search",
                    headers=headers_beta,
                    json={"query": "beta topic", "max_results": 1},
                )

            assert res_beta_own_search.status_code == 200, f"Beta own search failed: {res_beta_own_search.text}"
            beta_data = res_beta_own_search.json()["data"]
            assert beta_data["persisted_count"] == 1
            assert beta_data["sources"][0]["source_code"] == "S1"
            print("[PASS] User Beta searches own session successfully -> persisted as Beta S1")

            # -----------------------------------------------------------------
            # SCENARIO E: SOURCE CAPACITY ENFORCEMENT & DATABASE TRIGGER
            # -----------------------------------------------------------------
            print("\n--- [Scenario E] Source Capacity Enforcement & Database Trigger ---")

            # Alpha currently has 4 sources (S1..S4). Add 5th source via search to reach max quota (5).
            url_e5 = f"https://search-alpha-{run_id}.example.com/qubit-coupler"
            url_e6_overflow = f"https://search-alpha-{run_id}.example.com/qubit-readout"

            mock_search_results_e = [
                SearchResultItem(title="Qubit Coupler (5th Source)", url=url_e5, snippet="Fifth source snippet"),
                SearchResultItem(title="Qubit Readout (6th Overflow)", url=url_e6_overflow, snippet="Sixth source snippet"),
            ]

            async def mock_extract_e(target_url: str) -> WebsiteExtractionResult:
                return WebsiteExtractionResult(
                    url=target_url,
                    title="Fifth Source",
                    extracted_content="Content for fifth source.",
                    extraction_method="trafilatura",
                    extraction_status="success",
                )

            with (
                patch.object(DuckDuckGoSearchService, "search", new_callable=AsyncMock) as mock_ddgs,
                patch("app.services.search_orchestrator.extract_website_content", new_callable=AsyncMock) as mock_extract,
            ):
                mock_ddgs.return_value = mock_search_results_e
                mock_extract.side_effect = mock_extract_e

                res_search_e = await client.post(
                    f"/api/research/{session_alpha_id}/sources/search",
                    headers=headers_alpha,
                    json={"query": "qubit coupler", "max_results": 2},
                )

            assert res_search_e.status_code == 200
            data_e = res_search_e.json()["data"]
            assert data_e["persisted_count"] == 1
            assert data_e["sources"][0]["source_code"] == "S5"
            assert data_e["skipped_count"] == 1
            assert data_e["skipped"][0]["reason"] == "capacity_exceeded"
            print("[PASS] 5th source persisted as S5; candidate beyond quota skipped with reason='capacity_exceeded'")

            # 1. Verify Application-Level Check Rejection at Capacity 5
            res_full_capacity = await client.post(
                f"/api/research/{session_alpha_id}/sources/search",
                headers=headers_alpha,
                json={"query": "further discovery"},
            )
            assert res_full_capacity.status_code == 400
            err_json = res_full_capacity.json()
            assert "capacity reached" in err_json["message"].lower() or "capacity" in err_json["detail"].lower()
            print(f"[PASS] Application API rejected search at capacity (5 sources) -> HTTP 400 Bad Request")

            # 2. Verify Actual PostgreSQL Database Trigger (trg_enforce_source_capacity_limit)
            print("  Testing Supabase PostgreSQL Trigger directly via database client (no mocks)...")
            trigger_blocked = False
            trigger_error_msg = ""
            try:
                # Direct SQL insert bypasses application layer and goes straight to Supabase PostgreSQL table
                admin_client.table("sources").insert({
                    "research_id": session_alpha_id,
                    "source_code": "S6",
                    "source_type": "website",
                    "title": "Trigger Direct 6th Source Attack",
                    "extracted_content": "Testing PostgreSQL trigger capacity enforcement directly in Supabase.",
                    "extraction_status": "success",
                }).execute()
            except APIError as exc:
                trigger_blocked = True
                trigger_error_msg = str(getattr(exc, "message", exc)).lower()
            except Exception as exc:
                trigger_blocked = True
                trigger_error_msg = str(exc).lower()

            assert trigger_blocked is True, "CRITICAL DEFECT: Direct database insert bypassed capacity limit!"
            assert (
                "source capacity limit reached" in trigger_error_msg
                or "check_violation" in trigger_error_msg
                or "23514" in trigger_error_msg
            ), f"Unexpected trigger error response: {trigger_error_msg}"
            print(f"[PASS] Supabase PostgreSQL Database Trigger executed and BLOCKED 6th insert: {trigger_error_msg}")

            # Confirm Supabase table count remains strictly 5
            final_sources_check = (
                admin_client.table("sources")
                .select("source_code")
                .eq("research_id", session_alpha_id)
                .execute()
            )
            final_codes = [r["source_code"] for r in final_sources_check.data]
            assert len(final_codes) == 5, f"Expected exactly 5 sources, got {len(final_codes)}: {final_codes}"
            assert final_codes == ["S1", "S2", "S3", "S4", "S5"]
            print(f"[PASS] Database state verified strictly at quota: {final_codes}")

            # -----------------------------------------------------------------
            # SCENARIO F: RESEARCH SESSION CASCADE DELETION
            # -----------------------------------------------------------------
            print("\n--- [Scenario F] Research Session Cascade Deletion ---")
            res_del_alpha = await client.delete(
                f"/api/research/{session_alpha_id}",
                headers=headers_alpha,
            )
            assert res_del_alpha.status_code == 200, f"Failed deleting Alpha session: {res_del_alpha.text}"
            print("[PASS] Alpha research session deleted via API")

            # Verify PostgreSQL ON DELETE CASCADE purged all 5 sources
            cascaded_query = (
                admin_client.table("sources")
                .select("id")
                .eq("research_id", session_alpha_id)
                .execute()
            )
            assert len(cascaded_query.data) == 0, f"CASCADE FAILURE: Sources still present in database: {cascaded_query.data}"
            print("[PASS] All 5 sources for Alpha successfully purged via PostgreSQL ON DELETE CASCADE")

            # Verify Beta's session and Beta's S1 source remain untouched
            beta_session_check = (
                admin_client.table("research_sessions")
                .select("id")
                .eq("id", session_beta_id)
                .execute()
            )
            assert len(beta_session_check.data) == 1, "Beta session was unexpectedly deleted!"

            beta_sources_check = (
                admin_client.table("sources")
                .select("id")
                .eq("research_id", session_beta_id)
                .execute()
            )
            assert len(beta_sources_check.data) == 1, "Beta source was unexpectedly deleted!"
            print("[PASS] User Beta session and source verified completely intact")

    except Exception as exc:
        print(f"\n[FAIL] Live Search Integration test failed: {type(exc).__name__}: {exc}")
        overall_success = False
        raise

    finally:
        # ---------------------------------------------------------------------
        # CLEANUP: GUARANTEED PURGE OF DISPOSABLE USERS & SESSIONS
        # ---------------------------------------------------------------------
        print("\n--- [Cleanup] Purging Disposable Test Resources by Exact UUID ---")

        # 1. Purge Alpha session if still lingering
        if session_alpha_id:
            try:
                admin_client.table("research_sessions").delete().eq("id", session_alpha_id).execute()
            except Exception as exc:
                print(f"[WARN] Alpha session cleanup: {type(exc).__name__}")

        # 2. Purge Beta session
        if session_beta_id:
            try:
                admin_client.table("research_sessions").delete().eq("id", session_beta_id).execute()
                print(f"[CLEANUP] Deleted Beta session ({session_beta_id})")
            except Exception as exc:
                print(f"[WARN] Beta session cleanup: {type(exc).__name__}")
                cleanup_success = False

        # 3. Purge User Alpha by exact UUID
        if alpha_user_id:
            try:
                admin_client.auth.admin.delete_user(alpha_user_id)
                print(f"[CLEANUP] Deleted disposable User Alpha ({alpha_user_id})")
            except Exception as exc:
                print(f"[FAIL] Error deleting Alpha user: {type(exc).__name__}")
                cleanup_success = False

        # 4. Purge User Beta by exact UUID
        if beta_user_id:
            try:
                admin_client.auth.admin.delete_user(beta_user_id)
                print(f"[CLEANUP] Deleted disposable User Beta ({beta_user_id})")
            except Exception as exc:
                print(f"[FAIL] Error deleting Beta user: {type(exc).__name__}")
                cleanup_success = False

    print("\n==================================================================")
    if overall_success and cleanup_success:
        print("ALL LIVE SEARCH INTEGRATION & CAPACITY VERIFICATION CHECKS PASSED!")
        print("==================================================================")
        return 0
    else:
        print("LIVE SEARCH INTEGRATION TESTS OR CLEANUP FAILED!")
        print("==================================================================")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_search_integration_tests())
    sys.exit(exit_code)
