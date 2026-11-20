"""Website Content Extraction Service for ClarityX.

Orchestrates multi-engine content extraction:
1. Primary Extractor: Trafilatura (extracts clean text, title, and metadata without internal network calls).
2. Fallback Extractor: Jina Reader API (invoked when Trafilatura fails or yields fewer than 100 characters).
3. Security: All network operations enforce strict SSRF validation, size limits, and timeouts.
"""

from datetime import datetime
import io
import logging
from pathlib import Path
import re
from typing import Any, Optional, Tuple
import unicodedata
from urllib.parse import quote, urlsplit
import zipfile

import dateutil.parser
import docx
import httpx
import lxml.html
import pypdf
import trafilatura

from app.core.config import get_settings
from app.core.exceptions import (
    ContentSizeExceededError,
    EncryptedDocumentError,
    ExtractionError,
    IsPdfUrlError,
    SSRFSecurityError,
    UnsupportedContentTypeError,
)
from app.schemas.source import (
    DocumentExtractionResult,
    PastedTextExtractionResult,
    WebsiteExtractionResult,
    normalize_domain,
)

from app.services.ssrf_service import (
    SSRFProtectedTransport,
    fetch_pdf_document,
    fetch_website_content,
    validate_url_syntax,
)

logger = logging.getLogger("clarityx.extraction")

# Minimum characters considered useful for primary extraction before fallback
MIN_USEFUL_CONTENT_LENGTH = 100


def parse_document_date(raw_date: Any) -> Optional[datetime]:
    """Safely parses document metadata date (PDF or DOCX or ISO)."""
    if raw_date is None:
        return None
    if isinstance(raw_date, datetime):
        return raw_date
    if not isinstance(raw_date, str):
        return None
    date_str = raw_date.strip()
    if not date_str:
        return None

    # Handle PDF format: D:YYYYMMDDHHmmSS[OHH'mm']
    if date_str.startswith("D:"):
        date_str = date_str[2:].replace("'", "")

    try:
        return dateutil.parser.parse(date_str)
    except Exception:
        return None


class WebsiteExtractor:
    """Service that coordinates secure web retrieval, Trafilatura parsing, and Jina fallback."""

    def __init__(self):
        self.settings = get_settings()

    async def extract(self, url: str) -> WebsiteExtractionResult:
        """Extracts article or document content from a website URL.

        Enforces resilient multi-stage fallback:
        1. SSRF validation & protocol enforcement.
        2. Direct PDF URL detection & processing via DocumentExtractor.
        3. Primary Extractor: Trafilatura (extracts clean text, title, date, author, publisher).
        4. Fallback 1: Jina Reader API (if direct fetch fails with 403/connection error, or Trafilatura returns < 100 chars).
        5. Fallback 2: HTML Fallback Parser via lxml.html (if accessible HTML has < 100 chars in Trafilatura and Jina fails).
        6. Helpful, actionable error handling if all engines fail (suggesting PDF/DOCX upload or pasted text).
        """
        # 1. Validate initial URL syntax and security
        validate_url_syntax(url)

        domain = normalize_domain(url)
        clean_url = url.strip()

        # 2. Check for explicit PDF URL by extension
        path_without_query = clean_url.split("?")[0].lower()
        if path_without_query.endswith(".pdf"):
            return await self._extract_pdf_url(clean_url, domain)

        # 3. Attempt direct website fetch
        html_content: Optional[str] = None
        final_url: str = clean_url
        direct_fetch_error: Optional[ExtractionError] = None
        is_403_forbidden = False

        try:
            html_content, final_url, status = await fetch_website_content(clean_url)
            domain = normalize_domain(final_url)
        except IsPdfUrlError as exc:
            # Server responded with application/pdf content stream
            logger.info(f"Target URL {clean_url} dynamically serves PDF content. Routing to PDF extractor.")
            return await self._extract_pdf_url(exc.final_url, domain)
        except SSRFSecurityError:
            # Never bypass SSRF security violations!
            raise
        except (ContentSizeExceededError, UnsupportedContentTypeError):
            raise
        except ExtractionError as exc:
            direct_fetch_error = exc
            if exc.status_code == 403:
                is_403_forbidden = True
                logger.info(
                    f"Direct connection to {clean_url} returned HTTP 403 Forbidden. Will attempt Jina Reader fallback."
                )
            else:
                logger.info(
                    f"Direct fetch failed ({type(exc).__name__}: {exc.message}). Will attempt Jina Reader fallback."
                )

        # 4. If direct fetch succeeded (we have HTML content):
        if html_content:
            # 4a. Primary Extractor: Trafilatura
            (
                trafilatura_text,
                trafilatura_title,
                published_at,
                author,
                publisher,
                last_updated_at,
            ) = self._extract_with_trafilatura(
                html_content=html_content, target_url=final_url
            )

            if trafilatura_text and len(trafilatura_text.strip()) >= MIN_USEFUL_CONTENT_LENGTH:
                logger.info(
                    f"Trafilatura successfully extracted {len(trafilatura_text)} characters from {final_url}"
                )
                return WebsiteExtractionResult(
                    url=final_url,
                    title=trafilatura_title,
                    extracted_content=trafilatura_text.strip(),
                    author=author,
                    publisher=publisher,
                    domain=domain,
                    published_at=published_at,
                    last_updated_at=last_updated_at,
                    extraction_method="trafilatura",
                    extraction_status="success",
                )

            logger.info(
                f"Trafilatura yielded insufficient content ({len(trafilatura_text) if trafilatura_text else 0} chars) "
                f"for {final_url}. Attempting Jina Reader fallback."
            )

            # 4b. Fallback 1: Jina Reader API
            jina_text, jina_title = await self._extract_with_jina(final_url)

            if jina_text and len(jina_text.strip()) >= MIN_USEFUL_CONTENT_LENGTH:
                logger.info(
                    f"Jina Reader fallback successfully extracted {len(jina_text)} characters for {final_url}"
                )
                return WebsiteExtractionResult(
                    url=final_url,
                    title=jina_title or trafilatura_title,
                    extracted_content=jina_text.strip(),
                    author=author,
                    publisher=publisher,
                    domain=domain,
                    published_at=published_at,
                    last_updated_at=last_updated_at,
                    extraction_method="jina",
                    extraction_status="success",
                )

            # 4c. Fallback 2: HTML Fallback Parser (lxml.html)
            logger.info(f"Attempting HTML fallback parser for {final_url}")
            html_text, html_title, html_author = self._extract_with_html_parser(
                html_content, final_url
            )

            if html_text and len(html_text.strip()) >= MIN_USEFUL_CONTENT_LENGTH:
                logger.info(
                    f"HTML fallback parser successfully extracted {len(html_text)} characters for {final_url}"
                )
                return WebsiteExtractionResult(
                    url=final_url,
                    title=html_title or trafilatura_title,
                    extracted_content=html_text.strip(),
                    author=author or html_author,
                    publisher=publisher,
                    domain=domain,
                    published_at=published_at,
                    last_updated_at=last_updated_at,
                    extraction_method="html_parser",
                    extraction_status="success",
                )

            # 4d. Handle partial extraction if any text was collected
            best_content = ""
            best_method: str = "trafilatura"

            for candidate_text, method_name in [
                (trafilatura_text, "trafilatura"),
                (jina_text, "jina"),
                (html_text, "html_parser"),
            ]:
                if candidate_text and len(candidate_text.strip()) > len(best_content):
                    best_content = candidate_text.strip()
                    best_method = method_name

            if best_content:
                logger.warning(
                    f"Extraction yielded only partial content ({len(best_content)} chars) for {final_url}"
                )
                return WebsiteExtractionResult(
                    url=final_url,
                    title=trafilatura_title or jina_title or html_title,
                    extracted_content=best_content,
                    author=author or html_author,
                    publisher=publisher,
                    domain=domain,
                    published_at=published_at,
                    last_updated_at=last_updated_at,
                    extraction_method=best_method,  # type: ignore[arg-type]
                    extraction_status="partial",
                )

        # 5. Direct fetch failed (e.g. HTTP 403 Forbidden, connection timeout, 5xx):
        # Fallback to Jina Reader for public webpages without blindly retrying the forbidden endpoint
        else:
            logger.info(f"Attempting Jina Reader fallback after direct fetch failure for {clean_url}")
            jina_text, jina_title = await self._extract_with_jina(clean_url)

            if jina_text and len(jina_text.strip()) >= MIN_USEFUL_CONTENT_LENGTH:
                logger.info(
                    f"Jina Reader fallback rescued extraction ({len(jina_text)} chars) for {clean_url}"
                )
                return WebsiteExtractionResult(
                    url=clean_url,
                    title=jina_title,
                    extracted_content=jina_text.strip(),
                    author=None,
                    publisher=None,
                    domain=domain,
                    published_at=None,
                    last_updated_at=None,
                    extraction_method="jina",
                    extraction_status="success",
                )

        # 6. If every extraction method failed, return a specific, actionable error message
        hostname_display = domain or clean_url
        if is_403_forbidden:
            raise ExtractionError(
                message=f"The website '{hostname_display}' is protected by access controls or anti-bot verification (HTTP 403 Forbidden).",
                detail=(
                    f"ClarityX cannot bypass security restrictions or CAPTCHA challenges on '{hostname_display}'. "
                    "Please save or export the webpage content and use Document Upload (PDF/DOCX) or Pasted Text."
                ),
                status_code=403,
            )
        elif direct_fetch_error and direct_fetch_error.status_code == 404:
            raise ExtractionError(
                message=f"The requested webpage was not found on '{hostname_display}' (HTTP 404 Not Found).",
                detail="Please verify the URL or provide the content via Document Upload or Pasted Text.",
                status_code=404,
            )
        elif direct_fetch_error and direct_fetch_error.status_code == 504:
            raise ExtractionError(
                message=f"Request to '{hostname_display}' timed out.",
                detail="The website took too long to respond. Please check the URL or provide the content via Document Upload or Pasted Text.",
                status_code=504,
            )
        else:
            raise ExtractionError(
                message=f"Unable to extract meaningful readable content from '{hostname_display}'.",
                detail=(
                    f"All extraction methods (Trafilatura, Jina Reader, and HTML parser) failed to retrieve usable text. "
                    "Please provide the content via Document Upload (PDF/DOCX) or Pasted Text."
                ),
                status_code=422,
            )

    async def _extract_pdf_url(
        self, target_url: str, domain: Optional[str]
    ) -> WebsiteExtractionResult:
        """Downloads a PDF document from a URL and extracts its content using DocumentExtractor."""
        pdf_bytes, final_url = await fetch_pdf_document(target_url)

        # Derive a safe filename from the URL path
        url_path = urlsplit(final_url).path
        filename = Path(url_path).name or "document.pdf"
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"

        # Use DocumentExtractor to extract text, title, author, and date safely
        doc_extractor = DocumentExtractor()
        doc_result = doc_extractor.extract(pdf_bytes, filename=filename)

        status = doc_result.extraction_status
        # If extracted content is fewer than MIN_USEFUL_CONTENT_LENGTH (e.g. 13 chars), mark as partial
        if status == "success" and len(doc_result.extracted_content.strip()) < MIN_USEFUL_CONTENT_LENGTH:
            status = "partial"

        return WebsiteExtractionResult(
            url=final_url,
            title=doc_result.title,
            extracted_content=doc_result.extracted_content,
            author=doc_result.author,
            publisher=None,
            domain=domain or normalize_domain(final_url),
            published_at=doc_result.document_created_at,
            last_updated_at=None,
            extraction_method="pdf",
            extraction_status=status,
        )

    def _extract_with_html_parser(
        self, html_content: str, target_url: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Fallback extractor using lxml.html when Trafilatura and Jina yield insufficient text.

        Extracts title, meta description, and clean text from article/main/body tags,
        stripping scripts, styles, noscript, svg, nav, and footers.

        Returns:
            Tuple of (clean_text, title, author)
        """
        if not html_content or not html_content.strip():
            return None, None, None

        try:
            doc = lxml.html.fromstring(html_content)

            # 1. Title extraction
            title = None
            title_tag = doc.find(".//title")
            if title_tag is not None and title_tag.text:
                title = " ".join(title_tag.text.split()).strip()

            if not title:
                og_title = doc.xpath(
                    "//meta[@property='og:title']/@content | //meta[@name='twitter:title']/@content"
                )
                if og_title and str(og_title[0]).strip():
                    title = str(og_title[0]).strip()

            # 2. Author extraction
            author = None
            meta_author = doc.xpath(
                "//meta[@name='author']/@content | //meta[@property='article:author']/@content"
            )
            if meta_author and str(meta_author[0]).strip():
                author = str(meta_author[0]).strip()

            # 3. Clean DOM: drop non-content elements
            for tag in doc.xpath(
                "//script | //style | //noscript | //svg | //nav | //footer | //header | //aside | //form"
            ):
                tag.drop_tree()

            # 4. Extract content: prefer <article> or <main> if present with substantial text
            article_nodes = doc.xpath("//article | //main")
            best_text = ""
            if article_nodes:
                for node in article_nodes:
                    node_text = " ".join(node.text_content().split())
                    if len(node_text) > len(best_text):
                        best_text = node_text

            # If article/main had < 100 chars, fall back to entire body text
            if len(best_text) < MIN_USEFUL_CONTENT_LENGTH:
                best_text = " ".join(doc.text_content().split())

            clean_text = best_text.strip()
            if not clean_text:
                return None, title, author

            return clean_text, title, author

        except Exception as exc:
            logger.warning(f"Fallback HTML parser error for {target_url}: {type(exc).__name__}")
            return None, None, None

    def _extract_with_trafilatura(
        self, html_content: str, target_url: str
    ) -> Tuple[
        Optional[str],
        Optional[str],
        Optional[datetime],
        Optional[str],
        Optional[str],
        Optional[datetime],
    ]:
        """Parses raw HTML using Trafilatura without performing any network calls.

        Returns:
            Tuple of (extracted_text, title, published_date, author, publisher, last_updated_at)
        """
        if not html_content or not isinstance(html_content, str):
            return None, None, None, None, None, None

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

        # Extract metadata (title, publication date, author, publisher, last_updated_at)
        title: Optional[str] = None
        published_at: Optional[datetime] = None
        author: Optional[str] = None
        publisher: Optional[str] = None
        last_updated_at: Optional[datetime] = None

        try:
            metadata = trafilatura.extract_metadata(
                html_content,
                default_url=target_url,
            )
            if metadata:
                if (
                    hasattr(metadata, "title")
                    and isinstance(metadata.title, str)
                    and metadata.title.strip()
                ):
                    title = metadata.title.strip()[:255]

                if hasattr(metadata, "date") and metadata.date:
                    try:
                        # Attempt standard ISO parsing or fuzzy dateutil parsing
                        published_at = dateutil.parser.parse(str(metadata.date))
                    except Exception:
                        published_at = None

                if (
                    hasattr(metadata, "author")
                    and isinstance(metadata.author, str)
                    and metadata.author.strip()
                ):
                    author = metadata.author.strip()[:255]

                if (
                    hasattr(metadata, "sitename")
                    and isinstance(metadata.sitename, str)
                    and metadata.sitename.strip()
                ):
                    publisher = metadata.sitename.strip()[:255]
        except Exception as exc:
            logger.warning(f"Trafilatura metadata extraction exception: {type(exc).__name__}")

        # Meta tag fallbacks if trafilatura did not discover them
        if not author and html_content:
            author_match = re.search(
                r'<meta[^>]+(?:name|property)=["\'](?:author|article:author|byl|dc\.creator)["\'][^>]+content=["\']([^"\']+)["\']',
                html_content,
                re.IGNORECASE,
            ) or re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:author|article:author|byl|dc\.creator)["\']',
                html_content,
                re.IGNORECASE,
            )
            if author_match:
                cand = author_match.group(1).strip()
                if cand:
                    author = cand[:255]

        if not publisher and html_content:
            pub_match = re.search(
                r'<meta[^>]+(?:name|property)=["\'](?:og:site_name|publisher|dc\.publisher)["\'][^>]+content=["\']([^"\']+)["\']',
                html_content,
                re.IGNORECASE,
            ) or re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:og:site_name|publisher|dc\.publisher)["\']',
                html_content,
                re.IGNORECASE,
            )
            if pub_match:
                cand = pub_match.group(1).strip()
                if cand:
                    publisher = cand[:255]

        if not published_at and html_content:
            pub_date_match = re.search(
                r'<meta[^>]+(?:name|property)=["\'](?:article:published_time|publication_date|date|dc\.date)["\'][^>]+content=["\']([^"\']+)["\']',
                html_content,
                re.IGNORECASE,
            ) or re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:article:published_time|publication_date|date|dc\.date)["\']',
                html_content,
                re.IGNORECASE,
            )
            if pub_date_match:
                try:
                    published_at = dateutil.parser.parse(pub_date_match.group(1).strip())
                except Exception:
                    pass

        if not last_updated_at and html_content:
            modified_match = re.search(
                r'<meta[^>]+(?:name|property|itemprop)=["\'](?:article:modified_time|og:updated_time|last-modified|dateModified)["\'][^>]+content=["\']([^"\']+)["\']',
                html_content,
                re.IGNORECASE,
            ) or re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property|itemprop)=["\'](?:article:modified_time|og:updated_time|last-modified|dateModified)["\']',
                html_content,
                re.IGNORECASE,
            )
            if modified_match:
                try:
                    last_updated_at = dateutil.parser.parse(modified_match.group(1).strip())
                except Exception:
                    pass

        return extracted_text, title, published_at, author, publisher, last_updated_at

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

                # Guard against Cloudflare challenge / anti-bot interstitial returned by Jina
                lower_text = raw_text.lower()
                if (
                    "target url returned error 403" in lower_text
                    or "just a moment..." in lower_text
                    or "attention required! | cloudflare" in lower_text
                    or "cf-browser-verification" in lower_text
                ):
                    logger.warning(
                        f"Jina Reader returned anti-bot challenge or 403 error page for {target_url}"
                    )
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


class PastedTextExtractor:
    """Service that validates, sanitizes, and normalizes user-pasted text."""

    def __init__(self):
        self.settings = get_settings()

    def extract(
        self, text: str, title: Optional[str] = None
    ) -> PastedTextExtractionResult:
        """Sanitizes and normalizes pasted text content.

        Enforces:
        - Rejection of empty or whitespace-only text.
        - Enforcement of maximum character limit and UTF-8 byte limit.
        - Line-ending normalization (\r\n and \r to \n).
        - Removal of null bytes (\x00) and dangerous control characters.
        - Preservation of meaningful whitespace, paragraphs, and Unicode content.
        - Generation of sensible title from first meaningful line when not provided.
        - Exact computation of character and word counts.

        Returns:
            PastedTextExtractionResult

        Raises:
            ExtractionError: If text is empty or whitespace only.
            ContentSizeExceededError: If text exceeds character or UTF-8 byte limits.
        """
        if not text or not isinstance(text, str) or not text.strip():
            raise ExtractionError(
                message="Pasted text must not be empty or whitespace only.",
                status_code=422,
            )

        # 1. Enforce character limit
        if len(text) > self.settings.MAX_PASTED_TEXT_LENGTH:
            raise ContentSizeExceededError(
                message=f"Pasted text character count ({len(text)}) exceeds maximum allowable limit of {self.settings.MAX_PASTED_TEXT_LENGTH} characters."
            )

        # 2. Enforce UTF-8 byte limit (prevent multibyte Unicode expansion bypass)
        utf8_bytes = text.encode("utf-8")
        if len(utf8_bytes) > self.settings.MAX_PASTED_TEXT_BYTES:
            raise ContentSizeExceededError(
                message=f"Pasted text size ({len(utf8_bytes)} bytes) exceeds maximum allowable limit of {self.settings.MAX_PASTED_TEXT_BYTES} bytes."
            )

        # 3. Normalize line endings (\r\n and \r to \n)
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")

        # 4. Remove null bytes (\x00) and disallowed control characters.
        # Preserve newlines (\n) and tabs (\t), strip C0/C1 control codes and DEL (\x7f).
        cleaned_chars = []
        for ch in normalized:
            if ch in ("\n", "\t"):
                cleaned_chars.append(ch)
            elif ch == "\x00" or ord(ch) == 127 or unicodedata.category(ch) == "Cc":
                continue
            else:
                cleaned_chars.append(ch)

        cleaned_text = "".join(cleaned_chars)
        final_content = cleaned_text.strip()

        if not final_content:
            raise ExtractionError(
                message="Pasted text must not be empty or whitespace only.",
                status_code=422,
            )

        # 5. Handle title resolution
        final_title: str = "Untitled Pasted Text"

        if title is not None:
            user_title = title.strip()
            if not user_title:
                raise ExtractionError(
                    message="Title must not be whitespace only if provided.",
                    status_code=422,
                )
            final_title = user_title[:255]
        else:
            # Generate title from the first meaningful non-empty line
            generated_title = None
            for line in final_content.splitlines():
                candidate = line.strip()
                if candidate:
                    # Strip leading markdown header markers (e.g., "# Title" -> "Title")
                    clean_candidate = re.sub(r"^#+\s*", "", candidate).strip()
                    if clean_candidate:
                        generated_title = clean_candidate[:255]
                        break
            final_title = generated_title or "Untitled Pasted Text"

        # 6. Compute exact metrics
        character_count = len(final_content)
        word_count = len(final_content.split())

        logger.info(
            f"Successfully processed pasted text: {character_count} chars, {word_count} words"
        )

        return PastedTextExtractionResult(
            title=final_title,
            source_type="pasted_text",
            extracted_content=final_content,
            character_count=character_count,
            word_count=word_count,
            extraction_method="direct",
            extraction_status="success",
            error_message=None,
        )


# Reusable singleton instance for pasted text extraction
_pasted_text_extractor = PastedTextExtractor()


def extract_pasted_text(
    text: str, title: Optional[str] = None
) -> PastedTextExtractionResult:
    """Convenience function to extract and normalize pasted text using the singleton extractor."""
    return _pasted_text_extractor.extract(text, title=title)


class DocumentExtractor:
    """Service that coordinates secure, in-memory extraction for PDF and DOCX documents.

    Enforces:
    - Rejection of empty file input.
    - Pre-processing enforcement of file size limit (10 MB).
    - Filename sanitization to a safe basename (stripping directory traversal).
    - File extension and magic-byte signature validation:
        - PDF: b"%PDF-"
        - DOCX: b"PK\x03\x04", followed by ZIP archive structure validation (word/document.xml).
    - DOCX ZIP bomb prevention:
        - Total uncompressed size limit (50 MB).
        - Decompression ratio limits (100:1).
        - Path traversal checks in ZIP entry names.
    - PDF security guards:
        - Detection and rejection of encrypted/password-protected PDFs.
        - Page count limit (200 pages).
    - In-memory processing via io.BytesIO (zero filesystem writes).
    - Page-by-page PDF extraction and paragraph/table DOCX extraction.
    - Text collection limits:
        - Maximum character limit (1,048,576 chars).
        - Maximum UTF-8 byte limit (2,097,152 bytes).
        - Safe truncation with extraction_status="partial" when limits are exceeded.
    - Content sanitization:
        - Line-ending normalization (\r\n and \r to \n).
        - Null-byte (\x00) and dangerous control-character removal.
        - Preservation of tabs (\t), newlines (\n), Unicode, and international scripts.
    - Empty and scanned document detection (raises ExtractionError if 0 readable characters).
    - Hierarchical title resolution:
        1. User-provided title.
        2. Document metadata title.
        3. First meaningful extracted text line.
        4. Sanitized filename without extension.
        5. "Untitled Document".
    """

    def __init__(self):
        self.settings = get_settings()

    def sanitize_filename(self, filename: str) -> str:
        """Sanitizes user-supplied filename to a safe basename, preventing directory traversal."""
        if not filename or not isinstance(filename, str) or not filename.strip():
            raise ExtractionError("Filename must not be empty.", status_code=422)

        # Strip directory path separators and extract basename
        clean_name = Path(filename.strip()).name
        # Remove null bytes and non-printable control characters from filename
        clean_name = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", clean_name).strip()

        if not clean_name:
            raise ExtractionError(
                "Filename is invalid or empty after sanitization.", status_code=422
            )

        return clean_name

    def validate_file(self, file_bytes: bytes, filename: str) -> Tuple[str, str]:
        """Validates file existence, size, extension, and magic-byte signatures.

        Returns:
            Tuple[safe_filename, file_type] where file_type is 'pdf' or 'docx'.
        """
        if not file_bytes or len(file_bytes) == 0:
            raise ExtractionError("Document file is empty.", status_code=422)

        if len(file_bytes) > self.settings.MAX_DOCUMENT_FILE_SIZE:
            raise ContentSizeExceededError(
                message=f"Document file size ({len(file_bytes)} bytes) exceeds maximum allowable limit of {self.settings.MAX_DOCUMENT_FILE_SIZE} bytes."
            )

        safe_filename = self.sanitize_filename(filename)
        ext = Path(safe_filename).suffix.lower()

        if ext not in (".pdf", ".docx"):
            raise UnsupportedContentTypeError(
                message=f"Unsupported file type '{ext}'. Only PDF (.pdf) and Word (.docx) documents are supported."
            )

        if ext == ".pdf":
            if not file_bytes.startswith(b"%PDF-"):
                raise UnsupportedContentTypeError(
                    message="File content does not match PDF signature."
                )
            return safe_filename, "pdf"
        else:  # ext == ".docx"
            if not file_bytes.startswith(b"PK\x03\x04"):
                raise UnsupportedContentTypeError(
                    message="File content does not match DOCX/ZIP signature."
                )
            return safe_filename, "docx"

    def _validate_docx_zip(self, file_bytes: bytes) -> zipfile.ZipFile:
        """Inspects the ZIP archive structure of a DOCX file to guard against ZIP bombs and invalid archives."""
        try:
            zip_obj = zipfile.ZipFile(io.BytesIO(file_bytes))
        except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            raise ExtractionError(
                message="Corrupted or invalid DOCX archive.",
                status_code=422,
            ) from exc

        namelist = zip_obj.namelist()

        # Check required DOCX structure
        if "word/document.xml" not in namelist:
            raise UnsupportedContentTypeError(
                message="The uploaded archive is not a valid DOCX document (missing word/document.xml)."
            )

        # Check for path traversal in entry names
        for name in namelist:
            if name.startswith(("/", "\\")) or ".." in name.split("/"):
                raise ExtractionError(
                    message="Suspicious or invalid entry path in DOCX archive.",
                    status_code=422,
                )

        # ZIP bomb audit: check total uncompressed size and compression ratios
        total_uncompressed = 0
        file_len = len(file_bytes)

        for info in zip_obj.infolist():
            total_uncompressed += info.file_size

        if total_uncompressed > self.settings.MAX_DOCX_TOTAL_UNCOMPRESSED_BYTES:
            raise ContentSizeExceededError(
                message=f"DOCX decompression size ({total_uncompressed} bytes) exceeds maximum allowable limit of {self.settings.MAX_DOCX_TOTAL_UNCOMPRESSED_BYTES} bytes."
            )

        for info in zip_obj.infolist():
            # Per-entry compression ratio check for entries larger than 1 MB
            if info.compress_size > 0 and info.file_size > 1024 * 1024:
                ratio = info.file_size / info.compress_size
                if ratio > self.settings.MAX_DOCX_UNCOMPRESSED_RATIO:
                    raise ContentSizeExceededError(
                        message=f"DOCX entry '{info.filename}' exceeds maximum allowable compression ratio ({ratio:.1f} > {self.settings.MAX_DOCX_UNCOMPRESSED_RATIO})."
                    )

        if file_len > 0:
            total_ratio = total_uncompressed / file_len
            if total_ratio > self.settings.MAX_DOCX_UNCOMPRESSED_RATIO:
                raise ContentSizeExceededError(
                    message=f"DOCX archive exceeds maximum allowable compression ratio ({total_ratio:.1f} > {self.settings.MAX_DOCX_UNCOMPRESSED_RATIO})."
                )


        return zip_obj

    def _accumulate_chunk(
        self, text: str, accumulated_chars: int, accumulated_bytes: int
    ) -> Tuple[str, bool]:
        """Calculates text chunk fit against character and UTF-8 byte limits.

        Returns:
            Tuple[chunk_to_add, is_partial]
        """
        remaining_chars = (
            self.settings.MAX_DOCUMENT_EXTRACTED_CHARS - accumulated_chars
        )
        remaining_bytes = (
            self.settings.MAX_DOCUMENT_EXTRACTED_BYTES - accumulated_bytes
        )

        if remaining_chars <= 0 or remaining_bytes <= 0:
            return "", True

        chunk = text
        is_partial = False

        if len(chunk) > remaining_chars:
            chunk = chunk[:remaining_chars]
            is_partial = True

        encoded = chunk.encode("utf-8")
        if len(encoded) > remaining_bytes:
            encoded = encoded[:remaining_bytes]
            chunk = encoded.decode("utf-8", errors="ignore")
            is_partial = True

        return chunk, is_partial

    def _sanitize_text(self, text: str) -> str:
        """Sanitizes text by normalizing line endings and removing null bytes and control codes."""
        if not text:
            return ""

        # Normalize line endings
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")

        # Strip null bytes and C0/C1 control characters (preserve \n and \t)
        cleaned_chars = []
        for ch in normalized:
            if ch in ("\n", "\t"):
                cleaned_chars.append(ch)
            elif ch == "\x00" or ord(ch) == 127 or unicodedata.category(ch) == "Cc":
                continue
            else:
                cleaned_chars.append(ch)

        return "".join(cleaned_chars).strip()

    def _resolve_title(
        self,
        user_title: Optional[str],
        metadata_title: Optional[str],
        first_line_content: str,
        safe_filename: str,
    ) -> str:
        """Resolves document title according to established priority order:
        1. User-provided title.
        2. Document metadata title.
        3. First meaningful extracted text line.
        4. Sanitized filename without extension.
        5. "Untitled Document".
        """
        if user_title:
            user_clean = user_title.strip()
            if user_clean:
                return user_clean[:255]

        if metadata_title:
            meta_clean = metadata_title.strip()
            if meta_clean:
                return meta_clean[:255]

        # Extract first non-empty line
        for line in first_line_content.splitlines():
            candidate = line.strip()
            if candidate:
                clean_candidate = re.sub(r"^#+\s*", "", candidate).strip()
                if clean_candidate:
                    return clean_candidate[:255]

        # Fallback to filename stem
        stem = Path(safe_filename).stem.strip()
        if stem:
            return stem[:255]

        return "Untitled Document"

    def _extract_pdf(
        self, file_bytes: bytes, safe_filename: str, user_title: Optional[str] = None
    ) -> DocumentExtractionResult:
        """Extracts text and metadata from a validated PDF file in-memory page-by-page."""
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        except Exception as exc:
            logger.warning(f"Failed to parse PDF document: {exc}")
            raise ExtractionError(
                message="Corrupted or invalid PDF document.",
                status_code=422,
            ) from exc

        # Detect password protection / encryption
        if reader.is_encrypted:
            raise EncryptedDocumentError(
                message="Password-protected or encrypted documents cannot be processed."
            )

        try:
            num_pages = len(reader.pages)
        except Exception as exc:
            raise ExtractionError(
                message="Corrupted or unreadable PDF page catalog.",
                status_code=422,
            ) from exc

        if num_pages > self.settings.MAX_PDF_PAGES:
            raise ContentSizeExceededError(
                message=f"PDF document exceeds maximum allowable page count of {self.settings.MAX_PDF_PAGES} pages (found {num_pages} pages)."
            )

        metadata_title = None
        metadata_author = None
        doc_created_at = None
        doc_modified_at = None
        try:
            if reader.metadata:
                if getattr(reader.metadata, "title", None):
                    t = str(reader.metadata.title).strip()
                    if t:
                        metadata_title = t
                if getattr(reader.metadata, "author", None):
                    a = str(reader.metadata.author).strip()
                    if a:
                        metadata_author = a[:255]

                # PDF creation date
                raw_cdate = getattr(reader.metadata, "creation_date", None)
                if not raw_cdate and hasattr(reader.metadata, "get"):
                    raw_cdate = reader.metadata.get("/CreationDate")
                doc_created_at = parse_document_date(raw_cdate)

                # PDF modification date
                raw_mdate = getattr(reader.metadata, "modification_date", None)
                if not raw_mdate and hasattr(reader.metadata, "get"):
                    raw_mdate = reader.metadata.get("/ModDate")
                doc_modified_at = parse_document_date(raw_mdate)
        except Exception:
            pass  # Corrupted metadata should not fail extraction

        page_texts = []
        is_partial = False
        accumulated_chars = 0
        accumulated_bytes = 0

        for page_idx in range(num_pages):
            try:
                page = reader.pages[page_idx]
                page_raw = page.extract_text() or ""
            except Exception as exc:
                logger.warning(
                    f"Failed to extract text from page {page_idx + 1}: {exc}"
                )
                continue

            if not page_raw or not page_raw.strip():
                continue

            chunk, is_part = self._accumulate_chunk(
                page_raw, accumulated_chars, accumulated_bytes
            )
            page_texts.append(chunk)
            sep_len = 2 if len(page_texts) > 1 else 0
            accumulated_chars += len(chunk) + sep_len
            accumulated_bytes += len(chunk.encode("utf-8")) + sep_len
            if is_part:
                is_partial = True
                break

        raw_content = "\n\n".join(page_texts)
        final_content = self._sanitize_text(raw_content)

        # Enforce strict final boundary caps ensuring join separators do not push over limits
        if len(final_content) > self.settings.MAX_DOCUMENT_EXTRACTED_CHARS:
            final_content = final_content[: self.settings.MAX_DOCUMENT_EXTRACTED_CHARS]
            is_partial = True

        encoded = final_content.encode("utf-8")
        if len(encoded) > self.settings.MAX_DOCUMENT_EXTRACTED_BYTES:
            encoded = encoded[: self.settings.MAX_DOCUMENT_EXTRACTED_BYTES]
            final_content = encoded.decode("utf-8", errors="ignore")
            is_partial = True

        final_content = final_content.strip()


        if not final_content:
            raise ExtractionError(
                message="No readable text found in document. Scanned or image-only documents are not currently supported.",
                status_code=422,
            )

        final_title = self._resolve_title(
            user_title=user_title,
            metadata_title=metadata_title,
            first_line_content=final_content,
            safe_filename=safe_filename,
        )

        char_count = len(final_content)
        word_count = len(final_content.split())

        logger.info(
            f"Successfully processed PDF document '{safe_filename}': {char_count} chars, {word_count} words, {num_pages} pages"
        )

        return DocumentExtractionResult(
            file_name=safe_filename,
            file_type="pdf",
            file_size_bytes=len(file_bytes),
            title=final_title,
            source_type="document",
            extracted_content=final_content,
            character_count=char_count,
            word_count=word_count,
            page_count=num_pages,
            author=metadata_author,
            document_created_at=doc_created_at,
            document_modified_at=doc_modified_at,
            extraction_method="pypdf",
            extraction_status="partial" if is_partial else "success",
            error_message=None,
        )

    def _extract_docx(
        self, file_bytes: bytes, safe_filename: str, user_title: Optional[str] = None
    ) -> DocumentExtractionResult:
        """Extracts text, metadata, and tables from a validated DOCX file in-memory."""
        zip_obj = self._validate_docx_zip(file_bytes)
        zip_obj.close()

        try:
            doc = docx.Document(io.BytesIO(file_bytes))
        except Exception as exc:
            logger.warning(f"Failed to parse DOCX document: {exc}")
            raise ExtractionError(
                message="Failed to parse DOCX document content.",
                status_code=422,
            ) from exc

        metadata_title = None
        metadata_author = None
        doc_created_at = None
        doc_modified_at = None
        try:
            if doc.core_properties:
                if getattr(doc.core_properties, "title", None):
                    t = str(doc.core_properties.title).strip()
                    if t:
                        metadata_title = t
                if getattr(doc.core_properties, "author", None):
                    a = str(doc.core_properties.author).strip()
                    if a:
                        metadata_author = a[:255]
                if getattr(doc.core_properties, "created", None):
                    doc_created_at = parse_document_date(doc.core_properties.created)
                if getattr(doc.core_properties, "modified", None):
                    doc_modified_at = parse_document_date(doc.core_properties.modified)
        except Exception:
            pass

        text_blocks = []
        is_partial = False
        accumulated_chars = 0
        accumulated_bytes = 0

        # Extract body elements in true document order (paragraphs and tables interleaved)
        def _iter_body_items():
            if hasattr(doc, "iter_inner_content"):
                yield from doc.iter_inner_content()
            else:
                for child in doc.element.body:
                    if child.tag.endswith("p"):
                        yield docx.text.paragraph.Paragraph(child, doc)
                    elif child.tag.endswith("tbl"):
                        yield docx.table.Table(child, doc)

        for item in _iter_body_items():
            if isinstance(item, docx.text.paragraph.Paragraph):
                p_text = item.text
                if not p_text or not p_text.strip():
                    continue

                chunk, is_part = self._accumulate_chunk(
                    p_text, accumulated_chars, accumulated_bytes
                )
                text_blocks.append(chunk)
                sep_len = 2 if len(text_blocks) > 1 else 0
                accumulated_chars += len(chunk) + sep_len
                accumulated_bytes += len(chunk.encode("utf-8")) + sep_len
                if is_part:
                    is_partial = True
                    break

            elif isinstance(item, docx.table.Table):
                for row in item.rows:
                    cells_text = [cell.text.strip() for cell in row.cells]
                    row_str = "\t".join(cells_text).strip()
                    if not row_str:
                        continue

                    chunk, is_part = self._accumulate_chunk(
                        row_str, accumulated_chars, accumulated_bytes
                    )
                    text_blocks.append(chunk)
                    sep_len = 2 if len(text_blocks) > 1 else 0
                    accumulated_chars += len(chunk) + sep_len
                    accumulated_bytes += len(chunk.encode("utf-8")) + sep_len
                    if is_part:
                        is_partial = True
                        break
                if is_partial:
                    break


        raw_content = "\n\n".join(text_blocks)
        final_content = self._sanitize_text(raw_content)

        # Enforce strict final boundary caps ensuring join separators do not push over limits
        if len(final_content) > self.settings.MAX_DOCUMENT_EXTRACTED_CHARS:
            final_content = final_content[: self.settings.MAX_DOCUMENT_EXTRACTED_CHARS]
            is_partial = True

        encoded = final_content.encode("utf-8")
        if len(encoded) > self.settings.MAX_DOCUMENT_EXTRACTED_BYTES:
            encoded = encoded[: self.settings.MAX_DOCUMENT_EXTRACTED_BYTES]
            final_content = encoded.decode("utf-8", errors="ignore")
            is_partial = True

        final_content = final_content.strip()


        if not final_content:
            raise ExtractionError(
                message="No readable text found in document. Scanned or image-only documents are not currently supported.",
                status_code=422,
            )

        final_title = self._resolve_title(
            user_title=user_title,
            metadata_title=metadata_title,
            first_line_content=final_content,
            safe_filename=safe_filename,
        )

        char_count = len(final_content)
        word_count = len(final_content.split())

        logger.info(
            f"Successfully processed DOCX document '{safe_filename}': {char_count} chars, {word_count} words"
        )

        return DocumentExtractionResult(
            file_name=safe_filename,
            file_type="docx",
            file_size_bytes=len(file_bytes),
            title=final_title,
            source_type="document",
            extracted_content=final_content,
            character_count=char_count,
            word_count=word_count,
            page_count=None,
            author=metadata_author,
            document_created_at=doc_created_at,
            document_modified_at=doc_modified_at,
            extraction_method="python-docx",
            extraction_status="partial" if is_partial else "success",
            error_message=None,
        )

    def extract(
        self, file_bytes: bytes, filename: str, title: Optional[str] = None
    ) -> DocumentExtractionResult:
        """Extracts and normalizes content from a PDF or DOCX file.

        Args:
            file_bytes: Raw binary bytes of the document.
            filename: Original filename (used for validation and metadata).
            title: Optional user-provided title override.

        Returns:
            DocumentExtractionResult

        Raises:
            ExtractionError: If file is empty, corrupted, unreadable, or missing text.
            ContentSizeExceededError: If file size, page count, or uncompressed size exceeds limits.
            UnsupportedContentTypeError: If extension or file signature is invalid.
            EncryptedDocumentError: If document is password-protected or encrypted.
        """
        safe_filename, file_type = self.validate_file(file_bytes, filename)

        user_title_clean: Optional[str] = None
        if title is not None:
            user_title_clean = title.strip()
            if not user_title_clean:
                raise ExtractionError(
                    message="Title must not be whitespace only if provided.",
                    status_code=422,
                )

        if file_type == "pdf":
            return self._extract_pdf(
                file_bytes, safe_filename, user_title=user_title_clean
            )
        else:
            return self._extract_docx(
                file_bytes, safe_filename, user_title=user_title_clean
            )


# Reusable singleton instance for document extraction
_document_extractor = DocumentExtractor()


def extract_document(
    file_bytes: bytes, filename: str, title: Optional[str] = None
) -> DocumentExtractionResult:
    """Convenience function to extract and normalize document content using the singleton extractor."""
    return _document_extractor.extract(file_bytes, filename, title=title)



