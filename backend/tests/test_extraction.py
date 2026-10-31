"""Automated Test Suite for Website Extraction & SSRF Security (Checkpoint 4.1).

Tests:
1. SSRF URL validation and IP address filtering (IPv4, IPv6, loopback, private, link-local, cloud metadata).
2. DNS resolution failure and credential rejection.
3. Redirect security (safe redirects followed, unsafe redirects blocked, loop limit enforced).
4. Trafilatura primary HTML extraction (content, title, publication date).
5. Jina Reader fallback execution when Trafilatura returns < 100 characters.
6. Error conditions: unsupported content types, response size limits, HTTP errors, timeouts.
"""

import ipaddress
import socket
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from app.core.exceptions import (
    ContentSizeExceededError,
    ExtractionError,
    SSRFSecurityError,
    UnsupportedContentTypeError,
)
from app.services.extraction_service import WebsiteExtractor, extract_website_content
from app.services.ssrf_service import (
    fetch_website_content,
    resolve_and_validate_destination,
    validate_ip_address,
    validate_url_syntax,
)

# ---------------------------------------------------------------------------
# SSRF Validation Tests
# ---------------------------------------------------------------------------


def test_valid_public_http_url():
    """Valid HTTP public URLs should pass syntax validation."""
    scheme, host, port = validate_url_syntax("http://example.com/research-paper")
    assert scheme == "http"
    assert host == "example.com"
    assert port == 80


def test_valid_public_https_url():
    """Valid HTTPS public URLs should pass syntax validation."""
    scheme, host, port = validate_url_syntax("https://en.wikipedia.org/wiki/Quantum_computing")
    assert scheme == "https"
    assert host == "en.wikipedia.org"
    assert port == 443


def test_localhost_rejection():
    """Localhost and variations must be rejected."""
    prohibited_urls = [
        "http://localhost/admin",
        "http://localhost:8000/api",
        "https://LOCALHOST/secret",
        "http://app.localhost/metrics",
        "http://service.local/status",
        "http://api.internal/data",
    ]
    for url in prohibited_urls:
        with pytest.raises(SSRFSecurityError) as exc_info:
            validate_url_syntax(url)
        assert "prohibited" in exc_info.value.message.lower()


def test_ipv4_loopback_rejection():
    """Loopback IPv4 addresses (127.0.0.0/8) must be blocked."""
    loopbacks = [
        "127.0.0.1",
        "127.0.0.2",
        "127.1.2.3",
        "127.255.255.255",
    ]
    for ip_str in loopbacks:
        ip = ipaddress.ip_address(ip_str)
        with pytest.raises(SSRFSecurityError) as exc_info:
            validate_ip_address(ip)
        assert "loopback" in exc_info.value.message.lower()


def test_private_ipv4_rejection():
    """RFC 1918 private IPv4 addresses must be blocked."""
    private_ips = [
        "10.0.0.1",
        "10.255.255.254",
        "172.16.0.1",
        "172.31.255.254",
        "192.168.0.1",
        "192.168.1.254",
    ]
    for ip_str in private_ips:
        ip = ipaddress.ip_address(ip_str)
        with pytest.raises(SSRFSecurityError) as exc_info:
            validate_ip_address(ip)
        assert "private" in exc_info.value.message.lower()


def test_link_local_and_cloud_metadata_rejection():
    """Link-local (169.254.0.0/16) and cloud instance metadata addresses must be blocked."""
    metadata_ips = [
        "169.254.169.254",  # AWS / Azure / GCP metadata
        "169.254.169.253",  # AWS DNS
        "169.254.1.1",      # General link-local
        "100.100.100.200",  # Alibaba Cloud metadata
    ]
    for ip_str in metadata_ips:
        ip = ipaddress.ip_address(ip_str)
        with pytest.raises(SSRFSecurityError) as exc_info:
            validate_ip_address(ip)
        assert any(term in exc_info.value.message.lower() for term in ("metadata", "link-local", "private"))


def test_ipv6_loopback_and_metadata_rejection():
    """IPv6 loopback, link-local, and AWS IPv6 metadata must be blocked."""
    ipv6_prohibited = [
        "::1",            # Loopback
        "fe80::1",        # Link-local
        "fd00:ec2::254",  # AWS IPv6 metadata
        "::ffff:127.0.0.1", # IPv4-mapped loopback
        "::ffff:169.254.169.254", # IPv4-mapped metadata
    ]
    for ip_str in ipv6_prohibited:
        ip = ipaddress.ip_address(ip_str)
        with pytest.raises(SSRFSecurityError):
            validate_ip_address(ip)


def test_reserved_and_multicast_rejection():
    """Multicast, reserved, and unspecified addresses must be blocked."""
    ips = [
        "0.0.0.0",          # Unspecified
        "::",               # IPv6 unspecified
        "224.0.0.1",        # Multicast
        "ff02::1",          # IPv6 Multicast
        "240.0.0.1",        # Reserved Class E
    ]
    for ip_str in ips:
        ip = ipaddress.ip_address(ip_str)
        with pytest.raises(SSRFSecurityError):
            validate_ip_address(ip)


def test_unsupported_scheme_rejection():
    """Schemes other than HTTP and HTTPS must be rejected."""
    prohibited_schemes = [
        "file:///etc/passwd",
        "ftp://ftp.example.com/file",
        "gopher://gopher.example.com",
        "data:text/html,<html>Evil</html>",
        "javascript:alert(1)",
    ]
    for url in prohibited_schemes:
        with pytest.raises(SSRFSecurityError) as exc_info:
            validate_url_syntax(url)
        assert "unsupported scheme" in exc_info.value.message.lower()


def test_url_credentials_rejection():
    """URLs containing embedded user credentials must be rejected."""
    urls_with_creds = [
        "http://admin:secret@example.com/page",
        "https://user@example.com/dashboard",
        "http://user:password@1.1.1.1/",
    ]
    for url in urls_with_creds:
        with pytest.raises(SSRFSecurityError) as exc_info:
            validate_url_syntax(url)
        assert "credentials" in exc_info.value.message.lower()


def test_dns_resolution_failure():
    """Hosts that fail DNS resolution must raise SSRFSecurityError."""
    with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name resolution failure")):
        with pytest.raises(SSRFSecurityError) as exc_info:
            resolve_and_validate_destination("nonexistent-domain-xyz123.org", 80)
        assert "dns resolution failed" in exc_info.value.message.lower()


def test_dns_rebinding_mixed_resolution_fails_closed():
    """If a host resolves to both a public IP and a private IP, it must fail closed."""
    # Simulate DNS returning a public IP followed by a private IP
    mock_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80)),
    ]
    with patch("socket.getaddrinfo", return_value=mock_addrinfo):
        with pytest.raises(SSRFSecurityError) as exc_info:
            resolve_and_validate_destination("dual-homed-target.com", 80)
        assert "loopback" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# HTTP Fetching & Redirect Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_unsafe_redirect_rejection():
    """Redirects to private / internal IPs must be intercepted and rejected."""
    # Mock initial response as 302 pointing to an internal loopback target
    mock_redirect_response = MagicMock()
    mock_redirect_response.status_code = 302
    mock_redirect_response.headers = {"location": "http://127.0.0.1:8000/internal-admin"}
    mock_redirect_response.aclose = AsyncMock()

    with patch("httpx.AsyncClient.send", return_value=mock_redirect_response):
        with pytest.raises(SSRFSecurityError) as exc_info:
            await fetch_website_content("http://public-site.com/bounce")
        assert any(term in exc_info.value.message.lower() for term in ("prohibited", "loopback", "private"))


@pytest.mark.anyio
async def test_multiple_redirect_handling_within_limit():
    """Safe redirects within the maximum limit (5) should be followed successfully."""
    mock_hop1 = MagicMock(status_code=301, headers={"location": "https://public-site.com/hop2"}, aclose=AsyncMock())
    mock_hop2 = MagicMock(status_code=302, headers={"location": "https://public-site.com/final"}, aclose=AsyncMock())

    # Final response
    mock_final = MagicMock(
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        encoding="utf-8",
        url="https://public-site.com/final",
        aclose=AsyncMock(),
    )
    async def fake_aiter_bytes():
        yield b"<html><body><p>Final content</p></body></html>"
    mock_final.aiter_bytes = fake_aiter_bytes

    with patch("httpx.AsyncClient.send", side_effect=[mock_hop1, mock_hop2, mock_final]):
        html, final_url, status = await fetch_website_content("http://public-site.com/start")
        assert "Final content" in html
        assert final_url == "https://public-site.com/final"
        assert status == 200


@pytest.mark.anyio
async def test_exceeded_redirect_limit():
    """Exceeding the maximum allowed redirects must raise SSRFSecurityError."""
    # Creates an infinite redirect loop
    mock_redirect = MagicMock(
        status_code=302,
        headers={"location": "https://public-site.com/loop"},
        aclose=AsyncMock(),
    )

    with patch("httpx.AsyncClient.send", return_value=mock_redirect):
        with pytest.raises(SSRFSecurityError) as exc_info:
            await fetch_website_content("https://public-site.com/loop", max_redirects=3)
        assert "too many redirects" in exc_info.value.message.lower()


@pytest.mark.anyio
async def test_unsupported_content_type():
    """MIME types like application/zip or image/png must be rejected."""
    mock_response = MagicMock(
        status_code=200,
        headers={"content-type": "application/zip"},
        aclose=AsyncMock(),
    )
    with patch("httpx.AsyncClient.send", return_value=mock_response):
        with pytest.raises(UnsupportedContentTypeError) as exc_info:
            await fetch_website_content("https://public-site.com/archive.zip")
        assert "unsupported content type" in exc_info.value.message.lower()


@pytest.mark.anyio
async def test_response_size_limit_enforcement_via_header():
    """Content-Length exceeding maximum allowed bytes (5 MB) must be rejected immediately."""
    mock_response = MagicMock(
        status_code=200,
        headers={
            "content-type": "text/html",
            "content-length": str(10 * 1024 * 1024),  # 10 MB
        },
        aclose=AsyncMock(),
    )
    with patch("httpx.AsyncClient.send", return_value=mock_response):
        with pytest.raises(ContentSizeExceededError) as exc_info:
            await fetch_website_content("https://public-site.com/large-doc")
        assert "exceeds limit" in exc_info.value.message.lower()


@pytest.mark.anyio
async def test_response_size_limit_enforcement_during_streaming():
    """Streaming responses that exceed limit must be aborted during download."""
    mock_response = MagicMock(
        status_code=200,
        headers={"content-type": "text/html"},
        aclose=AsyncMock(),
    )
    # Stream 6 chunks of 1 MB each (exceeds 5MB limit)
    async def large_stream():
        chunk = b"X" * (1024 * 1024)
        for _ in range(6):
            yield chunk

    mock_response.aiter_bytes = large_stream

    with patch("httpx.AsyncClient.send", return_value=mock_response):
        with pytest.raises(ContentSizeExceededError) as exc_info:
            await fetch_website_content("https://public-site.com/stream-large")
        assert "exceeded maximum allowed limit" in exc_info.value.message.lower()


@pytest.mark.anyio
async def test_http_error_handling():
    """Non-200 responses like 404 or 500 must raise ExtractionError."""
    mock_response = MagicMock(
        status_code=404,
        headers={"content-type": "text/html"},
        aclose=AsyncMock(),
    )
    with patch("httpx.AsyncClient.send", return_value=mock_response):
        with pytest.raises(ExtractionError) as exc_info:
            await fetch_website_content("https://public-site.com/missing-page")
        assert "404" in exc_info.value.message


# ---------------------------------------------------------------------------
# Extraction Engine Tests (Trafilatura & Jina Fallback)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_successful_trafilatura_extraction():
    """Trafilatura extracts title, text (>100 chars), and published date without network calls."""
    sample_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Breakthrough in Grid Energy Storage</title>
        <meta name="date" content="2026-04-12">
    </head>
    <body>
        <main>
            <h1>Breakthrough in Grid Energy Storage</h1>
            <p>
                Researchers have achieved a critical commercial milestone in sodium-ion battery durability,
                demonstrating over 4,000 cycles with minimal capacity fade at utility scale.
                The chemistry eliminates cobalt and nickel dependencies while preserving high thermal stability
                under fluctuating climatic loads across continental distribution networks.
            </p>
        </main>
    </body>
    </html>
    """

    with patch("app.services.extraction_service.fetch_website_content", return_value=(sample_html, "https://battery-news.org/sodium", 200)):
        result = await extract_website_content("https://battery-news.org/sodium")
        assert result.extraction_status == "success"
        assert result.extraction_method == "trafilatura"
        assert "sodium-ion battery" in result.extracted_content
        assert len(result.extracted_content) >= 100
        assert result.title == "Breakthrough in Grid Energy Storage"
        assert isinstance(result.published_at, datetime)
        assert result.published_at.year == 2026


@pytest.mark.anyio
async def test_trafilatura_returns_insufficient_content_triggers_jina_fallback():
    """When Trafilatura returns fewer than 100 characters, Jina Reader is called."""
    short_html = "<html><body><p>Short snippet</p></body></html>"
    jina_markdown = (
        "Title: Fallback Comprehensive Report\n\n"
        "This is comprehensive text returned by Jina Reader fallback service when "
        "the primary DOM extractor cannot find an article block. It contains well over "
        "one hundred characters of readable context for information gap analysis."
    )

    with patch("app.services.extraction_service.fetch_website_content", return_value=(short_html, "https://sparse-site.com", 200)):
        with patch.object(WebsiteExtractor, "_extract_with_jina", return_value=(jina_markdown, "Fallback Comprehensive Report")):
            result = await extract_website_content("https://sparse-site.com")
            assert result.extraction_status == "success"
            assert result.extraction_method == "jina"
            assert "Jina Reader fallback service" in result.extracted_content
            assert len(result.extracted_content) >= 100
            assert result.title == "Fallback Comprehensive Report"


@pytest.mark.anyio
async def test_trafilatura_returns_none_triggers_jina_fallback():
    """When Trafilatura returns None, Jina Reader is called."""
    empty_html = "<html><body><div></div></body></html>"
    jina_markdown = "Title: Jina Extracted Document\n\n" + ("Valid content paragraph. " * 10)

    with patch("app.services.extraction_service.fetch_website_content", return_value=(empty_html, "https://empty-dom.com", 200)):
        with patch.object(WebsiteExtractor, "_extract_with_jina", return_value=(jina_markdown, "Jina Extracted Document")):
            result = await extract_website_content("https://empty-dom.com")
            assert result.extraction_status == "success"
            assert result.extraction_method == "jina"
            assert "Valid content paragraph" in result.extracted_content


@pytest.mark.anyio
async def test_jina_fallback_failure_preserves_partial_content():
    """If Jina fallback fails but Trafilatura extracted some text (<100 chars), return partial status."""
    partial_html = "<html><body><p>Brief company announcement statement.</p></body></html>"

    with patch("app.services.extraction_service.fetch_website_content", return_value=(partial_html, "https://brief-announcement.org", 200)):
        with patch.object(WebsiteExtractor, "_extract_with_jina", return_value=(None, None)):
            result = await extract_website_content("https://brief-announcement.org")
            assert result.extraction_status == "partial"
            assert result.extraction_method == "trafilatura"
            assert "Brief company announcement statement." in result.extracted_content


@pytest.mark.anyio
async def test_total_extraction_failure_raises_error():
    """If both Trafilatura and Jina extract nothing, raise ExtractionError."""
    blank_html = "<html><head></head><body></body></html>"

    with patch("app.services.extraction_service.fetch_website_content", return_value=(blank_html, "https://blank-page.com", 200)):
        with patch.object(WebsiteExtractor, "_extract_with_jina", return_value=(None, None)):
            with pytest.raises(ExtractionError) as exc_info:
                await extract_website_content("https://blank-page.com")
            assert "unable to extract meaningful readable content" in exc_info.value.message.lower()
            assert exc_info.value.status_code == 422


@pytest.mark.anyio
async def test_malformed_html_handling():
    """Malformed or non-standard HTML should be processed without unhandled crashes."""
    malformed_html = "<html<<>><body><p>Content inside broken markup tags that should still be salvaged if possible.</p>" * 3

    with patch("app.services.extraction_service.fetch_website_content", return_value=(malformed_html, "https://broken-html.com", 200)):
        result = await extract_website_content("https://broken-html.com")
        assert result.extraction_status in ("success", "partial")
        assert result.extracted_content != ""


# ---------------------------------------------------------------------------
# FIX 1: API Information Disclosure Remediation Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_api_ssrf_error_private_ipv4_generic_response():
    """API responses for private IPv4 rejection must return generic messages and not leak the IP."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.core.exceptions import register_exception_handlers

    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/test-private-ip")
    async def trigger_private():
        validate_url_syntax("http://192.168.1.100/admin")

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test-private-ip")
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert data["message"] == "The requested URL cannot be accessed for security reasons."
        assert data["detail"] == "Prohibited destination address or protocol."
        assert "192.168.1.100" not in response.text


@pytest.mark.anyio
async def test_api_ssrf_error_loopback_generic_response():
    """API responses for loopback rejection must return generic messages and not leak the IP."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.core.exceptions import register_exception_handlers

    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/test-loopback")
    async def trigger_loopback():
        validate_url_syntax("http://127.0.0.1:8080/metrics")

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test-loopback")
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert data["message"] == "The requested URL cannot be accessed for security reasons."
        assert "127.0.0.1" not in response.text


# ---------------------------------------------------------------------------
# Additional Compression Security Regression Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gzip_decompressed_size_exceeding_limit_aborts():
    """Gzip-compressed response whose decompressed size exceeds 5 MB must be aborted."""
    mock_response = MagicMock(
        status_code=200,
        headers={"content-type": "text/html", "content-encoding": "gzip"},
        aclose=AsyncMock(),
    )
    # Stream chunks of decompressed data totaling > 5 MB
    async def large_decompressed_stream():
        chunk = b"A" * (1024 * 1024)
        for _ in range(6):
            yield chunk

    mock_response.aiter_bytes = large_decompressed_stream

    with patch("httpx.AsyncClient.send", return_value=mock_response):
        with pytest.raises(ContentSizeExceededError) as exc_info:
            await fetch_website_content("https://public-site.com/gzip-bomb")
        assert "exceeded maximum allowed limit" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# FIX 2: Jina Reader Streaming, Size Limit, & Stream Cleanup Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_jina_streamed_response_success():
    """Jina Reader streaming extraction returns content and title successfully."""
    extractor = WebsiteExtractor()
    mock_response = MagicMock(status_code=200, headers={"content-type": "text/markdown"}, aclose=AsyncMock())

    async def fake_stream():
        yield b"Title: Streamed Jina Article\n\n"
        yield b"This is a high quality article body fetched via streaming from Jina Reader. " * 3

    mock_response.aiter_bytes = fake_stream

    with patch("httpx.AsyncClient.send", return_value=mock_response):
        content, title = await extractor._extract_with_jina("https://example.com/stream-jina")
        assert title == "Streamed Jina Article"
        assert "high quality article body fetched via streaming" in content
        mock_response.aclose.assert_awaited()


@pytest.mark.anyio
async def test_jina_response_exceeding_size_limit_aborts():
    """Jina responses exceeding maximum content size must abort download and return None."""
    extractor = WebsiteExtractor()
    mock_response = MagicMock(status_code=200, headers={"content-type": "text/markdown"}, aclose=AsyncMock())

    async def oversized_stream():
        chunk = b"X" * (1024 * 1024)
        for _ in range(6):  # 6 MB > 5 MB limit
            yield chunk

    mock_response.aiter_bytes = oversized_stream

    with patch("httpx.AsyncClient.send", return_value=mock_response):
        content, title = await extractor._extract_with_jina("https://example.com/oversized-jina")
        assert content is None
        assert title is None
        mock_response.aclose.assert_awaited()


@pytest.mark.anyio
async def test_jina_timeout_handling():
    """Jina timeouts must be safely caught, logged, and return None without exposing errors."""
    extractor = WebsiteExtractor()
    with patch("httpx.AsyncClient.send", side_effect=httpx.TimeoutException("Jina connection timed out")):
        content, title = await extractor._extract_with_jina("https://example.com/timeout-jina")
        assert content is None
        assert title is None


@pytest.mark.anyio
async def test_jina_non_200_response():
    """Non-200 responses from Jina Reader must safely close response and return None."""
    extractor = WebsiteExtractor()
    mock_response = MagicMock(status_code=429, headers={}, aclose=AsyncMock())

    with patch("httpx.AsyncClient.send", return_value=mock_response):
        content, title = await extractor._extract_with_jina("https://example.com/rate-limited")
        assert content is None
        assert title is None
        mock_response.aclose.assert_awaited()


@pytest.mark.anyio
async def test_jina_missing_or_empty_content():
    """Empty or whitespace-only response from Jina Reader must return None."""
    extractor = WebsiteExtractor()
    mock_response = MagicMock(status_code=200, headers={}, aclose=AsyncMock())

    async def empty_stream():
        yield b"   \n\t  "

    mock_response.aiter_bytes = empty_stream

    with patch("httpx.AsyncClient.send", return_value=mock_response):
        content, title = await extractor._extract_with_jina("https://example.com/empty-jina")
        assert content is None
        assert title is None
        mock_response.aclose.assert_awaited()


@pytest.mark.anyio
async def test_jina_stream_cleanup_on_exception():
    """If an exception occurs mid-stream, the response stream must be reliably closed."""
    extractor = WebsiteExtractor()
    mock_response = MagicMock(status_code=200, headers={}, aclose=AsyncMock())

    async def broken_stream():
        yield b"First partial chunk"
        raise httpx.RequestError("Network connection reset mid-download")

    mock_response.aiter_bytes = broken_stream

    with patch("httpx.AsyncClient.send", return_value=mock_response):
        content, title = await extractor._extract_with_jina("https://example.com/broken-stream")
        assert content is None
        assert title is None
        mock_response.aclose.assert_awaited()


@pytest.mark.anyio
async def test_jina_rejects_invalid_target_url_before_request():
    """Defense in depth: Invalid target URL must be rejected before any Jina request is dispatched."""
    extractor = WebsiteExtractor()
    with patch("httpx.AsyncClient.send") as mock_send:
        content, title = await extractor._extract_with_jina("http://192.168.1.1/secret-intranet")
        assert content is None
        assert title is None
        mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# FIX 3: Custom SSRF-Protected Transport & Socket Pinning Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ssrf_network_backend_connects_to_pinned_ipv4():
    """SSRFProtectedNetworkBackend.connect_tcp must pass the pinned IPv4 address to super().connect_tcp."""
    from app.services.ssrf_service import SSRFProtectedNetworkBackend

    backend = SSRFProtectedNetworkBackend()
    mock_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ]

    with patch("socket.getaddrinfo", return_value=mock_addrinfo):
        with patch("httpcore._backends.anyio.AnyIOBackend.connect_tcp", new_callable=AsyncMock) as mock_super_connect:
            mock_super_connect.return_value = MagicMock()
            await backend.connect_tcp(host="example.com", port=443, timeout=5.0)

            mock_super_connect.assert_called_once()
            call_kwargs = mock_super_connect.call_args.kwargs
            # Verify the destination IP is pinned to the validated IP, not the domain name
            assert call_kwargs["host"] == "93.184.216.34"
            assert call_kwargs["port"] == 443
            assert call_kwargs["timeout"] == 5.0


@pytest.mark.anyio
async def test_ssrf_network_backend_connects_to_pinned_ipv6():
    """SSRFProtectedNetworkBackend.connect_tcp must pass the pinned IPv6 address to super().connect_tcp."""
    from app.services.ssrf_service import SSRFProtectedNetworkBackend

    backend = SSRFProtectedNetworkBackend()
    mock_addrinfo = [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 443)),
    ]

    with patch("socket.getaddrinfo", return_value=mock_addrinfo):
        with patch("httpcore._backends.anyio.AnyIOBackend.connect_tcp", new_callable=AsyncMock) as mock_super_connect:
            mock_super_connect.return_value = MagicMock()
            await backend.connect_tcp(host="ipv6.example.com", port=443)

            mock_super_connect.assert_called_once()
            call_kwargs = mock_super_connect.call_args.kwargs
            assert call_kwargs["host"] == "2606:2800:220:1:248:1893:25c8:1946"
            assert call_kwargs["port"] == 443


@pytest.mark.anyio
async def test_ssrf_network_backend_rejects_unsafe_dns_before_connection():
    """SSRFProtectedNetworkBackend.connect_tcp must reject private IP before attempting any socket connection."""
    from app.services.ssrf_service import SSRFProtectedNetworkBackend

    backend = SSRFProtectedNetworkBackend()
    mock_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80)),
    ]

    with patch("socket.getaddrinfo", return_value=mock_addrinfo):
        with patch("httpcore._backends.anyio.AnyIOBackend.connect_tcp", new_callable=AsyncMock) as mock_super_connect:
            with pytest.raises(SSRFSecurityError) as exc_info:
                await backend.connect_tcp(host="malicious-rebind.com", port=80)

            assert "loopback" in exc_info.value.message.lower()
            # Crucial: underlying connection must NEVER have been called
            mock_super_connect.assert_not_called()


@pytest.mark.anyio
async def test_tls_hostname_preservation_with_pinned_socket():
    """Tests HTTPCore AsyncHTTPConnection._connect to verify TCP is pinned to IP while TLS SNI retains domain name.

    Note: This tests HTTPCore >= 1.0.0 internal contract where:
    1. _network_backend.connect_tcp is called with host (intercepted and pinned to IP by SSRFProtectedNetworkBackend).
    2. stream.start_tls is called with server_hostname=sni_hostname or origin.host.decode('ascii').
    """
    import httpcore
    from app.services.ssrf_service import SSRFProtectedNetworkBackend

    backend = SSRFProtectedNetworkBackend()
    origin = httpcore.Origin(b"https", b"secure-domain.org", 443)
    connection = httpcore.AsyncHTTPConnection(origin=origin, network_backend=backend)

    mock_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ]

    mock_stream = MagicMock()
    mock_stream.start_tls = AsyncMock(return_value=mock_stream)

    with patch("socket.getaddrinfo", return_value=mock_addrinfo):
        with patch("httpcore._backends.anyio.AnyIOBackend.connect_tcp", new_callable=AsyncMock) as mock_super_connect:
            mock_super_connect.return_value = mock_stream
            request = httpcore.Request("GET", "https://secure-domain.org/path")

            stream = await connection._connect(request)

            # 1. Verify TCP socket connection received the pinned IP address
            mock_super_connect.assert_called_once()
            assert mock_super_connect.call_args.kwargs["host"] == "93.184.216.34"

            # 2. Verify TLS SNI extension received the original domain name, NOT the IP
            mock_stream.start_tls.assert_called_once()
            start_tls_kwargs = mock_stream.start_tls.call_args.kwargs
            assert start_tls_kwargs["server_hostname"] == "secure-domain.org"
            assert stream is mock_stream

