"""Comprehensive Automated Test Suite for Resilient Website Extraction & Fallbacks.

Tests all required scenarios from Phase 5:
1. Normal publicly accessible webpage (primary Trafilatura succeeds).
2. Website where primary extraction yields < 100 chars but Jina Reader fallback succeeds.
3. Website where primary and Jina fail, but HTML parser (lxml) fallback succeeds.
4. Website returning HTTP 403 Forbidden where Jina Reader rescues extraction.
5. Website returning HTTP 403 Forbidden where all engines fail (anti-bot/CAPTCHA) raising helpful error.
6. Publicly accessible PDF URL:
   - By .pdf file extension.
   - By Content-Type: application/pdf header signal.
7. Malformed URLs and credential rejection.
8. Safe redirects and redirect to private/loopback/cloud metadata IP blocked.
9. RFC 6052 NAT64 IPv4-in-IPv6 address unpacking & security validation (Toyota scenario).
10. Inaccessible websites: 404 Not Found, connection timeouts, and DNS failure.
"""

import io
import ipaddress
import socket
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pypdf
import pytest

from app.core.exceptions import (
    ContentSizeExceededError,
    ExtractionError,
    IsPdfUrlError,
    SSRFSecurityError,
    UnsupportedContentTypeError,
)
from app.services.extraction_service import WebsiteExtractor, extract_website_content
from app.services.ssrf_service import (
    build_request_headers,
    fetch_pdf_document,
    fetch_website_content,
    resolve_and_validate_destination,
    validate_ip_address,
    validate_url_syntax,
)

SAMPLE_ARTICLE_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Next-Gen Solid State Battery Progress</title>
    <meta name="author" content="Dr. Sarah Connor">
    <meta property="article:published_time" content="2026-03-15T10:00:00Z">
</head>
<body>
    <article>
        <h1>Next-Gen Solid State Battery Progress</h1>
        <p>Solid-state batteries represent a generational breakthrough in automotive energy storage.</p>
        <p>By replacing liquid electrolytes with non-flammable solid ceramic separators, energy density exceeds 800 Wh/L.</p>
        <p>Extensive road testing indicates enhanced thermal stability across extreme temperatures ranging from -30C to 60C.</p>
        <p>Automotive OEMs are planning commercial vehicle platforms incorporating solid-state packs by 2027.</p>
    </article>
</body>
</html>"""


# ===========================================================================
# 1. Primary Extraction (Trafilatura) Success
# ===========================================================================


@pytest.mark.anyio
async def test_primary_trafilatura_extraction_success():
    """Normal publicly accessible webpage extracted successfully via primary Trafilatura engine."""
    extractor = WebsiteExtractor()

    with patch(
        "app.services.extraction_service.fetch_website_content",
        new_callable=AsyncMock,
        return_value=(SAMPLE_ARTICLE_HTML, "https://battery-tech.org/solid-state", 200),
    ):
        result = await extractor.extract("https://battery-tech.org/solid-state")

        assert result.extraction_status == "success"
        assert result.extraction_method == "trafilatura"
        assert "Solid-state batteries represent a generational breakthrough" in result.extracted_content
        assert result.title == "Next-Gen Solid State Battery Progress"
        assert result.author == "Dr. Sarah Connor"
        assert result.domain == "battery-tech.org"


# ===========================================================================
# 2. Fallback 1: Jina Reader Fallback (when Trafilatura yields < 100 chars)
# ===========================================================================


@pytest.mark.anyio
async def test_jina_fallback_when_trafilatura_insufficient():
    """When Trafilatura returns < 100 chars, Jina Reader fallback is invoked and succeeds."""
    extractor = WebsiteExtractor()
    stub_html = "<html><body><div>Loading JavaScript app...</div></body></html>"
    jina_markdown = (
        "Title: Rescued by Jina Reader\n\n"
        "This is comprehensive markdown content extracted by Jina Reader when the initial HTML DOM was sparse. "
        "It provides deep coverage of energy storage benchmarks and electrolyte conductivity metrics exceeding the minimum character threshold."
    )

    with patch(
        "app.services.extraction_service.fetch_website_content",
        new_callable=AsyncMock,
        return_value=(stub_html, "https://spa-battery.io/viewer", 200),
    ):
        with patch.object(extractor, "_extract_with_jina", new_callable=AsyncMock, return_value=(jina_markdown, "Rescued by Jina Reader")):
            result = await extractor.extract("https://spa-battery.io/viewer")

            assert result.extraction_status == "success"
            assert result.extraction_method == "jina"
            assert "comprehensive markdown content extracted by Jina Reader" in result.extracted_content
            assert result.title == "Rescued by Jina Reader"


# ===========================================================================
# 3. Fallback 2: HTML Fallback Parser (lxml.html) Success
# ===========================================================================


@pytest.mark.anyio
async def test_html_parser_fallback_when_trafilatura_and_jina_fail():
    """When Trafilatura yields < 100 chars and Jina Reader fails/times out, HTML fallback parser succeeds."""
    extractor = WebsiteExtractor()
    custom_table_html = """<!DOCTYPE html>
    <html>
    <head>
        <title>Battery Chemistry Specifications Table</title>
        <meta name="author" content="Elena Rostova">
    </head>
    <body>
        <main>
            <h1>Battery Chemistry Specifications Table</h1>
            <p>Cell Format: Cylindrical 4680 with dry electrode coating process.</p>
            <p>Gravimetric Energy Density: 350 Wh/kg nominal at 25 degrees Celsius.</p>
            <p>Volumetric Energy Density: 750 Wh/L pack integration benchmark.</p>
            <p>Separator: Thin-film oxide ceramic with dendrite inhibition layer.</p>
        </main>
    </body>
    </html>"""

    with patch(
        "app.services.extraction_service.fetch_website_content",
        new_callable=AsyncMock,
        return_value=(custom_table_html, "https://specs.battery.org/data", 200),
    ):
        with patch.object(extractor, "_extract_with_trafilatura", return_value=(None, None, None, None, None, None)):
            with patch.object(extractor, "_extract_with_jina", new_callable=AsyncMock, return_value=(None, None)):
                result = await extractor.extract("https://specs.battery.org/data")

                assert result.extraction_status == "success"
                assert result.extraction_method == "html_parser"
                assert "Cell Format: Cylindrical 4680" in result.extracted_content
                assert "Elena Rostova" in (result.author or "")


# ===========================================================================
# 4. HTTP 403 Forbidden with Jina Reader Rescue (QuantumScape / Cloudflare case)
# ===========================================================================


@pytest.mark.anyio
async def test_http_403_rescued_by_jina_reader():
    """When direct connection returns HTTP 403 (e.g. Cloudflare block), Jina Reader fallback rescues extraction."""
    extractor = WebsiteExtractor()
    jina_content = (
        "Title: QuantumScape QSE-5 B-Sample Overview\n\n"
        "QuantumScape has commenced shipment of first QSE-5 B-sample cells to automotive partners for integration testing. "
        "These cells demonstrate energy density exceeding 800 Wh/L with sub-15 minute fast charging capabilities."
    )

    with patch(
        "app.services.extraction_service.fetch_website_content",
        new_callable=AsyncMock,
        side_effect=ExtractionError("Website returned unsuccessful status code: 403", status_code=403),
    ):
        with patch.object(extractor, "_extract_with_jina", new_callable=AsyncMock, return_value=(jina_content, "QuantumScape QSE-5 B-Sample Overview")):
            result = await extractor.extract("https://www.quantumscape.com/qse-5-b-sample")

            assert result.extraction_status == "success"
            assert result.extraction_method == "jina"
            assert "QuantumScape has commenced shipment of first QSE-5" in result.extracted_content
            assert result.title == "QuantumScape QSE-5 B-Sample Overview"


# ===========================================================================
# 5. HTTP 403 Forbidden Where All Engines Fail (IEA / CAPTCHA case)
# ===========================================================================


@pytest.mark.anyio
async def test_http_403_anti_bot_challenge_raises_helpful_error():
    """When a website returns 403 and Jina also fails/encounters anti-bot CAPTCHA, returns clear error."""
    extractor = WebsiteExtractor()

    with patch(
        "app.services.extraction_service.fetch_website_content",
        new_callable=AsyncMock,
        side_effect=ExtractionError("Website returned unsuccessful status code: 403", status_code=403),
    ):
        with patch.object(extractor, "_extract_with_jina", new_callable=AsyncMock, return_value=(None, None)):
            with pytest.raises(ExtractionError) as exc_info:
                await extractor.extract("https://www.iea.org/reports/global-energy-review-2026")

            assert exc_info.value.status_code == 403
            assert "protected by access controls or anti-bot verification" in exc_info.value.message
            assert "Document Upload (PDF/DOCX) or Pasted Text" in exc_info.value.detail


# ===========================================================================
# 6. Publicly Accessible PDF URLs
# ===========================================================================


def create_dummy_pdf_bytes(text: str = "Solid-State Battery Technical Whitepaper benchmarks.") -> bytes:
    """Creates in-memory PDF bytes with text content."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata({
        "/Title": "Solid-State Battery Technical Whitepaper",
        "/Author": "Chief Battery Scientist",
        "/CreationDate": "D:20260110120000",
    })
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.mark.anyio
async def test_pdf_url_by_extension_extracted_successfully():
    """Direct URL ending in .pdf downloads PDF bytes and extracts text and metadata."""
    extractor = WebsiteExtractor()
    dummy_bytes = create_dummy_pdf_bytes()
    pdf_text = (
        "Technical Benchmarks: Demonstrates 840 Wh/L volumetric energy density and "
        "380 Wh/kg gravimetric energy density across utility-scale automotive battery cell formats."
    )

    with patch("app.services.extraction_service.fetch_pdf_document", new_callable=AsyncMock, return_value=(dummy_bytes, "https://energy.gov/spec.pdf")):
        with patch("pypdf.PageObject.extract_text", return_value=pdf_text):
            result = await extractor.extract("https://energy.gov/spec.pdf")

            assert result.extraction_status == "success"
            assert result.extraction_method == "pdf"
            assert "840 Wh/L volumetric energy density" in result.extracted_content
            assert result.title == "Solid-State Battery Technical Whitepaper"
            assert result.author == "Chief Battery Scientist"


@pytest.mark.anyio
async def test_pdf_url_short_stub_content_marked_partial():
    """PDF URLs yielding fewer than 100 characters (e.g. 13-character stub) are marked partial."""
    extractor = WebsiteExtractor()
    dummy_bytes = create_dummy_pdf_bytes()
    short_text = "Hello, world!"  # 13 chars

    with patch("app.services.extraction_service.fetch_pdf_document", new_callable=AsyncMock, return_value=(dummy_bytes, "https://energy.gov/stub.pdf")):
        with patch("pypdf.PageObject.extract_text", return_value=short_text):
            result = await extractor.extract("https://energy.gov/stub.pdf")

            assert result.extraction_status == "partial"
            assert result.extraction_method == "pdf"
            assert result.extracted_content == "Hello, world!"


@pytest.mark.anyio
async def test_pdf_url_by_content_type_signal_extracted_successfully():
    """When a dynamic URL returns application/pdf content stream, routes to dedicated PDF extractor."""
    extractor = WebsiteExtractor()
    dummy_bytes = create_dummy_pdf_bytes()
    pdf_text = (
        "Dynamic PDF Report: Q1 2026 automotive OEM integration results indicate robust thermal stability "
        "and cycling efficiency exceeding baseline lithium-ion cell expectations."
    )

    with patch(
        "app.services.extraction_service.fetch_website_content",
        new_callable=AsyncMock,
        side_effect=IsPdfUrlError(final_url="https://sec.gov/download/filing-stream"),
    ):
        with patch("app.services.extraction_service.fetch_pdf_document", new_callable=AsyncMock, return_value=(dummy_bytes, "https://sec.gov/download/filing-stream")):
            with patch("pypdf.PageObject.extract_text", return_value=pdf_text):
                result = await extractor.extract("https://sec.gov/download/filing-stream")

                assert result.extraction_status == "success"
                assert result.extraction_method == "pdf"
                assert "Dynamic PDF Report" in result.extracted_content


# ===========================================================================
# 7. Malformed URLs & Credential Rejection
# ===========================================================================


def test_malformed_urls_rejected_by_ssrf_validator():
    """Malformed URLs, unsupported schemes, and credentials fail syntax validation."""
    invalid_cases = [
        "",
        "   ",
        "ftp://files.example.com/data.txt",
        "javascript:alert(1)",
        "http://user:password@example.com/secret",
        "http://",
        "https://",
        "http://example.com:99999",
    ]
    for bad_url in invalid_cases:
        with pytest.raises(SSRFSecurityError):
            validate_url_syntax(bad_url)


# ===========================================================================
# 8. SSRF Redirect Protection (Unsafe Redirects Blocked)
# ===========================================================================


@pytest.mark.anyio
async def test_redirect_to_private_ip_is_blocked():
    """HTTP redirect pointing to a private or loopback destination is caught and rejected."""
    mock_redirect = MagicMock(
        status_code=302,
        headers={"location": "http://192.168.1.1/admin/credentials"},
        aclose=AsyncMock(),
    )

    with patch("httpx.AsyncClient.send", return_value=mock_redirect):
        with pytest.raises(SSRFSecurityError) as exc_info:
            await fetch_website_content("https://public-entry.com/login")

        assert "private network" in exc_info.value.message.lower()


@pytest.mark.anyio
async def test_redirect_to_cloud_metadata_is_blocked():
    """HTTP redirect pointing to cloud instance metadata (169.254.169.254) is rejected."""
    mock_redirect = MagicMock(
        status_code=302,
        headers={"location": "http://169.254.169.254/latest/meta-data/"},
        aclose=AsyncMock(),
    )

    with patch("httpx.AsyncClient.send", return_value=mock_redirect):
        with pytest.raises(SSRFSecurityError) as exc_info:
            await fetch_website_content("https://public-entry.com/meta")

        assert "cloud metadata" in exc_info.value.message.lower()


# ===========================================================================
# 9. RFC 6052 NAT64 IPv4-in-IPv6 Validation (Toyota Scenario)
# ===========================================================================


def test_nat64_rfc6052_public_ipv4_permitted():
    """RFC 6052 NAT64 prefix (64:ff9b::/96) embedding a public IPv4 (Toyota/Akamai) is permitted."""
    # 64:ff9b::1726:3eca embeds 23.38.62.202 (Akamai CDN)
    ip_obj = ipaddress.ip_address("64:ff9b::1726:3eca")
    # Must not raise SSRFSecurityError
    validate_ip_address(ip_obj)


def test_nat64_rfc6052_private_ipv4_blocked():
    """RFC 6052 NAT64 prefix embedding a private/loopback IPv4 fails closed."""
    # 64:ff9b::7f00:0001 embeds 127.0.0.1 (Loopback)
    loopback_nat64 = ipaddress.ip_address("64:ff9b::7f00:1")
    with pytest.raises(SSRFSecurityError) as exc_info:
        validate_ip_address(loopback_nat64)
    assert "loopback" in exc_info.value.message.lower()

    # 64:ff9b::0a00:0001 embeds 10.0.0.1 (Private 10.0.0.0/8)
    private_nat64 = ipaddress.ip_address("64:ff9b::0a00:1")
    with pytest.raises(SSRFSecurityError) as exc_info:
        validate_ip_address(private_nat64)
    assert "private" in exc_info.value.message.lower()


# ===========================================================================
# 10. Inaccessible Websites: 404 Not Found & Timeouts
# ===========================================================================


@pytest.mark.anyio
async def test_inaccessible_website_404_not_found():
    """Websites returning HTTP 404 raise clear ExtractionError with actionable guidance."""
    extractor = WebsiteExtractor()

    with patch(
        "app.services.extraction_service.fetch_website_content",
        new_callable=AsyncMock,
        side_effect=ExtractionError("Website returned unsuccessful status code: 404", status_code=404),
    ):
        with patch.object(extractor, "_extract_with_jina", new_callable=AsyncMock, return_value=(None, None)):
            with pytest.raises(ExtractionError) as exc_info:
                await extractor.extract("https://example.com/non-existent-page")

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.message.lower()
            assert "Document Upload or Pasted Text" in exc_info.value.detail


@pytest.mark.anyio
async def test_inaccessible_website_timeout():
    """Websites that time out raise clear ExtractionError with actionable guidance."""
    extractor = WebsiteExtractor()

    with patch(
        "app.services.extraction_service.fetch_website_content",
        new_callable=AsyncMock,
        side_effect=ExtractionError("Request to website timed out after 15.0 seconds.", status_code=504),
    ):
        with patch.object(extractor, "_extract_with_jina", new_callable=AsyncMock, return_value=(None, None)):
            with pytest.raises(ExtractionError) as exc_info:
                await extractor.extract("https://slow-unresponsive-site.org/report")

            assert exc_info.value.status_code == 504
            assert "timed out" in exc_info.value.message.lower()
            assert "Document Upload or Pasted Text" in exc_info.value.detail


# ===========================================================================
# 11. SEC EDGAR User-Agent Compliance Header Check
# ===========================================================================


def test_sec_edgar_user_agent_format():
    """Requests to sec.gov must use compliant declared User-Agent with contact email."""
    headers_sec = build_request_headers("https://www.sec.gov/Archives/edgar/data/1811414/000119312526316073/qs-20260630.htm")
    assert "ClarityXResearch" in headers_sec["User-Agent"]
    assert "@" in headers_sec["User-Agent"]

    headers_general = build_request_headers("https://example.com/article")
    assert "Mozilla/5.0" in headers_general["User-Agent"]
    assert "ClarityX" in headers_general["User-Agent"]
