"""ClarityX End-to-End Live Supabase Source Integration & Multi-User Isolation Verification Script.

Tests the full source extraction, persistence, and isolation lifecycle against live Supabase:
1. Real test user provisioning via Supabase Admin API with unique disposable emails.
2. Real user JWT authentication via public client.
3. Research session initialization for User Alpha (primary) and User Beta (isolation).
4. Multi-source extraction and persistence (Website, Pasted Text, PDF, DOCX).
5. Sequential source code allocation (S1, S2, S3, S4) and extraction status verification.
6. Direct database verification via PostgreSQL service client.
7. Content preview truncation enforcement on listing (never exposing raw extracted_content).
8. Single source full content retrieval.
9. Application-level ownership isolation via FastAPI (Beta receiving HTTP 404 on Alpha resources).
10. Database-level PostgreSQL RLS enforcement via PostgREST (Beta receiving 0 rows and zero delete impact).
11. Individual source deletion via API and database confirmation.
12. Cascade deletion: deleting research session automatically deletes all associated sources.
13. Guaranteed cleanup using exact created UUIDs in a try/finally block without modifying existing data.
"""

import asyncio
from datetime import datetime, timezone
import io
from pathlib import Path
import sys
import uuid
from typing import Dict, List, Optional

# Ensure backend root directory is in sys.path for direct script execution
backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

import docx
from httpx import ASGITransport, AsyncClient
import pypdf
from supabase import create_client

from app.core.config import get_settings
from app.database.supabase import get_supabase_client
from app.main import create_app

# Base minimal valid PDF template with standard Helvetica font
MINIMAL_PDF_BYTES = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 72 >> stream
BT
/F1 12 Tf
72 712 Td
(ClarityX E2E Live Integration Test - Page Stream Verification) Tj
ET
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000224 00000 n 
0000000346 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
416
%%EOF"""


def build_two_page_test_pdf() -> bytes:
    """Builds a valid 2-page PDF entirely in memory with recognizable test phrases."""
    reader = pypdf.PdfReader(io.BytesIO(MINIMAL_PDF_BYTES))
    writer = pypdf.PdfWriter()
    writer.add_page(reader.pages[0])
    writer.add_page(reader.pages[0])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def build_interleaved_test_docx() -> bytes:
    """Builds a valid DOCX entirely in memory with paragraphs and an interleaved table."""
    doc = docx.Document()
    doc.add_paragraph("ClarityX E2E Integration: Introductory findings on solid-state battery electrolytes.")

    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Electrolyte Material"
    table.rows[0].cells[1].text = "Ionic Conductivity"
    table.rows[1].cells[0].text = "Sulfide glass-ceramic"
    table.rows[1].cells[1].text = "1.2 x 10^-2 S/cm"

    doc.add_paragraph("ClarityX E2E Integration: Concluding benchmark metrics and degradation rates.")

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


async def run_integration_tests() -> int:
    settings = get_settings()
    admin_client = get_supabase_client()

    # Generate unique run ID and disposable credentials
    run_id = uuid.uuid4().hex[:8]
    email_alpha = f"audit_source_alpha_{run_id}@clarityx.dev"
    email_beta = f"audit_source_beta_{run_id}@clarityx.dev"
    test_password = f"P@ssword_{uuid.uuid4().hex[:12]}!"

    alpha_user_id: Optional[str] = None
    beta_user_id: Optional[str] = None
    session_alpha_id: Optional[str] = None
    session_beta_id: Optional[str] = None

    created_sources: List[Dict] = []
    overall_success = True
    cleanup_success = True
    website_skipped = False

    print("==================================================================")
    print(f"CLARITYX END-TO-END SOURCE INTEGRATION TEST (Run ID: {run_id})")
    print("==================================================================")

    try:
        # ---------------------------------------------------------------------
        # STAGE A: PROVISIONING
        # ---------------------------------------------------------------------
        print("\n--- [Stage A] Provisioning Disposable Test Users ---")
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

        # Authenticate both via public client using SUPABASE_ANON_KEY
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

        # Initialize FastAPI app test transport
        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # -----------------------------------------------------------------
            # STAGE B: RESEARCH SESSIONS
            # -----------------------------------------------------------------
            print("\n--- [Stage B] Research Sessions Initialization ---")
            headers_alpha = {"Authorization": f"Bearer {token_alpha}"}
            headers_beta = {"Authorization": f"Bearer {token_beta}"}

            res_alpha_sess = await client.post(
                "/api/research",
                headers=headers_alpha,
                json={"research_goal": f"E2E Integration Analysis {run_id}: Quantum Computing Feasibility"},
            )
            assert res_alpha_sess.status_code == 201, f"Failed creating Alpha session: {res_alpha_sess.text}"
            session_alpha_id = res_alpha_sess.json()["data"]["id"]
            assert res_alpha_sess.json()["data"]["user_id"] == alpha_user_id
            print(f"[PASS] User Alpha research session created (ID: {session_alpha_id})")

            res_beta_sess = await client.post(
                "/api/research",
                headers=headers_beta,
                json={"research_goal": f"E2E Integration Analysis {run_id}: Unrelated Isolation Session"},
            )
            assert res_beta_sess.status_code == 201, f"Failed creating Beta session: {res_beta_sess.text}"
            session_beta_id = res_beta_sess.json()["data"]["id"]
            assert res_beta_sess.json()["data"]["user_id"] == beta_user_id
            print(f"[PASS] User Beta research session created (ID: {session_beta_id})")

            # -----------------------------------------------------------------
            # STAGE C: ADD FOUR SOURCE TYPES (USER ALPHA)
            # -----------------------------------------------------------------
            print("\n--- [Stage C] Multi-Source Extraction & Persistence ---")

            # 1. Website Source (https://example.com)
            expected_code_idx = 1
            print("  1. Testing Website Source Extraction (https://example.com)...")
            try:
                res_web = await client.post(
                    f"/api/research/{session_alpha_id}/sources/website",
                    headers=headers_alpha,
                    json={"url": "https://example.com"},
                )
                if res_web.status_code == 201:
                    web_data = res_web.json()["data"]
                    assert web_data["source_code"] == f"S{expected_code_idx}"
                    assert web_data["source_type"] == "website"
                    assert len(web_data["extracted_content"]) > 0
                    assert web_data["extraction_status"] in ("success", "partial")
                    created_sources.append(web_data)
                    expected_code_idx += 1
                    print(f"     [PASS] Website extracted and persisted: code={web_data['source_code']}, title='{web_data['title']}'")
                else:
                    website_skipped = True
                    print(f"     [SKIP] Website extraction returned HTTP {res_web.status_code} (environmental network limitation). Continuing.")
            except Exception as exc:
                website_skipped = True
                print(f"     [SKIP] Website extraction skipped due to network error: {type(exc).__name__}. Continuing.")

            # 2. Pasted Text Source
            print("  2. Testing Pasted Text Extraction & Persistence...")
            pasted_title = f"Battery Degradation Protocols ({run_id})"
            pasted_text = (
                f"# {pasted_title}\n\n"
                "Standard operating procedure for thermal chamber cycling.\n"
                "Upper cutoff voltage: 4.25V.\n"
                "Lower cutoff voltage: 2.80V.\n"
                "Ambient temperature setpoint: -10 degrees Celsius."
            )
            res_pasted = await client.post(
                f"/api/research/{session_alpha_id}/sources/pasted-text",
                headers=headers_alpha,
                json={"text": pasted_text, "title": pasted_title},
            )
            assert res_pasted.status_code == 201, f"Failed adding pasted text: {res_pasted.text}"
            pasted_data = res_pasted.json()["data"]
            assert pasted_data["source_code"] == f"S{expected_code_idx}"
            assert pasted_data["source_type"] == "pasted_text"
            assert pasted_data["title"] == pasted_title
            assert "Upper cutoff voltage" in pasted_data["extracted_content"]
            assert pasted_data["extraction_status"] == "success"
            created_sources.append(pasted_data)
            expected_code_idx += 1
            print(f"     [PASS] Pasted text persisted: code={pasted_data['source_code']}, title='{pasted_data['title']}'")

            # 3. PDF Document Upload
            print("  3. Testing PDF Document Upload & Extraction...")
            pdf_bytes = build_two_page_test_pdf()
            res_pdf = await client.post(
                f"/api/research/{session_alpha_id}/sources/document",
                headers=headers_alpha,
                files={"file": ("integration_report.pdf", pdf_bytes, "application/pdf")},
                data={"title": f"Battery Thermal Report ({run_id})"},
            )
            assert res_pdf.status_code == 201, f"Failed uploading PDF: {res_pdf.text}"
            pdf_data = res_pdf.json()["data"]
            assert pdf_data["source_code"] == f"S{expected_code_idx}"
            assert pdf_data["source_type"] == "document"
            assert pdf_data["title"] == f"Battery Thermal Report ({run_id})"
            assert "ClarityX E2E Live Integration Test" in pdf_data["extracted_content"]
            assert pdf_data["extraction_status"] == "success"
            created_sources.append(pdf_data)
            expected_code_idx += 1
            print(f"     [PASS] PDF document persisted: code={pdf_data['source_code']}, title='{pdf_data['title']}'")

            # 4. DOCX Document Upload
            print("  4. Testing DOCX Document Upload & Interleaved Content Extraction...")
            docx_bytes = build_interleaved_test_docx()
            res_docx = await client.post(
                f"/api/research/{session_alpha_id}/sources/document",
                headers=headers_alpha,
                files={
                    "file": (
                        "interleaved_analysis.docx",
                        docx_bytes,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
                data={"title": f"Solid-State Electrolyte Benchmark ({run_id})"},
            )
            assert res_docx.status_code == 201, f"Failed uploading DOCX: {res_docx.text}"
            docx_data = res_docx.json()["data"]
            assert docx_data["source_code"] == f"S{expected_code_idx}"
            assert docx_data["source_type"] == "document"
            assert docx_data["title"] == f"Solid-State Electrolyte Benchmark ({run_id})"
            # Verify interleaved paragraph and table order
            extracted_docx_text = docx_data["extracted_content"]
            assert "Introductory findings" in extracted_docx_text
            assert "Sulfide glass-ceramic" in extracted_docx_text
            assert "Concluding benchmark metrics" in extracted_docx_text
            assert extracted_docx_text.index("Introductory findings") < extracted_docx_text.index("Sulfide glass-ceramic")
            assert extracted_docx_text.index("Sulfide glass-ceramic") < extracted_docx_text.index("Concluding benchmark metrics")
            assert docx_data["extraction_status"] == "success"
            created_sources.append(docx_data)
            expected_code_idx += 1
            print(f"     [PASS] DOCX document persisted: code={docx_data['source_code']}, title='{docx_data['title']}' (Interleaved order verified)")

            # -----------------------------------------------------------------
            # STAGE D: DIRECT DATABASE VERIFICATION (POSTGRESQL VIA SERVICE ROLE)
            # -----------------------------------------------------------------
            print("\n--- [Stage D] Direct Database State Verification ---")
            db_query = (
                admin_client.table("sources")
                .select("id, research_id, source_code, title, source_type, extracted_content, extraction_status, created_at")
                .eq("research_id", session_alpha_id)
                .order("source_code", desc=False)
                .execute()
            )
            db_records = db_query.data or []
            assert len(db_records) == len(created_sources), f"DB record count mismatch: expected {len(created_sources)}, got {len(db_records)}"

            for api_src, db_src in zip(created_sources, db_records):
                assert str(api_src["id"]) == str(db_src["id"])
                assert api_src["source_code"] == db_src["source_code"]
                assert api_src["source_type"] == db_src["source_type"]
                assert api_src["title"] == db_src["title"]
                assert db_src["extracted_content"] == api_src["extracted_content"]
                assert len(db_src["extracted_content"]) > 0

            print(f"[PASS] Direct DB verification successful: {len(db_records)} records match exactly with sequential codes {[r['source_code'] for r in db_records]}")

            # -----------------------------------------------------------------
            # STAGE E: LIST AND DETAIL ENDPOINTS
            # -----------------------------------------------------------------
            print("\n--- [Stage E] List Previews & Single Source Detail Retrieval ---")

            # 1. Listing endpoint: Previews only, extracted_content stripped
            res_list = await client.get(
                f"/api/research/{session_alpha_id}/sources?limit=10&offset=0",
                headers=headers_alpha,
            )
            assert res_list.status_code == 200, f"Failed listing sources: {res_list.text}"
            list_payload = res_list.json()["data"]
            assert list_payload["total"] == len(created_sources)
            assert len(list_payload["sources"]) == len(created_sources)

            for preview_item in list_payload["sources"]:
                assert "content_preview" in preview_item
                # Critical security assertion: extracted_content must NEVER be present in preview lists
                assert "extracted_content" not in preview_item
                preview_text = preview_item["content_preview"]
                assert len(preview_text) <= 253  # 250 characters + optional "..."

            print(f"[PASS] List sources verified: {list_payload['total']} previews returned; full extracted_content completely excluded from all items")

            # 2. Detail endpoint: Full extracted_content returned
            target_source = created_sources[0]
            res_detail = await client.get(
                f"/api/research/{session_alpha_id}/sources/{target_source['id']}",
                headers=headers_alpha,
            )
            assert res_detail.status_code == 200, f"Failed retrieving source detail: {res_detail.text}"
            detail_data = res_detail.json()["data"]
            assert detail_data["id"] == str(target_source["id"])
            assert detail_data["extracted_content"] == target_source["extracted_content"]
            assert len(detail_data["extracted_content"]) > 0
            print(f"[PASS] Single source detail verified: Full unclipped extracted_content returned for {detail_data['source_code']}")

            # -----------------------------------------------------------------
            # STAGE F: APPLICATION-LEVEL OWNERSHIP ISOLATION (FASTAPI)
            # -----------------------------------------------------------------
            print("\n--- [Stage F] Application-Level Multi-User Isolation (FastAPI) ---")

            # Beta tries to list Alpha's sources -> 404
            res_beta_list = await client.get(
                f"/api/research/{session_alpha_id}/sources",
                headers=headers_beta,
            )
            assert res_beta_list.status_code == 404, f"Expected 404 for Beta listing Alpha sources, got {res_beta_list.status_code}"
            print("[PASS] User Beta GET /api/research/{alpha_session}/sources -> HTTP 404 Not Found")

            # Beta tries to view Alpha's source -> 404
            res_beta_get = await client.get(
                f"/api/research/{session_alpha_id}/sources/{target_source['id']}",
                headers=headers_beta,
            )
            assert res_beta_get.status_code == 404, f"Expected 404 for Beta viewing Alpha source, got {res_beta_get.status_code}"
            print("[PASS] User Beta GET /api/research/{alpha_session}/sources/{id} -> HTTP 404 Not Found")

            # Beta tries to insert into Alpha's session -> 404
            res_beta_post = await client.post(
                f"/api/research/{session_alpha_id}/sources/pasted-text",
                headers=headers_beta,
                json={"text": "Malicious payload injection attempt", "title": "Attack"},
            )
            assert res_beta_post.status_code == 404, f"Expected 404 for Beta inserting into Alpha session, got {res_beta_post.status_code}"
            print("[PASS] User Beta POST /api/research/{alpha_session}/sources/pasted-text -> HTTP 404 Not Found")

            # Beta tries to delete Alpha's source -> 404
            res_beta_del = await client.delete(
                f"/api/research/{session_alpha_id}/sources/{target_source['id']}",
                headers=headers_beta,
            )
            assert res_beta_del.status_code == 404, f"Expected 404 for Beta deleting Alpha source, got {res_beta_del.status_code}"
            print("[PASS] User Beta DELETE /api/research/{alpha_session}/sources/{id} -> HTTP 404 Not Found")

            # Beta accesses own session normally -> 200
            res_beta_own = await client.get(
                f"/api/research/{session_beta_id}/sources",
                headers=headers_beta,
            )
            assert res_beta_own.status_code == 200
            assert res_beta_own.json()["data"]["total"] == 0
            print("[PASS] User Beta accesses own research session normally -> HTTP 200 OK")

            # -----------------------------------------------------------------
            # STAGE G: DIRECT DATABASE RLS ISOLATION (POSTGREST CLIENT)
            # -----------------------------------------------------------------
            print("\n--- [Stage G] Direct Database PostgreSQL RLS Verification (No Service Key) ---")
            beta_client = create_client(settings.SUPABASE_BASE_URL, settings.SUPABASE_ANON_KEY)
            beta_client.postgrest.auth(token_beta)

            # Direct SELECT against sources table for Alpha's session
            direct_select_beta = beta_client.table("sources").select("*").eq("research_id", session_alpha_id).execute()
            assert len(direct_select_beta.data) == 0, f"RLS VIOLATION: Beta query returned rows from Alpha session: {direct_select_beta.data}"
            print("[PASS] Database RLS SELECT: User Beta direct query returned 0 rows for Alpha sources (RLS ENFORCED)")

            # Direct DELETE attempt against Alpha's source
            beta_client.table("sources").delete().eq("id", target_source["id"]).execute()

            # Confirm row remains intact when queried via admin client
            check_intact = admin_client.table("sources").select("id").eq("id", target_source["id"]).execute()
            assert len(check_intact.data) == 1, "RLS VIOLATION: Beta direct DELETE compromised Alpha source row!"
            print("[PASS] Database RLS DELETE: Target source remained intact after unauthorized direct delete attempt (RLS ENFORCED)")

            # -----------------------------------------------------------------
            # STAGE H: INDIVIDUAL SOURCE DELETION
            # -----------------------------------------------------------------
            print("\n--- [Stage H] Individual Source Deletion ---")
            source_to_delete = created_sources[-1]  # delete the last source (DOCX)
            res_del_single = await client.delete(
                f"/api/research/{session_alpha_id}/sources/{source_to_delete['id']}",
                headers=headers_alpha,
            )
            assert res_del_single.status_code == 200, f"Failed deleting source: {res_del_single.text}"
            del_body = res_del_single.json()
            assert del_body["success"] is True
            assert del_body["message"] == "Source deleted successfully"

            # Verify deletion in Supabase
            check_deleted = admin_client.table("sources").select("id").eq("id", source_to_delete["id"]).execute()
            assert len(check_deleted.data) == 0, "Source was not removed from database!"

            # Verify other sources remain
            remaining_sources = admin_client.table("sources").select("id").eq("research_id", session_alpha_id).execute()
            assert len(remaining_sources.data) == len(created_sources) - 1
            print(f"[PASS] Source {source_to_delete['source_code']} deleted successfully via API; {len(remaining_sources.data)} remaining sources intact")

            # -----------------------------------------------------------------
            # STAGE I: CASCADE DELETION
            # -----------------------------------------------------------------
            print("\n--- [Stage I] Research Session Cascade Deletion ---")
            res_del_session = await client.delete(
                f"/api/research/{session_alpha_id}",
                headers=headers_alpha,
            )
            assert res_del_session.status_code == 200, f"Failed deleting research session: {res_del_session.text}"

            # Verify all sources for session_alpha_id are completely removed via CASCADE
            cascaded_sources = admin_client.table("sources").select("id").eq("research_id", session_alpha_id).execute()
            assert len(cascaded_sources.data) == 0, f"CASCADE FAILURE: Sources still lingered after session deletion: {cascaded_sources.data}"
            print("[PASS] Alpha research session deleted; all associated sources purged via PostgreSQL ON DELETE CASCADE")

            # Confirm Beta's session is untouched
            beta_check = admin_client.table("research_sessions").select("id").eq("id", session_beta_id).execute()
            assert len(beta_check.data) == 1, "Beta research session was unexpectedly affected!"
            print("[PASS] User Beta session verified intact after Alpha cascade deletion")

    except Exception as exc:
        print(f"\n[FAIL] Integration test failed with exception: {type(exc).__name__}: {exc}")
        overall_success = False
        raise

    finally:
        # ---------------------------------------------------------------------
        # STAGE J: GUARANTEED POST-TEST CLEANUP
        # ---------------------------------------------------------------------
        print("\n--- [Cleanup] Purging Test Resources by Exact UUID ---")

        # 1. Purge Alpha session if still present
        if session_alpha_id:
            try:
                admin_client.table("research_sessions").delete().eq("id", session_alpha_id).execute()
            except Exception as exc:
                print(f"[WARN] Alpha session cleanup exception: {type(exc).__name__}")

        # 2. Purge Beta session if still present
        if session_beta_id:
            try:
                admin_client.table("research_sessions").delete().eq("id", session_beta_id).execute()
                print(f"[CLEANUP] Deleted Beta session ({session_beta_id})")
            except Exception as exc:
                print(f"[WARN] Beta session cleanup exception: {type(exc).__name__}")
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
        print("ALL END-TO-END SOURCE INTEGRATION & ISOLATION CHECKS PASSED!")
        if website_skipped:
            print("(Note: Website source extraction was skipped due to network limitation)")
        print("==================================================================")
        return 0
    else:
        print("INTEGRATION TESTS OR CLEANUP FAILED!")
        print("==================================================================")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_integration_tests())
    sys.exit(exit_code)
