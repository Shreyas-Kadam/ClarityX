"""Website Content Extraction Service for ClarityX.

Orchestrates multi-engine content extraction:
1. Primary Extractor: Trafilatura (extracts clean text, title, and metadata without internal network calls).
2. Fallback Extractor: Jina Reader API (invoked when Trafilatura fails or yields fewer than 100 characters).
3. Security: All network operations enforce strict SSRF validation, size limits, and timeouts.
"""

from datetime import datetime
import logging
import re
from typing import Optional, Tuple
from urllib.parse import quote, urlsplit

import dateutil.parser
import httpx
import trafilatura

from app.core.config import get_settings
from app.core.exceptions import (
    ExtractionError,
    SSRFSecurityError,
)
from app.schemas.source import WebsiteExtractionResult
from app.services.ssrf_service import (
    SSRFProtectedTransport,
    fetch_website_content,
    validate_url_syntax,
)

logger = logging.getLogger("clarityx.extraction")

# Minimum characters considered useful for primary extraction before fallback
MIN_USEFUL_CONTENT_LENGTH = 100


class WebsiteExtractor:
    """Service that coordinates secure web retrieval, Trafilatura parsing, and Jina fallback."""

    def __init__(self):
        self.settings = get_settings()

    async def extract(self, url: str) -> WebsiteExtractionResult:
        """Extracts article content from a website URL.

        Enforces SSRF validation, applies Trafilatura extraction, and falls back
        to Jina Reader if extracted text is insufficient (< 100 chars).

        Returns:
            WebsiteExtractionResult

        Raises:
            SSRFSecurityError: If URL violates security constraints.
            ContentSizeExceededError: If response body exceeds limits.
            UnsupportedContentTypeError: If MIME type is unsupported.
            ExtractionError: If extraction fails completely across all engines.
        """
        # 1. Validate initial URL syntax and security
        validate_url_syntax(url)

        # 2. Securely fetch the target website HTML
        html_content, final_url, _ = await fetch_website_content(url)

        # 3. Attempt primary extraction using Trafilatura
        trafilatura_text, trafilatura_title, published_at = self._extract_with_trafilatura(
            html_content=html_content, target_url=final_url
        )

        # If Trafilatura returned sufficient content, return success
        if trafilatura_text and len(trafilatura_text.strip()) >= MIN_USEFUL_CONTENT_LENGTH:
            logger.info(
                f"Trafilatura successfully extracted {len(trafilatura_text)} characters from {final_url}"
            )
            return WebsiteExtractionResult(
                url=final_url,
                title=trafilatura_title,
                extracted_content=trafilatura_text.strip(),
                published_at=published_at,
                extraction_method="trafilatura",
                extraction_status="success",
            )

        logger.info(
            f"Trafilatura yielded insufficient content ({len(trafilatura_text) if trafilatura_text else 0} chars) "
            f"for {final_url}. Attempting Jina Reader fallback."
        )

        # 4. Attempt fallback extraction using Jina Reader
        jina_text, jina_title = await self._extract_with_jina(final_url)

        if jina_text and len(jina_text.strip()) >= MIN_USEFUL_CONTENT_LENGTH:
            logger.info(
                f"Jina Reader fallback successfully extracted {len(jina_text)} characters for {final_url}"
            )
            return WebsiteExtractionResult(
                url=final_url,
                title=jina_title or trafilatura_title,
                extracted_content=jina_text.strip(),
                published_at=published_at,  # Preserve date from metadata if found earlier
                extraction_method="jina",
                extraction_status="success",
            )

        # 5. Handle partial extraction or total failure
        best_content = ""
        best_method: str = "trafilatura"

        if trafilatura_text and len(trafilatura_text.strip()) > 0:
            best_content = trafilatura_text.strip()
            best_method = "trafilatura"
        elif jina_text and len(jina_text.strip()) > 0:
            best_content = jina_text.strip()
            best_method = "jina"

        if best_content:
            logger.warning(
                f"Extraction yielded only partial content ({len(best_content)} chars) for {final_url}"
            )
            return WebsiteExtractionResult(
                url=final_url,
                title=trafilatura_title or jina_title,
                extracted_content=best_content,
                published_at=published_at,
                extraction_method=best_method,  # type: ignore[arg-type]
                extraction_status="partial",
            )

        # Both engines failed completely
        logger.error(f"Complete extraction failure across Trafilatura and Jina for {final_url}")
        raise ExtractionError(
            message="Unable to extract meaningful readable content from the requested website.",
            detail="Both primary (Trafilatura) and fallback (Jina Reader) extractors failed to find article content.",
            status_code=422,
        )

    def _extract_with_trafilatura(
        self, html_content: str, target_url: str
    ) -> Tuple[Optional[str], Optional[str], Optional[datetime]]:
        """Parses raw HTML using Trafilatura without performing any network calls.

        Returns:
            Tuple of (extracted_text, title, published_date)
        """
        if not html_content or not isinstance(html_content, str):
            return None, None, None

        # Extract main text
        try:
            extracted_text = trafilatura.extract(
                html_content,
                url=target_url,
                include_comments=False,
                include_tables=True,
                include_links=False,
                no_fallback=False,
                output_format="txt",
            )
        except Exception as exc:
            logger.warning(f"Trafilatura extract parsing exception: {type(exc).__name__}")
            extracted_text = None

        # Extract metadata (title, publication date)
        title: Optional[str] = None
        published_at: Optional[datetime] = None

        try:
            metadata = trafilatura.extract_metadata(
                html_content,
                default_url=target_url,
            )
            if metadata:
                if metadata.title and metadata.title.strip():
                    title = metadata.title.strip()

                if metadata.date:
                    try:
                        # Attempt standard ISO parsing or fuzzy dateutil parsing
                        published_at = dateutil.parser.parse(str(metadata.date))
                    except Exception:
                        published_at = None
        except Exception as exc:
            logger.warning(f"Trafilatura metadata extraction exception: {type(exc).__name__}")

        return extracted_text, title, published_at

    async def _extract_with_jina(
        self, target_url: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Fetches readable content via Jina Reader API (https://r.jina.ai/{target_url}).

        Enforces:
        - Defense in depth: Validates target URL before constructing request.
        - Fixed endpoint: Only contacts the configured Jina Reader endpoint.
        - Strict streaming with maximum content length enforcement (decompressed bytes).
        - Reliable stream closure (including on exceptions/early abort).
        - Granular timeout and automatic redirects disabled.
        - Safe fallback failure without leaking internal network errors.

        Returns:
            Tuple of (jina_markdown_content, jina_title)
        """
        # 1. Defense-in-depth: Validate the embedded target URL directly
        try:
            validate_url_syntax(target_url)
        except SSRFSecurityError:
            logger.warning("Target URL rejected by SSRF guard before Jina fallback")
            return None, None

        jina_base = self.settings.JINA_READER_BASE_URL.rstrip("/")
        jina_url = f"{jina_base}/{target_url}"

        # 2. Validate syntax of the constructed Jina request URL
        try:
            validate_url_syntax(jina_url)
        except SSRFSecurityError:
            logger.warning("Jina fallback URL rejected by SSRF guard")
            return None, None

        max_bytes = self.settings.MAX_WEBSITE_CONTENT_LENGTH
        timeout = httpx.Timeout(self.settings.JINA_READER_TIMEOUT, connect=5.0)
        transport = SSRFProtectedTransport()

        headers = {
            "User-Agent": self.settings.USER_AGENT,
            "Accept": "text/plain, text/markdown",
            "X-Target-URL": target_url,
        }

        try:
            async with httpx.AsyncClient(
                transport=transport,
                timeout=timeout,
                follow_redirects=False,
                headers=headers,
            ) as client:
                request = client.build_request("GET", jina_url)
                response = await client.send(request, stream=True)

                # Reject non-200 responses safely
                if response.status_code != 200:
                    logger.warning(
                        f"Jina Reader returned non-200 status code: {response.status_code}"
                    )
                    await response.aclose()
                    return None, None

                # Check Content-Length header upfront if provided
                content_length_header = response.headers.get("content-length")
                if content_length_header:
                    try:
                        declared_len = int(content_length_header)
                        if declared_len > max_bytes:
                            logger.warning(
                                f"Jina response Content-Length ({declared_len}) exceeds limit of {max_bytes} bytes"
                            )
                            await response.aclose()
                            return None, None
                    except ValueError:
                        pass

                # Stream response body safely with decompressed byte limit guard
                body_chunks = []
                total_bytes = 0

                try:
                    async for chunk in response.aiter_bytes():
                        total_bytes += len(chunk)
                        if total_bytes > max_bytes:
                            logger.warning(
                                f"Jina response stream exceeded maximum allowed limit of {max_bytes} bytes"
                            )
                            await response.aclose()
                            return None, None
                        body_chunks.append(chunk)
                finally:
                    await response.aclose()

                raw_bytes = b"".join(body_chunks)
                if not raw_bytes or not raw_bytes.strip():
                    return None, None

                encoding = response.encoding if isinstance(response.encoding, str) else "utf-8"
                try:
                    raw_text = raw_bytes.decode(encoding, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    raw_text = raw_bytes.decode("utf-8", errors="replace")

                if not raw_text.strip():
                    return None, None

                # Extract title if Jina prepends "Title: <title>" header
                title = None
                title_match = re.search(r"^Title:\s*(.+)$", raw_text, re.MULTILINE)
                if title_match:
                    title = title_match.group(1).strip()

                return raw_text.strip(), title

        except (httpx.TimeoutException, httpx.RequestError) as exc:
            logger.warning(f"Jina Reader fallback connection error: {type(exc).__name__}")
            return None, None
        except Exception as exc:
            logger.warning(f"Unexpected Jina fallback error: {type(exc).__name__}")
            return None, None


# Reusable singleton instance
_extractor = WebsiteExtractor()


async def extract_website_content(url: str) -> WebsiteExtractionResult:
    """Convenience function to extract website content securely using the singleton extractor."""
    return await _extractor.extract(url)

