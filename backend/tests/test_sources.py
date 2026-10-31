"""Unit & Integration Tests for ClarityX Source API Routes (Checkpoint 4.4.2).

Tests:
1. Authentication & Authorization enforcement across all endpoints.
2. Cross-user isolation and missing session 404 handling.
3. Website source extraction, partial persistence, failure rejection, and SSRF handling.
4. Pasted-text source extraction, sanitization, validation, and persistence.
5. Document upload, extension filtering, 10MB streaming size enforcement, and encrypted/empty file rejection.
6. Content preview-only listing (extracted_content stripped) and pagination.
7. Single-source retrieval with full extracted_content.
8. Source deletion with proper 200 response envelope and 404 on missing records.
9. Database insertion prevention on extraction failures.
10. Input validation (UUIDs and forbidden fields).
"""

from datetime import datetime, timezone
import io
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import (
    ClarityXException,
    ContentSizeExceededError,
    EncryptedDocumentError,
    ExtractionError,
    SSRFSecurityError,
    UnsupportedContentTypeError,
)
from app.database.repositories import SourceRepository
from app.main import app
from app.routes.sources import get_source_repository
from app.schemas.source import (
    DocumentExtractionResult,
    PastedTextExtractionResult,
    WebsiteExtractionResult,
)


@pytest.fixture(autouse=True)
def reset_overrides():
    """Ensures dependency overrides are cleared after each test."""
    yield
    app.dependency_overrides.clear()


def create_mock_auth_user(
    user_id: str = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80",
    email: str = "alice@clarityx.dev",
    full_name: str = "Alice Researcher",
):
    """Helper creating a mocked Supabase Auth user response."""
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.email = email
    mock_user.user_metadata = {"full_name": full_name}

    mock_resp = MagicMock()
    mock_resp.user = mock_user
    return mock_resp


ALICE_ID = "e87b7ef5-1d4a-4632-9cb7-7f9cb894bb80"
BOB_ID = "99999999-9999-9999-9999-999999999999"
SESSION_ID = "11111111-2222-3333-4444-555555555555"
SOURCE_ID = "423e4567-e89b-12d3-a456-426614174003"


# =============================================================================
# 1. AUTHENTICATION & ACCESS CONTROL TESTS
# =============================================================================


@pytest.mark.anyio
@pytest.mark.parametrize(
    "method,endpoint,kwargs",
    [
        ("POST", f"/api/research/{SESSION_ID}/sources/website", {"json": {"url": "https://example.com"}}),
        ("POST", f"/api/research/{SESSION_ID}/sources/pasted-text", {"json": {"text": "Hello world"}}),
        ("POST", f"/api/research/{SESSION_ID}/sources/document", {"files": {"file": ("test.pdf", b"%PDF-1.4", "application/pdf")}}),
        ("GET", f"/api/research/{SESSION_ID}/sources", {}),
        ("GET", f"/api/research/{SESSION_ID}/sources/{SOURCE_ID}", {}),
        ("DELETE", f"/api/research/{SESSION_ID}/sources/{SOURCE_ID}", {}),
    ],
)
async def test_routes_require_authentication(method: str, endpoint: str, kwargs: dict):
    """All six source endpoints return 401 when the Authorization header is missing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req = getattr(client, method.lower())
        response = await req(endpoint, **kwargs)
        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert "Authorization header" in data["message"] or "Authentication required" in data["message"]


@pytest.mark.anyio
async def test_routes_reject_invalid_token():
    """Invalid or expired Bearer token returns HTTP 401."""
    mock_client = MagicMock()
    mock_client.auth.get_user.side_effect = Exception("Token expired")

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/research/{SESSION_ID}/sources",
                headers={"Authorization": "Bearer expired-token"},
            )
            assert response.status_code == 401
            assert response.json()["success"] is False


@pytest.mark.anyio
async def test_cross_user_access_blocked():
    """User B cannot create, list, retrieve, or delete sources belonging to User A's session."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=BOB_ID)

    mock_repo = MagicMock(spec=SourceRepository)
    unauthorized_exc = ClarityXException(
        message="Research session not found or unauthorized",
        status_code=404,
        detail="The specified research session does not exist or does not belong to the authenticated user.",
    )
    mock_repo.create_source = AsyncMock(side_effect=unauthorized_exc)
    mock_repo.list_sources = AsyncMock(side_effect=unauthorized_exc)
    mock_repo.get_source_by_id = AsyncMock(return_value=None)
    mock_repo.delete_source = AsyncMock(return_value=False)

    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth),
        patch(
            "app.routes.sources.extract_website_content",
            new_callable=AsyncMock,
            return_value=WebsiteExtractionResult(
                url="https://example.com",
                title="Example",
                extracted_content="Sample extracted text content",
                extraction_status="success",
            ),
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": "Bearer bobs-token"}

            # 1. Create website source blocked
            res_post = await client.post(
                f"/api/research/{SESSION_ID}/sources/website",
                headers=headers,
                json={"url": "https://example.com"},
            )
            assert res_post.status_code == 404

            # 2. List sources blocked
            res_list = await client.get(f"/api/research/{SESSION_ID}/sources", headers=headers)
            assert res_list.status_code == 404

            # 3. Get single source blocked
            res_get = await client.get(f"/api/research/{SESSION_ID}/sources/{SOURCE_ID}", headers=headers)
            assert res_get.status_code == 404

            # 4. Delete source blocked
            res_del = await client.delete(f"/api/research/{SESSION_ID}/sources/{SOURCE_ID}", headers=headers)
            assert res_del.status_code == 404


@pytest.mark.anyio
async def test_missing_research_session_returns_404():
    """Non-existent research session returns 404 on all endpoints."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.list_sources = AsyncMock(
        side_effect=ClarityXException(
            message="Research session not found or unauthorized",
            status_code=404,
        )
    )
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                f"/api/research/{SESSION_ID}/sources",
                headers={"Authorization": "Bearer alices-token"},
            )
            assert res.status_code == 404
            assert "not found" in res.json()["message"].lower()


@pytest.mark.anyio
async def test_client_cannot_spoof_user_id():
    """Injecting user_id in payloads is rejected by Pydantic extra='forbid' validation with 422."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": "Bearer alices-token"}

            # Website request with user_id
            res_web = await client.post(
                f"/api/research/{SESSION_ID}/sources/website",
                headers=headers,
                json={"url": "https://example.com", "user_id": BOB_ID},
            )
            assert res_web.status_code == 422

            # Pasted text request with user_id
            res_txt = await client.post(
                f"/api/research/{SESSION_ID}/sources/pasted-text",
                headers=headers,
                json={"text": "Hello world", "user_id": BOB_ID},
            )
            assert res_txt.status_code == 422


# =============================================================================
# 2. WEBSITE EXTRACTION & PERSISTENCE TESTS
# =============================================================================


@pytest.mark.anyio
async def test_add_website_source_success():
    """Successfully extracts website and persists record with allocated source code S1."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    now_iso = datetime.now(timezone.utc).isoformat()
    persisted_record = {
        "id": SOURCE_ID,
        "research_id": SESSION_ID,
        "source_code": "S1",
        "title": "Quantum Computing Advances",
        "url": "https://example.com/quantum",
        "source_type": "website",
        "extracted_content": "Extracted article text about quantum computing.",
        "published_at": "2026-10-15T00:00:00Z",
        "accessed_at": now_iso,
        "extraction_status": "success",
        "created_at": now_iso,
    }

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.create_source = AsyncMock(return_value=persisted_record)
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    mock_extract = AsyncMock(
        return_value=WebsiteExtractionResult(
            url="https://example.com/quantum",
            title="Quantum Computing Advances",
            extracted_content="Extracted article text about quantum computing.",
            published_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
            extraction_method="trafilatura",
            extraction_status="success",
        )
    )

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth),
        patch("app.routes.sources.extract_website_content", mock_extract),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{SESSION_ID}/sources/website",
                headers={"Authorization": "Bearer alices-token"},
                json={"url": "https://example.com/quantum"},
            )

            assert response.status_code == 201
            body = response.json()
            assert body["success"] is True
            assert body["message"] == "Website source extracted and persisted successfully"
            assert body["data"]["source_code"] == "S1"
            assert body["data"]["title"] == "Quantum Computing Advances"
            assert body["data"]["source_type"] == "website"
            assert body["data"]["extracted_content"] == "Extracted article text about quantum computing."

            mock_extract.assert_awaited_once_with("https://example.com/quantum")
            mock_repo.create_source.assert_awaited_once()


@pytest.mark.anyio
async def test_add_website_source_partial_success():
    """Partial extraction is persisted with extraction_status='partial'."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    now_iso = datetime.now(timezone.utc).isoformat()
    persisted_record = {
        "id": SOURCE_ID,
        "research_id": SESSION_ID,
        "source_code": "S2",
        "title": "Partial Article",
        "url": "https://example.com/partial",
        "source_type": "website",
        "extracted_content": "Partial snippet extracted before truncation",
        "published_at": None,
        "accessed_at": now_iso,
        "extraction_status": "partial",
        "created_at": now_iso,
    }

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.create_source = AsyncMock(return_value=persisted_record)
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    mock_extract = AsyncMock(
        return_value=WebsiteExtractionResult(
            url="https://example.com/partial",
            title="Partial Article",
            extracted_content="Partial snippet extracted before truncation",
            published_at=None,
            extraction_method="trafilatura",
            extraction_status="partial",
        )
    )

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth),
        patch("app.routes.sources.extract_website_content", mock_extract),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{SESSION_ID}/sources/website",
                headers={"Authorization": "Bearer alices-token"},
                json={"url": "https://example.com/partial"},
            )

            assert response.status_code == 201
            body = response.json()
            assert body["data"]["extraction_status"] == "partial"
            assert mock_repo.create_source.call_args.kwargs["extraction_status"] == "partial"


@pytest.mark.anyio
async def test_add_website_source_failure_does_not_create_source():
    """Extraction failure returns 422 and does NOT call repository create_source."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.create_source = AsyncMock()
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    mock_extract = AsyncMock(
        side_effect=ExtractionError(
            message="Unable to extract meaningful readable content from the requested website.",
            status_code=422,
        )
    )

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth),
        patch("app.routes.sources.extract_website_content", mock_extract),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{SESSION_ID}/sources/website",
                headers={"Authorization": "Bearer alices-token"},
                json={"url": "https://example.com/empty"},
            )

            assert response.status_code == 422
            data = response.json()
            assert data["success"] is False
            assert "Unable to extract" in data["message"]
            mock_repo.create_source.assert_not_called()


@pytest.mark.anyio
async def test_add_website_source_ssrf_error():
    """SSRF violation returns 400 with generic safe message, not internal IPs."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    mock_repo = MagicMock(spec=SourceRepository)
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    mock_extract = AsyncMock(
        side_effect=SSRFSecurityError(
            message="Security validation failed: Prohibited destination address."
        )
    )

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth),
        patch("app.routes.sources.extract_website_content", mock_extract),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{SESSION_ID}/sources/website",
                headers={"Authorization": "Bearer alices-token"},
                json={"url": "http://169.254.169.254/latest/meta-data"},
            )

            assert response.status_code == 400
            data = response.json()
            assert data["success"] is False
            assert "The requested URL cannot be accessed for security reasons." in data["message"]


# =============================================================================
# 3. PASTED TEXT EXTRACTION & PERSISTENCE TESTS
# =============================================================================


@pytest.mark.anyio
async def test_add_pasted_text_source_success():
    """Successfully sanitizes, normalizes, and persists user-submitted pasted text."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    now_iso = datetime.now(timezone.utc).isoformat()
    persisted_record = {
        "id": SOURCE_ID,
        "research_id": SESSION_ID,
        "source_code": "S2",
        "title": "My Research Notes",
        "url": None,
        "source_type": "pasted_text",
        "extracted_content": "Line 1\nLine 2\nMeaningful research notes.",
        "published_at": None,
        "accessed_at": now_iso,
        "extraction_status": "success",
        "created_at": now_iso,
    }

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.create_source = AsyncMock(return_value=persisted_record)
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{SESSION_ID}/sources/pasted-text",
                headers={"Authorization": "Bearer alices-token"},
                json={
                    "text": "# My Research Notes\nLine 1\r\nLine 2\nMeaningful research notes.",
                },
            )

            assert response.status_code == 201
            body = response.json()
            assert body["success"] is True
            assert body["data"]["source_type"] == "pasted_text"
            assert body["data"]["title"] == "My Research Notes"
            mock_repo.create_source.assert_awaited_once()


@pytest.mark.anyio
async def test_add_pasted_text_source_with_title_override():
    """User-supplied title override is prioritized in pasted text source."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.create_source = AsyncMock(
        return_value={
            "id": SOURCE_ID,
            "research_id": SESSION_ID,
            "source_code": "S1",
            "title": "Custom Title Override",
            "url": None,
            "source_type": "pasted_text",
            "extracted_content": "Raw notes here.",
            "published_at": None,
            "accessed_at": datetime.now(timezone.utc).isoformat(),
            "extraction_status": "success",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{SESSION_ID}/sources/pasted-text",
                headers={"Authorization": "Bearer alices-token"},
                json={
                    "text": "Raw notes here.",
                    "title": "Custom Title Override",
                },
            )

            assert response.status_code == 201
            assert mock_repo.create_source.call_args.kwargs["title"] == "Custom Title Override"


@pytest.mark.anyio
async def test_add_pasted_text_empty_input_rejected():
    """Empty or whitespace-only pasted text is rejected with 422 before database insertion."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.create_source = AsyncMock()
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/research/{SESSION_ID}/sources/pasted-text",
                headers={"Authorization": "Bearer alices-token"},
                json={"text": "    \n   \t  "},
            )

            assert response.status_code == 422
            mock_repo.create_source.assert_not_called()


# =============================================================================
# 4. DOCUMENT EXTRACTION & UPLOAD TESTS
# =============================================================================


@pytest.mark.anyio
async def test_add_pdf_document_source_success():
    """Uploading a valid PDF extracts content, closes file, and persists source record."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    now_iso = datetime.now(timezone.utc).isoformat()
    persisted_record = {
        "id": SOURCE_ID,
        "research_id": SESSION_ID,
        "source_code": "S3",
        "title": "Annual Report",
        "url": None,
        "source_type": "document",
        "extracted_content": "Extracted text from PDF document.",
        "published_at": None,
        "accessed_at": now_iso,
        "extraction_status": "success",
        "created_at": now_iso,
    }

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.create_source = AsyncMock(return_value=persisted_record)
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    mock_doc_result = DocumentExtractionResult(
        file_name="report.pdf",
        file_type="pdf",
        file_size_bytes=1024,
        title="Annual Report",
        source_type="document",
        extracted_content="Extracted text from PDF document.",
        character_count=32,
        word_count=5,
        page_count=1,
        extraction_method="pypdf",
        extraction_status="success",
    )

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth),
        patch("app.routes.sources.extract_document", return_value=mock_doc_result) as mock_extract,
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            pdf_bytes = b"%PDF-1.4\nfake pdf content"
            files = {"file": ("report.pdf", pdf_bytes, "application/pdf")}
            data = {"title": "Annual Report"}

            response = await client.post(
                f"/api/research/{SESSION_ID}/sources/document",
                headers={"Authorization": "Bearer alices-token"},
                files=files,
                data=data,
            )

            assert response.status_code == 201
            body = response.json()
            assert body["success"] is True
            assert body["data"]["source_type"] == "document"
            assert body["data"]["source_code"] == "S3"
            assert body["data"]["extracted_content"] == "Extracted text from PDF document."

            mock_extract.assert_called_once()
            assert mock_extract.call_args.kwargs["filename"] == "report.pdf"
            assert mock_extract.call_args.kwargs["title"] == "Annual Report"


@pytest.mark.anyio
async def test_add_docx_document_source_success():
    """Uploading a valid DOCX extracts content and persists source record."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    persisted_record = {
        "id": SOURCE_ID,
        "research_id": SESSION_ID,
        "source_code": "S4",
        "title": "Word Document",
        "url": None,
        "source_type": "document",
        "extracted_content": "Extracted paragraph and table content from Word.",
        "published_at": None,
        "accessed_at": datetime.now(timezone.utc).isoformat(),
        "extraction_status": "success",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.create_source = AsyncMock(return_value=persisted_record)
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    mock_doc_result = DocumentExtractionResult(
        file_name="draft.docx",
        file_type="docx",
        file_size_bytes=2048,
        title="Word Document",
        source_type="document",
        extracted_content="Extracted paragraph and table content from Word.",
        character_count=48,
        word_count=7,
        extraction_method="python-docx",
        extraction_status="success",
    )

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth),
        patch("app.routes.sources.extract_document", return_value=mock_doc_result),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            docx_bytes = b"PK\x03\x04fake docx"
            files = {"file": ("draft.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}

            response = await client.post(
                f"/api/research/{SESSION_ID}/sources/document",
                headers={"Authorization": "Bearer alices-token"},
                files=files,
            )

            assert response.status_code == 201
            body = response.json()
            assert body["data"]["source_code"] == "S4"
            assert body["data"]["source_type"] == "document"


@pytest.mark.anyio
async def test_add_document_partial_extraction_persisted():
    """Document extraction that exceeds character/byte limit is persisted with status 'partial'."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.create_source = AsyncMock(
        return_value={
            "id": SOURCE_ID,
            "research_id": SESSION_ID,
            "source_code": "S5",
            "title": "Long Document",
            "url": None,
            "source_type": "document",
            "extracted_content": "Extracted text up to 1MB limit...",
            "published_at": None,
            "accessed_at": datetime.now(timezone.utc).isoformat(),
            "extraction_status": "partial",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    mock_doc_result = DocumentExtractionResult(
        file_name="huge.pdf",
        file_type="pdf",
        file_size_bytes=5000000,
        title="Long Document",
        source_type="document",
        extracted_content="Extracted text up to 1MB limit...",
        character_count=1048576,
        word_count=150000,
        page_count=150,
        extraction_method="pypdf",
        extraction_status="partial",
    )

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth),
        patch("app.routes.sources.extract_document", return_value=mock_doc_result),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"file": ("huge.pdf", b"%PDF-1.4\ncontent", "application/pdf")}
            response = await client.post(
                f"/api/research/{SESSION_ID}/sources/document",
                headers={"Authorization": "Bearer alices-token"},
                files=files,
            )

            assert response.status_code == 201
            assert response.json()["data"]["extraction_status"] == "partial"
            assert mock_repo.create_source.call_args.kwargs["extraction_status"] == "partial"


@pytest.mark.anyio
async def test_add_document_unsupported_extension_rejected():
    """Unsupported document extensions (.txt, .exe, .png) are rejected with HTTP 415."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"file": ("malicious.exe", b"MZ\x90\x00executable", "application/octet-stream")}
            response = await client.post(
                f"/api/research/{SESSION_ID}/sources/document",
                headers={"Authorization": "Bearer alices-token"},
                files=files,
            )

            assert response.status_code == 415
            data = response.json()
            assert data["success"] is False
            assert "Unsupported file type" in data["message"]


@pytest.mark.anyio
async def test_add_document_oversized_stream_rejected_413():
    """Actual upload byte limit (>10 MB) is enforced during streaming and rejected with HTTP 413."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.create_source = AsyncMock()
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    # Create dummy payload larger than 10 MB (10,485,760 bytes)
    oversized_size = 10 * 1024 * 1024 + 1024  # 10 MB + 1 KB
    oversized_bytes = b"0" * oversized_size

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"file": ("toolarge.pdf", oversized_bytes, "application/pdf")}
            response = await client.post(
                f"/api/research/{SESSION_ID}/sources/document",
                headers={"Authorization": "Bearer alices-token"},
                files=files,
            )

            assert response.status_code == 413
            data = response.json()
            assert data["success"] is False
            assert "exceeds maximum allowable limit" in data["message"]
            mock_repo.create_source.assert_not_called()


@pytest.mark.anyio
async def test_add_document_encrypted_pdf_rejected_422():
    """Password-protected / encrypted PDF raises 422 EncryptedDocumentError without database insertion."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.create_source = AsyncMock()
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    mock_extract = MagicMock(
        side_effect=EncryptedDocumentError(
            message="Password-protected or encrypted documents cannot be processed."
        )
    )

    transport = ASGITransport(app=app)
    with (
        patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth),
        patch("app.routes.sources.extract_document", mock_extract),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"file": ("locked.pdf", b"%PDF-1.4\nencrypted", "application/pdf")}
            response = await client.post(
                f"/api/research/{SESSION_ID}/sources/document",
                headers={"Authorization": "Bearer alices-token"},
                files=files,
            )

            assert response.status_code == 422
            data = response.json()
            assert data["success"] is False
            assert "Password-protected" in data["message"]
            mock_repo.create_source.assert_not_called()


@pytest.mark.anyio
async def test_add_document_empty_file_rejected_422():
    """Empty 0-byte document is rejected with 422 without database insertion."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.create_source = AsyncMock()
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"file": ("empty.pdf", b"", "application/pdf")}
            response = await client.post(
                f"/api/research/{SESSION_ID}/sources/document",
                headers={"Authorization": "Bearer alices-token"},
                files=files,
            )

            assert response.status_code == 422
            mock_repo.create_source.assert_not_called()


# =============================================================================
# 5. SOURCE LISTING & RETRIEVAL TESTS
# =============================================================================


@pytest.mark.anyio
async def test_list_sources_returns_previews_only():
    """Listing sources returns content_preview and NEVER exposes full extracted_content."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    now_iso = datetime.now(timezone.utc).isoformat()
    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.list_sources = AsyncMock(
        return_value={
            "sources": [
                {
                    "id": SOURCE_ID,
                    "research_id": SESSION_ID,
                    "source_code": "S1",
                    "title": "Preview Item",
                    "url": "https://example.com",
                    "source_type": "website",
                    "content_preview": "This is a 250-character preview...",
                    "published_at": None,
                    "accessed_at": now_iso,
                    "extraction_status": "success",
                    "created_at": now_iso,
                }
            ],
            "total": 1,
            "limit": 50,
            "offset": 0,
        }
    )
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/research/{SESSION_ID}/sources",
                headers={"Authorization": "Bearer alices-token"},
            )

            assert response.status_code == 200
            body = response.json()
            assert body["success"] is True
            assert len(body["data"]["sources"]) == 1
            item = body["data"]["sources"][0]
            assert "content_preview" in item
            assert item["content_preview"] == "This is a 250-character preview..."
            assert "extracted_content" not in item


@pytest.mark.anyio
async def test_list_sources_pagination():
    """limit and offset query parameters are properly forwarded to repository."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.list_sources = AsyncMock(
        return_value={"sources": [], "total": 0, "limit": 10, "offset": 20}
    )
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/research/{SESSION_ID}/sources?limit=10&offset=20",
                headers={"Authorization": "Bearer alices-token"},
            )

            assert response.status_code == 200
            mock_repo.list_sources.assert_awaited_once_with(
                session_id=SESSION_ID,
                user_id=ALICE_ID,
                limit=10,
                offset=20,
            )


@pytest.mark.anyio
async def test_get_source_by_id_returns_full_content():
    """Retrieving a single source returns the full extracted_content."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    now_iso = datetime.now(timezone.utc).isoformat()
    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.get_source_by_id = AsyncMock(
        return_value={
            "id": SOURCE_ID,
            "research_id": SESSION_ID,
            "source_code": "S1",
            "title": "Complete Document",
            "url": None,
            "source_type": "document",
            "extracted_content": "Full unclipped 50,000-character evidence text here.",
            "published_at": None,
            "accessed_at": now_iso,
            "extraction_status": "success",
            "created_at": now_iso,
        }
    )
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/research/{SESSION_ID}/sources/{SOURCE_ID}",
                headers={"Authorization": "Bearer alices-token"},
            )

            assert response.status_code == 200
            body = response.json()
            assert body["success"] is True
            assert body["data"]["id"] == SOURCE_ID
            assert body["data"]["extracted_content"] == "Full unclipped 50,000-character evidence text here."


@pytest.mark.anyio
async def test_get_source_by_id_not_found_returns_404():
    """Non-existent source ID returns HTTP 404."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.get_source_by_id = AsyncMock(return_value=None)
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/research/{SESSION_ID}/sources/{SOURCE_ID}",
                headers={"Authorization": "Bearer alices-token"},
            )

            assert response.status_code == 404
            assert "not found" in response.json()["message"].lower()


# =============================================================================
# 6. SOURCE DELETION TESTS
# =============================================================================


@pytest.mark.anyio
async def test_delete_source_success():
    """Source deletion returns HTTP 200 and standard success envelope."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.delete_source = AsyncMock(return_value=True)
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/research/{SESSION_ID}/sources/{SOURCE_ID}",
                headers={"Authorization": "Bearer alices-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["message"] == "Source deleted successfully"
            mock_repo.delete_source.assert_awaited_once_with(
                session_id=SESSION_ID,
                source_id=SOURCE_ID,
                user_id=ALICE_ID,
            )


@pytest.mark.anyio
async def test_delete_source_not_found_returns_404():
    """Deleting a non-existent or inaccessible source returns HTTP 404."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    mock_repo = MagicMock(spec=SourceRepository)
    mock_repo.delete_source = AsyncMock(return_value=False)
    app.dependency_overrides[get_source_repository] = lambda: mock_repo

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/research/{SESSION_ID}/sources/{SOURCE_ID}",
                headers={"Authorization": "Bearer alices-token"},
            )

            assert response.status_code == 404
            assert "not found" in response.json()["message"].lower()


# =============================================================================
# 7. INPUT VALIDATION TESTS
# =============================================================================


@pytest.mark.parametrize("invalid_id", ["not-a-uuid", "12345", "xyz-abc", "   "])
@pytest.mark.anyio
async def test_invalid_uuid_parameters_return_400(invalid_id: str):
    """Malformed UUID path parameters return HTTP 400 client error."""
    mock_auth = MagicMock()
    mock_auth.auth.get_user.return_value = create_mock_auth_user(user_id=ALICE_ID)

    transport = ASGITransport(app=app)
    with patch("app.dependencies.auth.get_supabase_client", return_value=mock_auth):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Invalid research_id
            res1 = await client.get(
                f"/api/research/{invalid_id}/sources",
                headers={"Authorization": "Bearer alices-token"},
            )
            assert res1.status_code == 400
            assert "Invalid research session ID" in res1.json()["message"]

            # Invalid source_id
            res2 = await client.get(
                f"/api/research/{SESSION_ID}/sources/{invalid_id}",
                headers={"Authorization": "Bearer alices-token"},
            )
            assert res2.status_code == 400
            assert "Invalid source ID" in res2.json()["message"]
