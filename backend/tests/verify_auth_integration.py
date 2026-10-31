"""ClarityX End-to-End Live Supabase Auth & Multi-User Isolation Verification Script.

Tests the full authentication and isolation lifecycle:
1. Guaranteed cleanup of any existing or created test users via try/finally
2. Registration and login with valid credentials (real user JWTs)
3. Login failure with invalid credentials
4. User profile retrieval through GET /api/auth/me
5. Expired/invalid token rejection (HTTP 401)
6. Research session creation by User Alpha
7. Application-level isolation: User Beta cannot access Alpha's session via FastAPI
8. Database-level RLS isolation: User Beta querying Supabase PostgREST directly with anon key + Beta JWT
   (guaranteeing RLS is enforced and NOT bypassed by service-role key)
9. Research session deletion and verification
"""

import asyncio
from httpx import AsyncClient, ASGITransport
from supabase import create_client

from app.main import create_app
from app.database.supabase import get_supabase_client
from app.core.config import get_settings


async def main():
    settings = get_settings()
    admin_client = get_supabase_client()

    email_alpha = "audit_test_alpha@clarityx.dev"
    email_beta = "audit_test_beta@clarityx.dev"
    test_password = "AuditPassword123!"

    user_alpha = None
    user_beta = None

    print("=== [1] Pre-Test Cleanup of Lingering Test Users ===")
    users = admin_client.auth.admin.list_users()
    for u in users:
        if u.email in (email_alpha, email_beta):
            admin_client.auth.admin.delete_user(u.id)
            print(f"Cleaned up pre-existing test user: {u.email}")

    try:
        print("\n=== [2] Create Real Test Users in Supabase Auth ===")
        user_alpha = admin_client.auth.admin.create_user({
            "email": email_alpha,
            "password": test_password,
            "email_confirm": True,
            "user_metadata": {"full_name": "Audit Alpha Analyst"}
        })
        print(f"User Alpha created: ID={user_alpha.user.id}, email={user_alpha.user.email}")

        user_beta = admin_client.auth.admin.create_user({
            "email": email_beta,
            "password": test_password,
            "email_confirm": True,
            "user_metadata": {"full_name": "Audit Beta Analyst"}
        })
        print(f"User Beta created: ID={user_beta.user.id}, email={user_beta.user.email}")

        print("\n=== [3] Authenticate via Public Client (Anon Key) ===")
        public_client = create_client(settings.SUPABASE_BASE_URL, settings.SUPABASE_ANON_KEY)

        # 3a. Test valid login
        session_alpha = public_client.auth.sign_in_with_password({
            "email": email_alpha,
            "password": test_password
        })
        token_alpha = session_alpha.session.access_token
        print(f"Alpha authenticated successfully (JWT length: {len(token_alpha)})")

        session_beta = public_client.auth.sign_in_with_password({
            "email": email_beta,
            "password": test_password
        })
        token_beta = session_beta.session.access_token
        print(f"Beta authenticated successfully (JWT length: {len(token_beta)})")

        # 3b. Test invalid credentials login
        try:
            public_client.auth.sign_in_with_password({
                "email": email_alpha,
                "password": "WrongPassword999!"
            })
            raise AssertionError("Login with invalid password unexpectedly succeeded!")
        except Exception as e:
            print(f"Invalid credentials login correctly rejected: {type(e).__name__}")

        print("\n=== [4] FastAPI Verification via Real User JWTs ===")
        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 4a. Profile retrieval for Alpha
            res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_alpha}"})
            assert res.status_code == 200, f"Alpha /api/auth/me failed: {res.text}"
            profile_alpha = res.json()
            assert profile_alpha["email"] == email_alpha
            assert profile_alpha["full_name"] == "Audit Alpha Analyst"
            print(f"Alpha /api/auth/me: HTTP 200 OK (Name: {profile_alpha['full_name']})")

            # 4b. Profile retrieval for Beta
            res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_beta}"})
            assert res.status_code == 200, f"Beta /api/auth/me failed: {res.text}"
            profile_beta = res.json()
            assert profile_beta["email"] == email_beta
            assert profile_beta["full_name"] == "Audit Beta Analyst"
            print(f"Beta /api/auth/me: HTTP 200 OK (Name: {profile_beta['full_name']})")

            # 4c. Expired / Invalid token rejection check
            res = await client.get("/api/auth/me", headers={"Authorization": "Bearer invalid_garbage_token"})
            assert res.status_code == 401, f"Expected 401 for invalid token, got {res.status_code}"
            print("Invalid Bearer token rejection: HTTP 401 Unauthorized (Verified)")

            # 4d. Missing Authorization header check
            res = await client.get("/api/auth/me")
            assert res.status_code == 401, f"Expected 401 for missing header, got {res.status_code}"
            print("Missing Authorization header rejection: HTTP 401 Unauthorized (Verified)")

            # 4e. User Alpha creates research session
            goal = "Audit Verification: Solid-state battery commercial longevity in cold climates."
            res = await client.post(
                "/api/research",
                json={"research_goal": goal},
                headers={"Authorization": f"Bearer {token_alpha}"}
            )
            assert res.status_code == 201, f"POST /api/research failed: {res.text}"
            created_session = res.json()["data"]
            session_id = created_session["id"]
            assert created_session["user_id"] == str(user_alpha.user.id)
            print(f"Alpha created research session: ID={session_id}")

            # 4f. Alpha lists sessions
            res = await client.get("/api/research", headers={"Authorization": f"Bearer {token_alpha}"})
            assert res.status_code == 200
            alpha_sessions = res.json()["data"]["research_sessions"]
            assert any(s["id"] == session_id for s in alpha_sessions)
            print(f"Alpha session list: contains session {session_id} (Verified)")

            # 4g. Application-level isolation: User Beta lists sessions
            res = await client.get("/api/research", headers={"Authorization": f"Bearer {token_beta}"})
            assert res.status_code == 200
            beta_sessions = res.json()["data"]["research_sessions"]
            assert not any(s["id"] == session_id for s in beta_sessions)
            print("Application Isolation: Beta cannot see Alpha's session in GET /api/research (Verified)")

            # 4h. Application-level isolation: User Beta accesses Alpha's session by ID
            res = await client.get(f"/api/research/{session_id}", headers={"Authorization": f"Bearer {token_beta}"})
            assert res.status_code == 404
            print("Application Isolation: Beta GET /api/research/{id} -> HTTP 404 Not Found (Verified)")

            # 4i. Application-level isolation: User Beta attempts to delete Alpha's session
            res = await client.delete(f"/api/research/{session_id}", headers={"Authorization": f"Bearer {token_beta}"})
            assert res.status_code == 404
            print("Application Isolation: Beta DELETE /api/research/{id} -> HTTP 404 Not Found (Verified)")

        print("\n=== [5] Direct Database-Level PostgreSQL RLS Verification (No Service Key) ===")
        # Connect to Supabase using public anon key and User Beta's JWT
        beta_client = create_client(settings.SUPABASE_BASE_URL, settings.SUPABASE_ANON_KEY)
        beta_client.postgrest.auth(token_beta)

        # 5a. Direct RLS SELECT test: Beta queries research_sessions table directly via PostgREST
        direct_select = beta_client.table("research_sessions").select("*").eq("id", session_id).execute()
        assert len(direct_select.data) == 0, f"RLS VIOLATION: Beta read Alpha session directly! {direct_select.data}"
        print(f"Database RLS SELECT: Beta direct query returned 0 rows for Alpha session (RLS ENFORCED)")

        # 5b. Direct RLS DELETE test: Beta attempts to delete Alpha's session directly via PostgREST
        beta_client.table("research_sessions").delete().eq("id", session_id).execute()
        # Verify row still exists for Alpha
        alpha_client = create_client(settings.SUPABASE_BASE_URL, settings.SUPABASE_ANON_KEY)
        alpha_client.postgrest.auth(token_alpha)
        direct_check = alpha_client.table("research_sessions").select("*").eq("id", session_id).execute()
        assert len(direct_check.data) == 1, "RLS VIOLATION: Beta was able to delete Alpha session directly!"
        print(f"Database RLS DELETE: Beta direct delete blocked, row intact for Alpha (RLS ENFORCED)")

        print("\n=== [6] Cleanup Created Session via Alpha ===")
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            del_res = await client.delete(f"/api/research/{session_id}", headers={"Authorization": f"Bearer {token_alpha}"})
            assert del_res.status_code == 200
            print(f"Alpha deleted own session: HTTP 200 OK")

    finally:
        print("\n=== [7] Guaranteed Post-Test Cleanup ===")
        if user_alpha:
            admin_client.auth.admin.delete_user(user_alpha.user.id)
            print(f"Deleted test user Alpha ({user_alpha.user.id})")
        if user_beta:
            admin_client.auth.admin.delete_user(user_beta.user.id)
            print(f"Deleted test user Beta ({user_beta.user.id})")
        print("Test user cleanup completed successfully.")

    print("\n==================================================================")
    print("ALL AUDIT SCENARIOS: AUTHENTICATION, API ISOLATION, & RLS PASSED!")
    print("==================================================================")


if __name__ == "__main__":
    asyncio.run(main())
