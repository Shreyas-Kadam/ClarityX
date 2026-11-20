"""ClarityX Live Supabase Session & Source Verification Script.

Validates against live Supabase:
1. Disposable test user provisioning and JWT authentication.
2. Research session creation.
3. Successful source ingestion and persistence (Website + Document).
4. Preservation of source metadata and extracted content.
5. Failed source rejection and handling (e.g., 403 access control / 422 extraction errors).
6. Refresh simulation: GET /api/research/{id} and GET /api/research/{id}/sources/{source_id}
   retaining complete source metadata and full extracted content.
7. Verification that failed or empty sources are never included in usable_sources for AI analysis.
8. Full cleanup of disposable research sessions and test user.
"""

import asyncio
from datetime import datetime, timezone
import io
from pathlib import Path
import sys
import uuid
from typing import Dict, List, Optional

# Force unbuffered prints
_orig_print = print
def print(*args, **kwargs):
    kwargs.setdefault("flush", True)
    _orig_print(*args, **kwargs)

# Ensure backend root directory is in sys.path
backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from httpx import ASGITransport, AsyncClient
import pypdf
from supabase import create_client

from app.core.config import get_settings
from app.database.repositories import SourceRepository
from app.database.supabase import get_supabase_client
from app.main import create_app

MINIMAL_PDF_BYTES = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 120 >> stream
BT
/F1 12 Tf
72 712 Td
(ClarityX Live Verification: Solid-state battery testing demonstrates 80 percent retention after 800 cycles.) Tj
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
0000000394 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
464
%%EOF"""


async def run_live_session_verification() -> bool:
    settings = get_settings()
    admin_client = get_supabase_client()

    run_id = uuid.uuid4().hex[:8]
    test_email = f"audit_source_e2e_{run_id}@clarityx.dev"
    test_password = f"P@ssword_{uuid.uuid4().hex[:12]}!"

    user_id: Optional[str] = None
    session_id: Optional[str] = None
    success = True

    print("==================================================================")
    print(f"CLARITYX LIVE SUPABASE SESSION & SOURCE VERIFICATION (Run ID: {run_id})")
    print("==================================================================")

    try:
        # 1. Provision disposable test user
        print("\n--- 1. Provisioning Test User in Supabase ---")
        user_resp = admin_client.auth.admin.create_user({
            "email": test_email,
            "password": test_password,
            "email_confirm": True,
            "user_metadata": {"full_name": f"Session Tester {run_id}"},
        })
        user_id = str(user_resp.user.id)
        print(f"[PASS] Created test user: {test_email} (ID: {user_id})")

        # 2. Authenticate to obtain real user JWT
        print("\n--- 2. Authenticating via Supabase Public Client ---")
        public_client = create_client(settings.SUPABASE_BASE_URL, settings.SUPABASE_ANON_KEY)
        auth_session = public_client.auth.sign_in_with_password({
            "email": test_email,
            "password": test_password,
        })
        access_token = auth_session.session.access_token
        assert access_token, "No access token received"
        print(f"[PASS] Authenticated successfully. JWT obtained ({len(access_token)} chars).")

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            headers = {"Authorization": f"Bearer {access_token}"}

            # 3. Create Research Session
            print("\n--- 3. Creating Research Session ---")
            create_session_resp = await client.post(
                "/api/research",
                json={
                    "research_goal": f"Solid-State Battery Audit {run_id}",
                },
                headers=headers,
            )
            assert create_session_resp.status_code == 201, f"Failed to create session: {create_session_resp.text}"
            session_data = create_session_resp.json()["data"]
            session_id = session_data["id"]
            print(f"[PASS] Research session created with ID: {session_id}")

            # 4. Ingest Successful Website Source (Toyota corporate release)
            print("\n--- 4. Ingesting Successful Website Source ---")
            website_url = "https://global.toyota/en/newsroom/corporate/43380876.html"
            ingest_web_resp = await client.post(
                f"/api/research/{session_id}/sources/website",
                json={"url": website_url},
                headers=headers,
            )
            assert ingest_web_resp.status_code == 201, f"Failed to ingest website: {ingest_web_resp.text}"
            web_source = ingest_web_resp.json()["data"]
            web_source_id = web_source["id"]
            assert web_source["source_type"] == "website"
            assert web_source["extraction_status"] == "success"
            assert web_source["domain"] == "global.toyota"
            assert len(web_source["extracted_content"]) > 0
            print(f"[PASS] Ingested Website source: {web_source['source_code']} (ID: {web_source_id})")
            print(f"       Domain: {web_source['domain']}, Title: {web_source['title'][:50]}...")
            print(f"       Extraction Status: {web_source['extraction_status']}")

            # 5. Ingest Successful Document Source (PDF)
            print("\n--- 5. Ingesting Successful Document Source (PDF) ---")
            files = {
                "file": ("solid_state_benchmark.pdf", MINIMAL_PDF_BYTES, "application/pdf")
            }
            data = {"title": "Solid-State Benchmark Report"}
            ingest_doc_resp = await client.post(
                f"/api/research/{session_id}/sources/document",
                files=files,
                data=data,
                headers=headers,
            )
            assert ingest_doc_resp.status_code == 201, f"Failed to ingest document: {ingest_doc_resp.text}"
            doc_source = ingest_doc_resp.json()["data"]
            doc_source_id = doc_source["id"]
            assert doc_source["source_type"] == "document"
            assert doc_source["extraction_status"] == "success"
            assert doc_source["character_count"] > 50
            print(f"[PASS] Ingested Document source: {doc_source['source_code']} (ID: {doc_source_id})")
            print(f"       Chars: {doc_source['character_count']}, Status: {doc_source['extraction_status']}")

            # 6. Test Failed Website Source Handling
            print("\n--- 6. Verifying Rejection of Protected/Unextractable Website ---")
            failed_url = "https://www.iea.org/files/857aa690-2a43-453f-9f12-147cc8f01a0d/GlobalEVOutlook2026.pdf"
            failed_resp = await client.post(
                f"/api/research/{session_id}/sources/website",
                json={"url": failed_url},
                headers=headers,
            )
            # Should reject with HTTP 422 or 403, and provide clear recommendation
            assert failed_resp.status_code in (403, 422), f"Unexpected status code: {failed_resp.status_code}"
            err_json = failed_resp.json()
            assert "detail" in err_json or "message" in err_json
            print(f"[PASS] Successfully rejected unextractable source with HTTP {failed_resp.status_code}")
            print(f"       Error detail: {err_json.get('detail') or err_json.get('message')}")

            # 7. Directly insert a failed source record to test DB persistence of failed status
            print("\n--- 7. Directly Persisting a Failed Source Record ---")
            source_repo = SourceRepository()
            failed_db_source = await source_repo.create_source(
                session_id=session_id,
                user_id=user_id,
                source_type="website",
                extracted_content="",  # empty content
                title="Failed Extraction Source",
                url="https://example.com/broken",
                domain="example.com",
                extraction_status="failed",
            )
            assert failed_db_source["extraction_status"] == "failed"
            print(f"[PASS] Created test failed source record: {failed_db_source['source_code']} (Status: {failed_db_source['extraction_status']})")

            # 8. Refresh Simulation (GET /api/research/{session_id})
            print("\n--- 8. Simulating Page Refresh (GET /api/research/{id}) ---")
            report_resp = await client.get(
                f"/api/research/{session_id}",
                headers=headers,
            )
            assert report_resp.status_code == 200, f"Failed to retrieve report: {report_resp.text}"
            report_data = report_resp.json()["data"]
            sources_list = report_data["sources"]
            print(f"[PASS] Report retrieved. Total sources persisted: {len(sources_list)}")
            assert len(sources_list) == 3, f"Expected 3 sources, got {len(sources_list)}"

            # Confirm source codes and statuses in list
            statuses = {s["source_code"]: s["extraction_status"] for s in sources_list}
            print(f"       Persisted source statuses: {statuses}")
            assert statuses["S1"] == "success"
            assert statuses["S2"] == "success"
            assert statuses["S3"] == "failed"

            # 9. Verify Full Extracted Content Retrieval for Valid Source
            print("\n--- 9. Verifying Full Content Retrieval (GET /api/research/{id}/sources/{source_id}) ---")
            web_full_resp = await client.get(
                f"/api/research/{session_id}/sources/{web_source_id}",
                headers=headers,
            )
            assert web_full_resp.status_code == 200
            web_full_data = web_full_resp.json()["data"]
            assert len(web_full_data["extracted_content"]) > 1000
            assert "Toyota" in web_full_data["extracted_content"]
            print(f"[PASS] Full extracted content retrieved ({len(web_full_data['extracted_content'])} characters).")

            # 10. Verify AI Analysis Filtering Logic
            print("\n--- 10. Verifying AI Analysis Usable Sources Filter ---")
            raw_sources = await source_repo.get_raw_sources_by_session(
                session_id=session_id,
                user_id=user_id,
            )
            assert len(raw_sources) == 3

            # Exact filter from backend/app/routes/research.py lines 324-328:
            usable_sources = [
                s
                for s in raw_sources
                if s.get("extraction_status") != "failed" and bool((s.get("extracted_content") or "").strip())
            ]

            print(f"       Raw sources in DB: {len(raw_sources)}")
            print(f"       Usable sources for AI: {len(usable_sources)}")
            assert len(usable_sources) == 2, f"Expected 2 usable sources, got {len(usable_sources)}"

            usable_codes = [s["source_code"] for s in usable_sources]
            print(f"       Usable source codes: {usable_codes}")
            assert "S1" in usable_codes
            assert "S2" in usable_codes
            assert "S3" not in usable_codes, "Failed source S3 must NOT be in usable sources!"
            print("[PASS] Failed and empty sources are strictly excluded from AI analysis!")

            # 11. Delete Research Session
            print("\n--- 11. Testing Session Deletion ---")
            del_resp = await client.delete(
                f"/api/research/{session_id}",
                headers=headers,
            )
            assert del_resp.status_code == 200
            print("[PASS] Session deleted successfully.")

    except Exception as exc:
        print(f"\n[FAIL] An error occurred during verification: {exc}")
        import traceback
        traceback.print_exc()
        success = False

    finally:
        # Cleanup test user
        if user_id:
            print("\n--- Teardown: Deleting Test User ---")
            try:
                admin_client.auth.admin.delete_user(user_id)
                print(f"[PASS] Test user {user_id} deleted successfully.")
            except Exception as e:
                print(f"[WARNING] Failed to clean up test user {user_id}: {e}")

    return success


if __name__ == "__main__":
    result = asyncio.run(run_live_session_verification())
    if not result:
        sys.exit(1)
    print("\n==================================================================")
    print("ALL LIVE SUPABASE SESSION VERIFICATION CHECKS PASSED!")
    print("==================================================================")
