"""SSRF Security Service for ClarityX.

Provides comprehensive Server-Side Request Forgery (SSRF) validation and safe HTTP transport:
- Restricts schemes strictly to HTTP and HTTPS.
- Rejects URLs containing credentials.
- Rejects localhost, local, internal, and reserved hostnames.
- Pre-resolves DNS and validates every resolved IPv4 and IPv6 address against private,
  loopback, link-local, multicast, cloud metadata, and reserved ranges.
- Enforces transport-level socket binding directly to the validated IP address, eliminating
  DNS rebinding attacks while preserving original Host headers and TLS SNI validation.
- Validates every HTTP redirect hop individually against SSRF rules with a strict redirect cap.
"""

import ipaddress
import logging
import socket
from typing import Optional, Set, Tuple
from urllib.parse import urljoin, urlsplit

import httpcore
from httpcore._backends.anyio import AnyIOBackend
import httpx

from app.core.config import get_settings
from app.core.exceptions import (
    ContentSizeExceededError,
    ExtractionError,
    IsPdfUrlError,
    SSRFSecurityError,
    UnsupportedContentTypeError,
)

logger = logging.getLogger("clarityx.security.ssrf")

# Disallowed local and internal hostname suffixes / exact names
DISALLOWED_HOSTNAMES: Set[str] = {
    "localhost",
    "localhost.localdomain",
    "broadcasthost",
    "local",
    "internal",
    "lan",
    "home",
    "corp",
    "test",
    "invalid",
    "onion",
}

DISALLOWED_DOMAINS_SUFFIXES: Tuple[str, ...] = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home",
    ".corp",
    ".test",
    ".invalid",
    ".onion",
)

# Explicitly blocked cloud instance metadata IP addresses
BLOCKED_METADATA_IPS: Set[str] = {
    "169.254.169.254",  # AWS, GCP, Azure, OpenStack IPv4 metadata
    "169.254.169.253",  # AWS IPv4 DNS metadata
    "100.100.100.200",  # Alibaba Cloud metadata
    "fd00:ec2::254",    # AWS IPv6 metadata
}

# Permitted MIME types for website text extraction
ALLOWED_CONTENT_TYPES: Set[str] = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "application/xml",
    "text/xml",
    "application/pdf",
    "application/x-pdf",
}

# RFC 6052 Well-Known Prefix for IPv4/IPv6 translation
NAT64_WELL_KNOWN_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")


def validate_ip_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """Validates that an IP address is a public, routable destination.

    Blocks loopback, private, link-local, multicast, reserved, unspecified,
    and cloud instance metadata IPs.
    Unpacks IPv4-mapped IPv6 (::ffff:0:0/96) and RFC 6052 NAT64 prefixes (64:ff9b::/96)
    so embedded public IPv4 addresses are verified and permitted, while embedded
    private or loopback IPs fail closed.

    Raises:
        SSRFSecurityError: If IP address is in a prohibited range.
    """
    # Unpack IPv4-mapped IPv6 addresses (e.g., ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        elif ip in NAT64_WELL_KNOWN_PREFIX:
            # Unpack RFC 6052 embedded IPv4 address (last 32 bits)
            ip = ipaddress.IPv4Address(ip.packed[-4:])

    ip_str = str(ip)

    # Explicit cloud metadata check
    if ip_str in BLOCKED_METADATA_IPS:
        logger.warning(f"SSRF violation: blocked access to cloud metadata IP address {ip_str}")
        raise SSRFSecurityError(
            "Access to cloud metadata address is prohibited."
        )

    if ip.is_loopback:
        logger.warning(f"SSRF violation: blocked access to loopback IP address {ip_str}")
        raise SSRFSecurityError(
            "Access to loopback address is prohibited."
        )

    if ip.is_private:
        logger.warning(f"SSRF violation: blocked access to private network IP address {ip_str}")
        raise SSRFSecurityError(
            "Access to private network address is prohibited."
        )

    if ip.is_link_local:
        logger.warning(f"SSRF violation: blocked access to link-local IP address {ip_str}")
        raise SSRFSecurityError(
            "Access to link-local address is prohibited."
        )

    if ip.is_multicast:
        logger.warning(f"SSRF violation: blocked access to multicast IP address {ip_str}")
        raise SSRFSecurityError(
            "Access to multicast address is prohibited."
        )

    if ip.is_reserved:
        logger.warning(f"SSRF violation: blocked access to reserved IP address {ip_str}")
        raise SSRFSecurityError(
            "Access to reserved address is prohibited."
        )

    if ip.is_unspecified:
        logger.warning(f"SSRF violation: blocked access to unspecified IP address {ip_str}")
        raise SSRFSecurityError(
            "Access to unspecified address is prohibited."
        )


def validate_url_syntax(url: str) -> Tuple[str, str, int]:
    """Validates basic URL syntax, scheme, credentials, and hostname.

    Returns:
        Tuple of (normalized_scheme, hostname, port)

    Raises:
        SSRFSecurityError: If URL fails syntax or security validation.
    """
    if not url or not isinstance(url, str):
        raise SSRFSecurityError("URL must be a non-empty string.")

    trimmed_url = url.strip()
    if len(trimmed_url) > 2048:
        raise SSRFSecurityError("URL exceeds maximum length of 2048 characters.")

    try:
        parsed = urlsplit(trimmed_url)
    except Exception as exc:
        raise SSRFSecurityError(f"Malformed URL format: {type(exc).__name__}") from exc

    # 1. Scheme validation (strictly http and https)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise SSRFSecurityError(
            f"Unsupported scheme '{scheme}'. Only HTTP and HTTPS protocols are permitted."
        )

    # 2. Reject credentials in URL (e.g. http://user:pass@example.com)
    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        raise SSRFSecurityError("URLs containing user credentials are prohibited.")

    # 3. Hostname validation
    hostname = parsed.hostname
    if not hostname:
        raise SSRFSecurityError("URL must contain a valid hostname.")

    hostname_lower = hostname.lower().strip(".")

    # Reject empty or root hostname
    if not hostname_lower:
        raise SSRFSecurityError("URL must contain a non-empty hostname.")

    # Reject local/internal hostnames
    if hostname_lower in DISALLOWED_HOSTNAMES:
        logger.warning(f"SSRF violation: blocked access to local hostname {hostname_lower}")
        raise SSRFSecurityError("Access to local hostname is prohibited.")

    for suffix in DISALLOWED_DOMAINS_SUFFIXES:
        if hostname_lower.endswith(suffix):
            logger.warning(f"SSRF violation: blocked access to internal domain {hostname_lower}")
            raise SSRFSecurityError("Access to internal domain is prohibited.")

    # 4. If hostname is an IP literal, validate against prohibited ranges immediately
    clean_host = hostname_lower.strip("[]")
    try:
        ip_obj = ipaddress.ip_address(clean_host)
        validate_ip_address(ip_obj)
    except ValueError:
        pass  # It is a domain name, will be validated during DNS resolution

    # 5. Port validation
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80
    elif not (1 <= port <= 65535):
        raise SSRFSecurityError(f"Invalid port number: {port}")

    return scheme, hostname_lower, port


def resolve_and_validate_destination(hostname: str, port: int) -> str:
    """Resolves DNS for a hostname and validates every resolved IP address.

    Returns the validated IP string to be used for the direct outbound TCP connection,
    defeating DNS rebinding attacks.

    Raises:
        SSRFSecurityError: If resolution fails or any resolved IP is non-public.
    """
    clean_host = hostname.strip("[]")

    # If already an IP literal, validate immediately
    try:
        direct_ip = ipaddress.ip_address(clean_host)
        validate_ip_address(direct_ip)
        return str(direct_ip)
    except ValueError:
        pass  # It's a domain name, proceed to DNS resolution

    # Resolve domain via getaddrinfo
    try:
        addrinfo = socket.getaddrinfo(
            clean_host, port, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        logger.warning(f"DNS resolution failure for {clean_host}: {exc}")
        raise SSRFSecurityError(
            "DNS resolution failed for the requested hostname."
        ) from exc
    except Exception as exc:
        logger.warning(f"Unexpected error resolving hostname {clean_host}: {type(exc).__name__}")
        raise SSRFSecurityError(
            "DNS resolution failed for the requested hostname."
        ) from exc

    if not addrinfo:
        logger.warning(f"No IP addresses found for hostname {clean_host}")
        raise SSRFSecurityError("No IP addresses found for the requested hostname.")

    # Validate EVERY resolved IP address associated with the host.
    # If any resolved IP is private/loopback/metadata, fail closed immediately.
    validated_ips = []
    for entry in addrinfo:
        ip_str = entry[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            validate_ip_address(ip_obj)
            validated_ips.append(ip_str)
        except SSRFSecurityError:
            logger.warning(f"SSRF violation resolved for {clean_host} ({ip_str})")
            raise

    # Return the first validated IP for socket binding
    return validated_ips[0]


class SSRFProtectedNetworkBackend(AnyIOBackend):
    """Custom HTTPCore network backend that binds outbound TCP connections directly
    to the validated IP address, eliminating DNS rebinding while preserving SNI.
    """

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options=None,
    ):
        # Resolve and validate host to obtain the verified IP address
        validated_ip = resolve_and_validate_destination(host, port)

        # Directly connect the TCP socket to the validated IP.
        # HTTPCore's caller preserves the original hostname for SNI and Host headers.
        return await super().connect_tcp(
            host=validated_ip,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class SSRFProtectedTransport(httpx.AsyncHTTPTransport):
    """HTTPX Async Transport enforcing SSRF protection and DNS-rebinding immunity."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Override the connection pool with our SSRFProtectedNetworkBackend
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=self._pool._ssl_context,
            network_backend=SSRFProtectedNetworkBackend(),
            retries=0,
            http1=True,
            http2=False,
        )


def build_request_headers(target_url: str, is_pdf: bool = False) -> dict:
    """Builds appropriate, security-conscious HTTP request headers for web requests."""
    settings = get_settings()
    parsed = urlsplit(target_url)
    hostname = (parsed.hostname or "").lower()

    if hostname.endswith("sec.gov"):
        # SEC EDGAR automated compliance requirement: declared identity with contact email
        user_agent = getattr(
            settings,
            "SEC_USER_AGENT",
            f"ClarityXResearch/0.1.0 ({getattr(settings, 'SEC_CONTACT_EMAIL', 'research@clarityx.ai')})",
        )
    else:
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36 (compatible; ClarityX/0.1.0; +https://github.com/ClarityX; contact@clarityx.dev)"
        )

    accept = (
        "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8"
        if is_pdf
        else "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,application/pdf;q=0.7,*/*;q=0.5"
    )

    return {
        "User-Agent": user_agent,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
    }


async def fetch_website_content(
    target_url: str,
    max_content_length: Optional[int] = None,
    timeout_seconds: Optional[float] = None,
    max_redirects: Optional[int] = None,
) -> Tuple[str, str, int]:
    """Securely fetches web content using SSRF-protected HTTPX transport.

    Enforces:
    - Initial and redirect URL validation.
    - Manual redirect processing (up to max_redirects).
    - Response body streaming with strict byte limit (max_content_length).
    - Supported content-type verification.

    Returns:
        Tuple of (decoded_html_string, final_url, status_code)

    Raises:
        SSRFSecurityError: If any target or redirect URL violates SSRF rules.
        ContentSizeExceededError: If response body exceeds content limit.
        UnsupportedContentTypeError: If target MIME type is not HTML/text.
        IsPdfUrlError: If target URL serves a PDF document stream.
        ExtractionError: If network connection or HTTP request fails.
    """
    settings = get_settings()
    max_bytes = max_content_length or settings.MAX_WEBSITE_CONTENT_LENGTH
    timeout = timeout_seconds or settings.WEBSITE_EXTRACTION_TIMEOUT
    max_hops = max_redirects if max_redirects is not None else settings.MAX_REDIRECTS

    current_url = target_url
    redirect_count = 0

    transport = SSRFProtectedTransport()
    client_timeout = httpx.Timeout(timeout, connect=timeout)

    headers = build_request_headers(target_url, is_pdf=False)

    async with httpx.AsyncClient(
        transport=transport,
        timeout=client_timeout,
        follow_redirects=False,
        headers=headers,
    ) as client:
        while True:
            # 1. Validate the current URL syntax and safety
            validate_url_syntax(current_url)

            try:
                request = client.build_request("GET", current_url)
                response = await client.send(request, stream=True)
            except (SSRFSecurityError, ContentSizeExceededError, UnsupportedContentTypeError):
                raise
            except httpx.TimeoutException as exc:
                raise ExtractionError(
                    message=f"Request to website timed out after {timeout} seconds.",
                    status_code=504,
                ) from exc
            except httpx.RequestError as exc:
                logger.warning(f"HTTP request error fetching {current_url}: {type(exc).__name__}")
                raise ExtractionError(
                    message="Unable to establish a secure connection to the requested website.",
                    status_code=502,
                ) from exc

            # 2. Handle HTTP Redirects manually
            if response.status_code in (301, 302, 303, 307, 308):
                redirect_count += 1
                await response.aclose()

                if redirect_count > max_hops:
                    raise SSRFSecurityError(
                        f"Too many redirects: exceeded maximum allowable limit of {max_hops}."
                    )

                location = response.headers.get("location")
                if not location:
                    raise ExtractionError(
                        message="Redirect response received without a Location header.",
                        status_code=502,
                    )

                # Resolve relative redirects
                next_url = urljoin(current_url, location)
                logger.info(f"Following secure redirect #{redirect_count}: {current_url} -> {next_url}")
                current_url = next_url
                continue

            # 3. Handle non-2xx responses
            if response.status_code != 200:
                status = response.status_code
                await response.aclose()
                raise ExtractionError(
                    message=f"Website returned unsuccessful status code: {status}",
                    status_code=status if status in (403, 404, 410, 500, 502, 503) else 502,
                )

            # 4. Validate Content-Type
            content_type_header = response.headers.get("content-type", "").lower()
            mime_type = content_type_header.split(";")[0].strip()

            # Detect PDF response stream and signal dedicated PDF document processing
            if mime_type in ("application/pdf", "application/x-pdf"):
                await response.aclose()
                raise IsPdfUrlError(final_url=str(response.url))

            if mime_type and mime_type not in ALLOWED_CONTENT_TYPES:
                await response.aclose()
                raise UnsupportedContentTypeError(
                    message=f"Unsupported content type '{mime_type}'. Only HTML and text documents can be processed."
                )

            # 5. Check Content-Length header upfront if provided
            content_length_header = response.headers.get("content-length")
            if content_length_header:
                try:
                    declared_length = int(content_length_header)
                    if declared_length > max_bytes:
                        await response.aclose()
                        raise ContentSizeExceededError(
                            message=f"Website content size ({declared_length} bytes) exceeds limit of {max_bytes} bytes."
                        )
                except ValueError:
                    pass

            # 6. Stream response body safely with byte limit guard
            body_chunks = []
            total_bytes = 0

            try:
                async for chunk in response.aiter_bytes():
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        await response.aclose()
                        raise ContentSizeExceededError(
                            message=f"Website content exceeded maximum allowed limit of {max_bytes} bytes while downloading."
                        )
                    body_chunks.append(chunk)
            finally:
                await response.aclose()

            raw_bytes = b"".join(body_chunks)

            # 7. Decode HTML using declared or fallback encoding
            encoding = response.encoding or "utf-8"
            try:
                decoded_text = raw_bytes.decode(encoding, errors="replace")
            except (LookupError, UnicodeDecodeError):
                decoded_text = raw_bytes.decode("utf-8", errors="replace")

            return decoded_text, str(response.url), response.status_code


async def fetch_pdf_document(
    target_url: str,
    max_file_size: Optional[int] = None,
    timeout_seconds: Optional[float] = None,
    max_redirects: Optional[int] = None,
) -> Tuple[bytes, str]:
    """Securely downloads a PDF document stream using SSRF-protected HTTPX transport.

    Enforces:
    - Initial and redirect URL validation.
    - SSRF destination checks on every redirect hop.
    - PDF size limit (defaults to MAX_DOCUMENT_FILE_SIZE = 10 MB).
    - PDF magic-byte validation (b"%PDF-").

    Returns:
        Tuple of (pdf_bytes, final_url)

    Raises:
        SSRFSecurityError: If any target or redirect URL violates SSRF rules.
        ContentSizeExceededError: If PDF exceeds max_file_size limit.
        ExtractionError: If download fails or content is not a valid PDF.
    """
    settings = get_settings()
    max_bytes = max_file_size or settings.MAX_DOCUMENT_FILE_SIZE
    timeout = timeout_seconds or settings.WEBSITE_EXTRACTION_TIMEOUT
    max_hops = max_redirects if max_redirects is not None else settings.MAX_REDIRECTS

    current_url = target_url
    redirect_count = 0

    transport = SSRFProtectedTransport()
    client_timeout = httpx.Timeout(timeout, connect=timeout)

    headers = build_request_headers(target_url, is_pdf=True)

    async with httpx.AsyncClient(
        transport=transport,
        timeout=client_timeout,
        follow_redirects=False,
        headers=headers,
    ) as client:
        while True:
            validate_url_syntax(current_url)

            try:
                request = client.build_request("GET", current_url)
                response = await client.send(request, stream=True)
            except (SSRFSecurityError, ContentSizeExceededError):
                raise
            except httpx.TimeoutException as exc:
                raise ExtractionError(
                    message=f"Request to download PDF timed out after {timeout} seconds.",
                    status_code=504,
                ) from exc
            except httpx.RequestError as exc:
                logger.warning(f"HTTP error fetching PDF from {current_url}: {type(exc).__name__}")
                raise ExtractionError(
                    message="Unable to establish a secure connection to download the requested PDF.",
                    status_code=502,
                ) from exc

            # Handle redirects
            if response.status_code in (301, 302, 303, 307, 308):
                redirect_count += 1
                await response.aclose()

                if redirect_count > max_hops:
                    raise SSRFSecurityError(
                        f"Too many redirects: exceeded maximum allowable limit of {max_hops}."
                    )

                location = response.headers.get("location")
                if not location:
                    raise ExtractionError(
                        message="Redirect response received without a Location header.",
                        status_code=502,
                    )

                next_url = urljoin(current_url, location)
                current_url = next_url
                continue

            if response.status_code != 200:
                status = response.status_code
                await response.aclose()
                raise ExtractionError(
                    message=f"PDF download returned unsuccessful status code: {status}",
                    status_code=status if status in (403, 404, 410, 500, 502, 503) else 502,
                )

            # Check declared content-length
            content_length_header = response.headers.get("content-length")
            if content_length_header:
                try:
                    declared_len = int(content_length_header)
                    if declared_len > max_bytes:
                        await response.aclose()
                        raise ContentSizeExceededError(
                            message=f"PDF size ({declared_len} bytes) exceeds limit of {max_bytes} bytes."
                        )
                except ValueError:
                    pass

            # Stream body with byte limit guard
            body_chunks = []
            total_bytes = 0
            try:
                async for chunk in response.aiter_bytes():
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        await response.aclose()
                        raise ContentSizeExceededError(
                            message=f"PDF exceeded maximum allowed limit of {max_bytes} bytes while downloading."
                        )
                    body_chunks.append(chunk)
            finally:
                await response.aclose()

            pdf_bytes = b"".join(body_chunks)

            # Verify magic bytes
            if not pdf_bytes.startswith(b"%PDF-"):
                raise ExtractionError(
                    message="Downloaded file is not a valid PDF document (missing %PDF- header).",
                    status_code=422,
                )

            return pdf_bytes, str(response.url)
