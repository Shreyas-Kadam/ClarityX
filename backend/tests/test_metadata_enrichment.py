"""Automated Test Suite for Phase 2, Milestone 1: Metadata Enrichment & Context Pipeline.

Tests:
1. Domain normalization across various URL shapes, protocols, subdomains, ports, and edge cases.
2. Trafilatura metadata extraction (author, publisher, domain, published_at, last_updated_at).
3. PDF metadata extraction: author, document_created_at, document_modified_at; verifies published_at is None.
4. DOCX metadata extraction: author, document_created_at, document_modified_at; verifies published_at is None.
5. Pasted text extraction: verifies null web metadata.
6. AI prompt construction: includes Domain, Author, Publisher, Publication Date, Last Updated, Accessed Date.
7. System prompt verification: confirms presence of all 9 metadata, attribution, and temporal rules.
8. SourceResponse & SourcePreviewResponse dynamic domain derivation and validation.
9. Repository backward compatibility fallback when database has not yet applied migration 004.
"""

from datetime import datetime, timezone
import io
from unittest.mock import AsyncMock, MagicMock, patch
import docx
import pypdf
import pytest
from postgrest.exceptions import APIError

from app.database.repositories import SourceRepository
from app.schemas.analysis import SourceAnalysisInput
from app.schemas.source import (
    SourcePreviewResponse,
    SourceResponse,
    WebsiteExtractionResult,
    normalize_domain,
)
from app.services.ai_service import build_analysis_prompt
from app.services.extraction_service import (
    DocumentExtractor,
    PastedTextExtractor,
    WebsiteExtractor,
    extract_pasted_text,
    parse_document_date,
)


# =============================================================================
# 1. Domain Normalization Tests
# =============================================================================


def test_domain_normalization_standard_urls():
    """Domain normalization extracts lowercase host and strips www."""
    assert normalize_domain("https://www.nature.com/articles/s41586") == "nature.com"
    assert normalize_domain("http://www.bbc.co.uk/news") == "bbc.co.uk"
    assert normalize_domain("https://en.wikipedia.org/wiki/Quantum") == "en.wikipedia.org"
    assert normalize_domain("https://SUB.DOMAIN.EXAMPLE.COM/path") == "sub.domain.example.com"


def test_domain_normalization_ports_and_credentials():
    """Domain normalization strips ports and userinfo."""
    assert normalize_domain("http://user:pass@example.com:8080/path") == "example.com"
    assert normalize_domain("https://api.internal.org:443/data") == "api.internal.org"


def test_domain_normalization_bare_and_schemeless():
    """Domain normalization works on bare domains and schemeless URLs."""
    assert normalize_domain("www.researchgate.net") == "researchgate.net"
    assert normalize_domain("arxiv.org/abs/2103.00020") == "arxiv.org"
    assert normalize_domain("//cdn.example.org/assets") == "cdn.example.org"


def test_domain_normalization_empty_and_invalid():
    """Invalid or empty inputs return None safely."""
    assert normalize_domain(None) is None
    assert normalize_domain("") is None
    assert normalize_domain("   ") is None
    assert normalize_domain("not a valid domain") is None


# =============================================================================
# 2. Document Date Parsing Tests
# =============================================================================


def test_parse_document_date_pdf_format():
    """Parses standard PDF creation date format D:YYYYMMDDHHmmSS."""
    pdf_date = "D:20240315143022"
    parsed = parse_document_date(pdf_date)
    assert parsed is not None
    assert parsed.year == 2024
    assert parsed.month == 3
    assert parsed.day == 15


def test_parse_document_date_iso_and_datetime():
    """Parses ISO strings and passes through existing datetime objects."""
    iso_date = "2025-06-12T10:00:00Z"
    parsed = parse_document_date(iso_date)
    assert parsed is not None
    assert parsed.year == 2025

    now = datetime.now(timezone.utc)
    assert parse_document_date(now) == now
    assert parse_document_date(None) is None
    assert parse_document_date("invalid-date-string") is None


# =============================================================================
# 3. Website Extraction Metadata Enrichment Tests
# =============================================================================


@pytest.mark.anyio
async def test_website_extraction_metadata_enrichment():
    """Trafilatura HTML extraction captures author, publisher, domain, and timestamps."""
    sample_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Quantum Supremacy Milestone</title>
        <meta name="author" content="Dr. Jane Doe">
        <meta property="og:site_name" content="Tech Science Review">
        <meta name="date" content="2025-01-10">
        <meta property="article:modified_time" content="2025-01-15T12:00:00Z">
    </head>
    <body>
        <main>
            <h1>Quantum Supremacy Milestone</h1>
            <p>
                Researchers have demonstrated quantum computational advantages on real-world algorithms,
                surpassing classical supercomputers across cryptographic simulation workloads.
                This breakthrough enables high-speed factoring and simulated material optimization.
            </p>
        </main>
    </body>
    </html>
    """

    with patch(
        "app.services.extraction_service.fetch_website_content",
        return_value=(sample_html, "https://www.techsciencereview.com/quantum", 200),
    ):
        extractor = WebsiteExtractor()
        result = await extractor.extract("https://www.techsciencereview.com/quantum")

        assert result.extraction_status == "success"
        assert result.domain == "techsciencereview.com"
        assert "Jane Doe" in (result.author or "")
        assert result.publisher == "Tech Science Review"
        assert result.published_at is not None
        assert result.published_at.year == 2025
        assert result.last_updated_at is not None
        assert result.last_updated_at.year == 2025
        assert result.last_updated_at.day == 15


# =============================================================================
# 4. Document Metadata Enrichment Tests (PDF and DOCX)
# =============================================================================


def test_pdf_extraction_metadata_and_date_separation():
    """PDF extraction extracts author and document_created_at, but leaves published_at None."""
    extractor = DocumentExtractor()

    # Create a small valid PDF in memory using pypdf
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    # Add minimal readable text page
    page = writer.pages[0]
    # Inject metadata
    writer.add_metadata({
        "/Author": "Alice Smith",
        "/Title": "Internal Technical Specification",
        "/CreationDate": "D:20240101120000",
        "/ModDate": "D:20240201120000",
    })

    pdf_buffer = io.BytesIO()
    writer.write(pdf_buffer)
    pdf_bytes = pdf_buffer.getvalue()

    # Mock extract_text on page to ensure readable text is returned
    with patch("pypdf.PageObject.extract_text", return_value="This is extracted PDF content with technical requirements."):
        result = extractor._extract_pdf(pdf_bytes, "tech_spec.pdf")

        assert result.extraction_status == "success"
        assert result.author == "Alice Smith"
        assert result.document_created_at is not None
        assert result.document_created_at.year == 2024
        assert result.document_modified_at is not None
        assert result.document_modified_at.year == 2024

        # Crucial Rule: document_created_at must NOT be published_at
        # DocumentExtractionResult does not even expose published_at
        assert not hasattr(result, "published_at") or getattr(result, "published_at", None) is None


def test_docx_extraction_metadata_and_date_separation():
    """DOCX extraction extracts author and created/modified dates without setting published_at."""
    extractor = DocumentExtractor()

    # Create a valid DOCX document in memory
    doc = docx.Document()
    doc.add_heading("Architecture Overview", level=1)
    doc.add_paragraph("This document outlines the distributed system architecture and reliability goals.")
    doc.core_properties.author = "Bob Johnson"
    doc.core_properties.title = "Architecture Overview"
    doc.core_properties.created = datetime(2023, 11, 20, 9, 30, tzinfo=timezone.utc)
    doc.core_properties.modified = datetime(2023, 12, 1, 15, 0, tzinfo=timezone.utc)

    docx_buffer = io.BytesIO()
    doc.save(docx_buffer)
    docx_bytes = docx_buffer.getvalue()

    result = extractor._extract_docx(docx_bytes, "arch.docx")

    assert result.extraction_status == "success"
    assert result.title == "Architecture Overview"
    assert result.author == "Bob Johnson"
    assert result.document_created_at is not None
    assert result.document_created_at.year == 2023
    assert result.document_modified_at is not None
    assert result.document_modified_at.month == 12


# =============================================================================
# 5. Pasted Text Metadata Tests
# =============================================================================


def test_pasted_text_null_metadata():
    """Pasted text has direct content without fabricated metadata."""
    res = extract_pasted_text(
        text="Executive summary of market trends in renewable energy storage.",
        title="Market Summary",
    )
    assert res.extraction_status == "success"
    assert res.title == "Market Summary"
    assert res.source_type == "pasted_text"
    assert not hasattr(res, "url")
    assert not hasattr(res, "domain")


# =============================================================================
# 6. SourceResponse and SourcePreviewResponse Domain Derivation Tests
# =============================================================================


def test_source_response_dynamic_domain_derivation():
    """SourceResponse automatically derives domain from url when domain is None."""
    now = datetime.now(timezone.utc)
    resp = SourceResponse(
        id="11111111-1111-1111-1111-111111111111",
        research_id="22222222-2222-2222-2222-222222222222",
        source_code="S1",
        title="Sample News",
        url="https://www.reuters.com/business/finance",
        source_type="website",
        extracted_content="Financial markets posted modest gains today.",
        accessed_at=now,
        created_at=now,
        extraction_status="success",
    )
    assert resp.domain == "reuters.com"
    assert resp.character_count == len("Financial markets posted modest gains today.")
    assert resp.word_count == 6


def test_source_preview_response_dynamic_domain_derivation():
    """SourcePreviewResponse derives domain dynamically from url."""
    now = datetime.now(timezone.utc)
    prev = SourcePreviewResponse(
        id="11111111-1111-1111-1111-111111111111",
        research_id="22222222-2222-2222-2222-222222222222",
        source_code="S1",
        title="Sample News",
        url="https://www.technologyreview.com/2025/ai",
        source_type="website",
        content_preview="AI advancements in robotics...",
        accessed_at=now,
        created_at=now,
        extraction_status="success",
    )
    assert prev.domain == "technologyreview.com"


# =============================================================================
# 7. AI Prompt Construction and Metadata Pipeline Tests
# =============================================================================


def test_ai_prompt_metadata_blocks():
    """build_analysis_prompt embeds Domain, Author, Publisher, and Dates into source blocks."""
    pub_dt = datetime(2025, 4, 1, 10, 0, tzinfo=timezone.utc)
    upd_dt = datetime(2025, 4, 5, 12, 0, tzinfo=timezone.utc)
    acc_dt = datetime(2025, 4, 10, 8, 30, tzinfo=timezone.utc)

    sources = [
        SourceAnalysisInput(
            source_code="S1",
            title="Battery Tech Report",
            source_type="website",
            url="https://www.cleanenergy.org/battery-report",
            domain="cleanenergy.org",
            author="Dr. Sarah Connor",
            publisher="Clean Energy Institute",
            published_at=pub_dt,
            last_updated_at=upd_dt,
            accessed_at=acc_dt,
            extracted_content="Solid state batteries achieved 500 Wh/kg density.",
        ),
        SourceAnalysisInput(
            source_code="S2",
            title="Meeting Notes",
            source_type="pasted_text",
            url=None,
            domain=None,
            author=None,
            publisher=None,
            published_at=None,
            last_updated_at=None,
            accessed_at=acc_dt,
            extracted_content="Team decided to evaluate solid state battery suppliers.",
        ),
    ]

    system_prompt, user_prompt = build_analysis_prompt(
        research_goal="Investigate solid state battery density milestones",
        sources=sources,
    )

    # Check S1 formatted block
    assert "--- BEGIN SOURCE [S1] ---" in user_prompt
    assert "Domain: cleanenergy.org" in user_prompt
    assert "Author: Dr. Sarah Connor" in user_prompt
    assert "Publisher: Clean Energy Institute" in user_prompt
    assert "Publication Date: 2025-04-01" in user_prompt
    assert "Last Updated: 2025-04-05" in user_prompt
    assert "Accessed Date: 2025-04-10" in user_prompt

    # Check S2 formatted block (null defaults)
    assert "--- BEGIN SOURCE [S2] ---" in user_prompt
    assert "Domain: N/A" in user_prompt
    assert "Author: Unknown" in user_prompt
    assert "Publisher: Unknown" in user_prompt
    assert "Publication Date: Undetermined" in user_prompt
    assert "Last Updated: N/A" in user_prompt


def test_system_prompt_contains_all_9_metadata_rules():
    """System prompt explicitly contains the 9 source metadata, attribution, and temporal rules."""
    sources = [
        SourceAnalysisInput(
            source_code="S1",
            title="Sample",
            source_type="website",
            extracted_content="Content",
        )
    ]
    system_prompt, _ = build_analysis_prompt("Research Goal", sources)

    assert "=== SOURCE METADATA, ATTRIBUTION & TEMPORAL RULES ===" in system_prompt
    assert "1. Attribution Reliability:" in system_prompt
    assert "2. Publication vs Modification:" in system_prompt
    assert "3. Temporal Freshness:" in system_prompt
    assert "4. Undetermined Dates:" in system_prompt
    assert "5. Domain Context:" in system_prompt
    assert "6. Pasted Text and Documents:" in system_prompt
    assert "7. Cross-Source Attribution:" in system_prompt
    assert "8. Evidence Grounding:" in system_prompt
    assert "9. Missing vs Disproven:" in system_prompt


# =============================================================================
# 8. Repository Backward Compatibility Tests
# =============================================================================


@pytest.mark.anyio
async def test_repository_backward_compatible_fallback_on_missing_columns():
    """SourceRepository falls back to base columns if PostgREST rejects new columns."""
    mock_client = MagicMock()

    # Session ownership query
    mock_session_query = MagicMock()
    mock_session_query.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "sess-1"}]
    )

    mock_sources = MagicMock()
    # select handles count_sources first, then get_next_source_code
    mock_sources.select.return_value.eq.return_value.execute.side_effect = [
        MagicMock(data=[], count=0),
        MagicMock(data=[]),
    ]

    first_error = APIError({"message": "Could not find the 'author' column in the schema cache", "code": "PGRST204"})
    # insert handles first call (raises missing column error), then fallback call (succeeds)
    mock_sources.insert.return_value.execute.side_effect = [
        first_error,
        MagicMock(
            data=[{
                "id": "src-uuid-1",
                "research_id": "sess-1",
                "source_code": "S1",
                "title": "Fallback Source",
                "url": "https://example.com",
                "source_type": "website",
                "extracted_content": "Extracted text content.",
                "published_at": None,
                "extraction_status": "success",
                "created_at": "2026-04-15T00:00:00Z",
            }]
        ),
    ]

    def table_router(table_name):
        if table_name == "research_sessions":
            return mock_session_query
        return mock_sources

    mock_client.table.side_effect = table_router

    repo = SourceRepository(client=mock_client)
    res = await repo.create_source(
        session_id="sess-1",
        user_id="user-1",
        source_type="website",
        extracted_content="Extracted text content.",
        title="Fallback Source",
        url="https://example.com",
        author="John Doe",
        publisher="Example News",
        domain="example.com",
    )

    assert res is not None
    assert res["id"] == "src-uuid-1"
    # Metadata re-attached in memory on fallback
    assert res["author"] == "John Doe"
    assert res["publisher"] == "Example News"
    assert res["domain"] == "example.com"
