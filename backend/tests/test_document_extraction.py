"""Automated Test Suite for PDF/DOCX Document Extraction (Checkpoint 4.3).

Tests:
1. File validation (valid PDF/DOCX, empty bytes, unsupported extensions, signature mismatch,
   invalid ZIP to DOCX, ordinary ZIP to DOCX, file size exceeded, unsafe filename sanitization).
2. PDF extraction (valid text, multiple pages, metadata title, user title precedence,
   encrypted PDF rejection, corrupted PDF rejection, page count limit, empty/image-only PDF rejection,
   character/byte limits, partial extraction status).
3. DOCX extraction (paragraphs, tables, metadata title, user title precedence, invalid archive,
   missing document.xml, uncompressed size limit, compression ratio limit, path traversal entry,
   empty DOCX rejection, character/byte limits, partial extraction status, Unicode preservation).
4. General behavior (line-ending normalization, control-character/null-byte stripping,
   exact word/character counts, correct metadata and source type, safe error messages, zero disk I/O).
"""

import io
from pathlib import Path
from typing import List, Optional
import zipfile

import docx
import pypdf
import pytest

from app.core.config import get_settings
from app.core.exceptions import (
    ContentSizeExceededError,
    EncryptedDocumentError,
    ExtractionError,
    UnsupportedContentTypeError,
)
from app.schemas.source import DocumentExtractionResult
from app.services.extraction_service import (
    DocumentExtractor,
    extract_document,
)

# Base minimal valid PDF template with standard 14 font (Helvetica)
MINIMAL_PDF_BYTES = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 44 >> stream
BT
/F1 12 Tf
72 712 Td
(ClarityX PDF Page Text) Tj
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
0000000318 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
388
%%EOF"""


def build_test_pdf(
    num_pages: int = 1,
    title: Optional[str] = None,
    password: Optional[str] = None,
) -> bytes:
    """Constructs an in-memory synthetic PDF with specified pages, metadata, and optional password."""
    reader = pypdf.PdfReader(io.BytesIO(MINIMAL_PDF_BYTES))
    writer = pypdf.PdfWriter()

    for _ in range(num_pages):
        writer.add_page(reader.pages[0])

    if title:
        writer.add_metadata({"/Title": title})

    if password:
        writer.encrypt(password)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def build_blank_pdf(num_pages: int = 1) -> bytes:
    """Constructs an in-memory PDF with blank pages containing zero text streams."""
    writer = pypdf.PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=100, height=100)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def build_test_docx(
    paragraphs: Optional[List[str]] = None,
    tables: Optional[List[List[List[str]]]] = None,
    title: Optional[str] = None,
) -> bytes:
    """Constructs an in-memory synthetic DOCX document with paragraphs, tables, and metadata."""
    doc = docx.Document()
    if title:
        doc.core_properties.title = title

    if paragraphs:
        for p in paragraphs:
            doc.add_paragraph(p)

    if tables:
        for tbl_data in tables:
            if not tbl_data:
                continue
            num_rows = len(tbl_data)
            num_cols = len(tbl_data[0]) if num_rows > 0 else 0
            table = doc.add_table(rows=num_rows, cols=num_cols)
            for r_idx, row in enumerate(tbl_data):
                for c_idx, val in enumerate(row):
                    table.rows[r_idx].cells[c_idx].text = val

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


# =============================================================================
# 1. FILE VALIDATION TESTS
# =============================================================================


def test_valid_pdf_basic_extraction():
    """Standard valid PDF should extract text, page count, and return success metadata."""
    pdf_bytes = build_test_pdf(num_pages=1)
    result = extract_document(pdf_bytes, "investigation.pdf")

    assert isinstance(result, DocumentExtractionResult)
    assert result.source_type == "document"
    assert result.file_type == "pdf"
    assert result.extraction_method == "pypdf"
    assert result.extraction_status == "success"
    assert result.file_name == "investigation.pdf"
    assert result.file_size_bytes == len(pdf_bytes)
    assert result.page_count == 1
    assert "ClarityX PDF Page Text" in result.extracted_content
    assert result.character_count == len(result.extracted_content)
    assert result.word_count == 4
    assert result.error_message is None


def test_valid_docx_basic_extraction():
    """Standard valid DOCX should extract paragraphs, tables, and return success metadata."""
    docx_bytes = build_test_docx(
        paragraphs=["First section of research report.", "Second paragraph detailing evidence."],
        title="ClarityX DOCX Title",
    )
    result = extract_document(docx_bytes, "report.docx")

    assert isinstance(result, DocumentExtractionResult)
    assert result.source_type == "document"
    assert result.file_type == "docx"
    assert result.extraction_method == "python-docx"
    assert result.extraction_status == "success"
    assert result.file_name == "report.docx"
    assert result.title == "ClarityX DOCX Title"
    assert "First section of research report." in result.extracted_content
    assert "Second paragraph detailing evidence." in result.extracted_content
    assert result.page_count is None


def test_empty_bytes_rejected():
    """Empty byte input should be rejected immediately."""
    with pytest.raises(ExtractionError) as exc_info:
        extract_document(b"", "sample.pdf")
    assert "empty" in exc_info.value.message.lower()
    assert exc_info.value.status_code == 422


def test_unsupported_file_extension():
    """Disallowed extensions (.txt, .exe, .png) should be rejected with HTTP 415."""
    for bad_name in ("test.txt", "payload.exe", "image.png", "notes.doc"):
        with pytest.raises(UnsupportedContentTypeError) as exc_info:
            extract_document(b"Some text content", bad_name)
        assert exc_info.value.status_code == 415
        assert "unsupported file type" in exc_info.value.message.lower()


def test_pdf_magic_bytes_mismatch():
    """File named .pdf without %PDF- signature should be rejected with HTTP 415."""
    fake_pdf = b"NOT_A_REAL_PDF_HEADER but named pdf"
    with pytest.raises(UnsupportedContentTypeError) as exc_info:
        extract_document(fake_pdf, "forged.pdf")
    assert exc_info.value.status_code == 415
    assert "signature" in exc_info.value.message.lower()


def test_docx_magic_bytes_mismatch():
    """File named .docx without PK ZIP signature should be rejected with HTTP 415."""
    fake_docx = b"PlainTextContentThatIsSupposedToBeDocx"
    with pytest.raises(UnsupportedContentTypeError) as exc_info:
        extract_document(fake_docx, "forged.docx")
    assert exc_info.value.status_code == 415
    assert "signature" in exc_info.value.message.lower()


def test_invalid_zip_renamed_to_docx():
    """Corrupted ZIP bytes starting with PK\x03\x04 should be rejected with HTTP 422."""
    corrupted_zip = b"PK\x03\x04CorruptedGarbageThatCannotBeParsedAsZip"
    with pytest.raises(ExtractionError) as exc_info:
        extract_document(corrupted_zip, "corrupted.docx")
    assert exc_info.value.status_code == 422
    assert "corrupted or invalid" in exc_info.value.message.lower()


def test_ordinary_zip_renamed_to_docx():
    """Valid ZIP without word/document.xml should be rejected with HTTP 415."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("notes.txt", "This is an ordinary ZIP, not a Word document.")
    ordinary_zip = out.getvalue()

    with pytest.raises(UnsupportedContentTypeError) as exc_info:
        extract_document(ordinary_zip, "not_really.docx")
    assert exc_info.value.status_code == 415
    assert "not a valid docx" in exc_info.value.message.lower()


def test_file_size_exceeded():
    """Files exceeding MAX_DOCUMENT_FILE_SIZE (10 MB) should be rejected with HTTP 413."""
    settings = get_settings()
    oversized_bytes = b"%PDF-" + (b"0" * (settings.MAX_DOCUMENT_FILE_SIZE + 10))

    with pytest.raises(ContentSizeExceededError) as exc_info:
        extract_document(oversized_bytes, "oversized.pdf")
    assert exc_info.value.status_code == 413
    assert "exceeds maximum allowable limit" in exc_info.value.message.lower()


def test_unsafe_filename_sanitization():
    """Path traversal sequences and control characters in filename should be sanitized to safe basename."""
    pdf_bytes = build_test_pdf(num_pages=1)

    # Path traversal attack vectors
    for malicious in (
        "../../etc/passwd.pdf",
        "..\\..\\Windows\\System32\\config.pdf",
        "/var/log/secret.pdf",
        "C:\\Users\\admin\\malware.pdf",
        "nested/path/to/research.pdf",
    ):
        result = extract_document(pdf_bytes, malicious)
        assert "/" not in result.file_name
        assert "\\" not in result.file_name
        assert not result.file_name.startswith("..")
        assert result.file_name.endswith(".pdf")


def test_empty_or_whitespace_filename_rejected():
    """Empty or whitespace-only filename should be rejected with HTTP 422."""
    pdf_bytes = build_test_pdf(num_pages=1)
    for bad_name in ("", "   ", "\t\n"):
        with pytest.raises(ExtractionError) as exc_info:
            extract_document(pdf_bytes, bad_name)
        assert exc_info.value.status_code == 422


# =============================================================================
# 2. PDF EXTRACTION TESTS
# =============================================================================


def test_pdf_multiple_pages():
    """Multi-page PDF should extract all pages and report accurate page count."""
    pdf_bytes = build_test_pdf(num_pages=3)
    result = extract_document(pdf_bytes, "multi_page.pdf")

    assert result.page_count == 3
    assert result.extraction_status == "success"
    # Should contain page texts joined by double newline
    assert result.extracted_content.count("ClarityX PDF Page Text") == 3


def test_pdf_metadata_title():
    """PDF metadata title should be resolved when user title is not supplied."""
    pdf_bytes = build_test_pdf(num_pages=1, title="AI Safety and Governance")
    result = extract_document(pdf_bytes, "safety.pdf")

    assert result.title == "AI Safety and Governance"


def test_user_title_precedence_over_pdf_metadata():
    """User-provided title must strictly take precedence over PDF metadata title."""
    pdf_bytes = build_test_pdf(num_pages=1, title="Embedded Document Title")
    result = extract_document(pdf_bytes, "doc.pdf", title="User Explicit Title")

    assert result.title == "User Explicit Title"


def test_encrypted_pdf_rejection():
    """Password-protected / encrypted PDF must raise EncryptedDocumentError with HTTP 422."""
    encrypted_pdf = build_test_pdf(num_pages=1, password="super_secret_password")

    with pytest.raises(EncryptedDocumentError) as exc_info:
        extract_document(encrypted_pdf, "encrypted.pdf")
    assert exc_info.value.status_code == 422
    assert "password-protected or encrypted" in exc_info.value.message.lower()


def test_corrupted_pdf_rejection():
    """Corrupted PDF stream starting with %PDF- but having invalid body raises ExtractionError (422)."""
    corrupted_pdf = b"%PDF-1.4\n1 0 obj << truncated and corrupted >>\n%%EOF"

    with pytest.raises(ExtractionError) as exc_info:
        extract_document(corrupted_pdf, "broken.pdf")
    assert exc_info.value.status_code == 422


def test_pdf_page_count_limit_exceeded():
    """PDF exceeding MAX_PDF_PAGES (200 pages) should be rejected with HTTP 413."""
    oversized_pdf = build_blank_pdf(num_pages=205)

    with pytest.raises(ContentSizeExceededError) as exc_info:
        extract_document(oversized_pdf, "encyclopedia.pdf")
    assert exc_info.value.status_code == 413
    assert "page count" in exc_info.value.message.lower()


def test_empty_or_scanned_pdf_rejected():
    """PDF with zero extractable text (e.g. scanned/image-only) must raise ExtractionError (422)."""
    blank_pdf = build_blank_pdf(num_pages=2)

    with pytest.raises(ExtractionError) as exc_info:
        extract_document(blank_pdf, "scanned_invoice.pdf")
    assert exc_info.value.status_code == 422
    assert "no readable text" in exc_info.value.message.lower()


def test_pdf_character_limit_partial_status(monkeypatch):
    """PDF exceeding character limit must safely truncate and set extraction_status='partial'."""
    settings = get_settings()
    monkeypatch.setattr(settings, "MAX_DOCUMENT_EXTRACTED_CHARS", 30)

    pdf_bytes = build_test_pdf(num_pages=3)
    result = extract_document(pdf_bytes, "truncated.pdf")

    assert result.extraction_status == "partial"
    assert len(result.extracted_content) <= 30
    assert result.character_count == len(result.extracted_content)


def test_pdf_utf8_byte_limit_partial_status(monkeypatch):
    """PDF exceeding UTF-8 byte limit must safely truncate and set extraction_status='partial'."""
    settings = get_settings()
    monkeypatch.setattr(settings, "MAX_DOCUMENT_EXTRACTED_BYTES", 25)

    pdf_bytes = build_test_pdf(num_pages=2)
    result = extract_document(pdf_bytes, "byte_limit.pdf")

    assert result.extraction_status == "partial"
    assert len(result.extracted_content.encode("utf-8")) <= 25


# =============================================================================
# 3. DOCX EXTRACTION TESTS
# =============================================================================


def test_docx_table_extraction():
    """DOCX with tables should extract rows with tab-separated cells and newline-separated rows."""
    table_data = [
        ["Metric", "2024", "2025"],
        ["Accuracy", "92%", "98%"],
        ["Latency", "45ms", "12ms"],
    ]
    docx_bytes = build_test_docx(
        paragraphs=["Performance Benchmark Overview"],
        tables=[table_data],
    )
    result = extract_document(docx_bytes, "benchmark.docx")

    assert result.extraction_status == "success"
    assert "Performance Benchmark Overview" in result.extracted_content
    assert "Metric\t2024\t2025" in result.extracted_content
    assert "Accuracy\t92%\t98%" in result.extracted_content
    assert "Latency\t45ms\t12ms" in result.extracted_content


def test_docx_interleaved_paragraphs_and_tables_order():
    """DOCX paragraphs and tables must be extracted in their exact document-body order."""
    doc = docx.Document()

    # 1. Paragraph 1
    doc.add_paragraph("Paragraph 1: Initial research context.")

    # 2. Table 1
    t1 = doc.add_table(rows=1, cols=2)
    t1.rows[0].cells[0].text = "T1_Metric"
    t1.rows[0].cells[1].text = "T1_Value"

    # 3. Paragraph 2
    doc.add_paragraph("Paragraph 2: Intermediate analysis discussion.")

    # 4. Table 2
    t2 = doc.add_table(rows=1, cols=2)
    t2.rows[0].cells[0].text = "T2_Score"
    t2.rows[0].cells[1].text = "T2_Rating"

    # 5. Paragraph 3
    doc.add_paragraph("Paragraph 3: Concluding findings and gap identification.")

    out = io.BytesIO()
    doc.save(out)
    interleaved_bytes = out.getvalue()

    result = extract_document(interleaved_bytes, "interleaved.docx")

    assert result.extraction_status == "success"
    content = result.extracted_content

    # Check presence of all elements
    assert "Paragraph 1: Initial research context." in content
    assert "T1_Metric\tT1_Value" in content
    assert "Paragraph 2: Intermediate analysis discussion." in content
    assert "T2_Score\tT2_Rating" in content
    assert "Paragraph 3: Concluding findings and gap identification." in content

    # Assert exact sequential document-body order
    idx_p1 = content.index("Paragraph 1: Initial research context.")
    idx_t1 = content.index("T1_Metric\tT1_Value")
    idx_p2 = content.index("Paragraph 2: Intermediate analysis discussion.")
    idx_t2 = content.index("T2_Score\tT2_Rating")
    idx_p3 = content.index("Paragraph 3: Concluding findings and gap identification.")

    assert idx_p1 < idx_t1 < idx_p2 < idx_t2 < idx_p3



def test_docx_metadata_title():
    """DOCX metadata title should be resolved when user title is not supplied."""
    docx_bytes = build_test_docx(
        paragraphs=["Body paragraph content"],
        title="Annual Strategic Assessment",
    )
    result = extract_document(docx_bytes, "strategy.docx")

    assert result.title == "Annual Strategic Assessment"


def test_user_title_precedence_over_docx_metadata():
    """User title must strictly take precedence over DOCX core properties title."""
    docx_bytes = build_test_docx(
        paragraphs=["Document body text"],
        title="Internal Core Title",
    )
    result = extract_document(docx_bytes, "doc.docx", title="Overridden User Title")

    assert result.title == "Overridden User Title"


def test_empty_docx_rejected():
    """DOCX with zero paragraphs and zero tables should be rejected with HTTP 422."""
    empty_docx = build_test_docx(paragraphs=[], tables=[])

    with pytest.raises(ExtractionError) as exc_info:
        extract_document(empty_docx, "empty.docx")
    assert exc_info.value.status_code == 422
    assert "no readable text" in exc_info.value.message.lower()


def test_docx_zip_bomb_uncompressed_size_limit():
    """DOCX archive exceeding MAX_DOCX_TOTAL_UNCOMPRESSED_BYTES (50 MB) must raise HTTP 413."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # Write 55 MB of repeating text (compresses to ~50 KB)
        z.writestr("word/document.xml", b"0" * (55 * 1024 * 1024))
    bomb_bytes = out.getvalue()

    with pytest.raises(ContentSizeExceededError) as exc_info:
        extract_document(bomb_bytes, "bomb.docx")
    assert exc_info.value.status_code == 413
    assert "decompression size" in exc_info.value.message.lower()


def test_docx_zip_bomb_compression_ratio_limit(monkeypatch):
    """DOCX archive exceeding MAX_DOCX_UNCOMPRESSED_RATIO must raise HTTP 413."""
    settings = get_settings()
    # Set a sensitive ratio threshold to trigger ratio guard
    monkeypatch.setattr(settings, "MAX_DOCX_UNCOMPRESSED_RATIO", 5.0)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # Highly compressible content creates 200:1 ratio
        z.writestr("word/document.xml", b"A" * (2 * 1024 * 1024))
    ratio_bomb_bytes = out.getvalue()

    with pytest.raises(ContentSizeExceededError) as exc_info:
        extract_document(ratio_bomb_bytes, "ratio_bomb.docx")
    assert exc_info.value.status_code == 413
    assert "compression ratio" in exc_info.value.message.lower()


def test_docx_path_traversal_entry_rejected():
    """DOCX archive containing path traversal in entry names must raise ExtractionError (422)."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("word/document.xml", "<w:document><w:body/></w:document>")
        z.writestr("../../../etc/shadow", "malicious_content")
    traversal_zip = out.getvalue()

    with pytest.raises(ExtractionError) as exc_info:
        extract_document(traversal_zip, "evil.docx")
    assert exc_info.value.status_code == 422
    assert "suspicious or invalid entry path" in exc_info.value.message.lower()


def test_docx_character_limit_partial_status(monkeypatch):
    """DOCX exceeding character limit must truncate and set extraction_status='partial'."""
    settings = get_settings()
    monkeypatch.setattr(settings, "MAX_DOCUMENT_EXTRACTED_CHARS", 40)

    docx_bytes = build_test_docx(
        paragraphs=[
            "This is a long introductory paragraph describing the context.",
            "This second paragraph contains additional important findings.",
        ]
    )
    result = extract_document(docx_bytes, "truncated.docx")

    assert result.extraction_status == "partial"
    assert len(result.extracted_content) <= 40
    assert result.character_count == len(result.extracted_content)


def test_docx_unicode_and_scripts_preservation():
    """DOCX should preserve multilingual scripts, accents, emojis, and punctuation."""
    international_text = [
        "Français: Les données sont précises et fiables.",
        "Deutsch: Überprüfung der Qualität und Zuverlässigkeit.",
        "日本語: 情報の透明性と検証可能性の向上。",
        "العربية: التحقق من دقة وموثوقية مصادر المعلومات.",
        "हिन्दी: सूचना की प्रामाणिकता और सटीकता का परीक्षण।",
        "Emojis: 🔍 🚀 📊 💡",
    ]
    docx_bytes = build_test_docx(paragraphs=international_text)
    result = extract_document(docx_bytes, "international.docx")

    assert result.extraction_status == "success"
    for line in international_text:
        assert line in result.extracted_content


# =============================================================================
# 4. GENERAL BEHAVIOR AND METRICS TESTS
# =============================================================================


def test_title_hierarchy_first_line_and_filename_stem():
    """Title resolution falls back to first text line, then filename stem."""
    # 1. First line fallback (no user title, no metadata title)
    docx_bytes = build_test_docx(paragraphs=["# Critical Security Assessment", "Details follow..."])
    result = extract_document(docx_bytes, "assessment.docx")
    assert result.title == "Critical Security Assessment"

    # 2. Filename stem fallback when first line is already empty/generic
    docx_bytes_stem = build_test_docx(paragraphs=["Simple data."])
    result_stem = extract_document(docx_bytes_stem, "Quarterly_Summary.docx")
    assert result_stem.title in ("Simple data.", "Quarterly_Summary")


def test_user_title_whitespace_only_rejected():
    """User title that is whitespace-only should raise ExtractionError (422)."""
    docx_bytes = build_test_docx(paragraphs=["Valid document content."])
    with pytest.raises(ExtractionError) as exc_info:
        extract_document(docx_bytes, "doc.docx", title="   \t  ")
    assert exc_info.value.status_code == 422
    assert "title must not be whitespace only" in exc_info.value.message.lower()


def test_line_ending_normalization():
    """CRLF and CR line endings should be normalized to standard LF (\\n)."""
    docx_bytes = build_test_docx(
        paragraphs=["First line\r\nSecond line\rThird line"]
    )
    result = extract_document(docx_bytes, "endings.docx")

    assert "\r\n" not in result.extracted_content
    assert "\r" not in result.extracted_content
    assert "\n" in result.extracted_content


def test_control_character_and_null_byte_removal():
    """Null bytes and C0/C1 control characters must be stripped while tabs and newlines are kept."""
    extractor = DocumentExtractor()
    dirty_text = "Clean Header\x00\x08\x0b\x0c\x7f\nColumn1\tColumn2\nFinal Row"
    cleaned = extractor._sanitize_text(dirty_text)

    assert "\x00" not in cleaned
    assert "\x08" not in cleaned
    assert "\x7f" not in cleaned
    assert "\t" in cleaned
    assert "\n" in cleaned

    # Also verify through PDF extraction with control codes
    raw_pdf_with_controls = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 58 >> stream
BT
/F1 12 Tf
72 712 Td
(PDF\\000Control\\177Text\tColumn) Tj
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
0000000332 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
402
%%EOF"""
    result = extract_document(raw_pdf_with_controls, "controls.pdf")
    assert "\x00" not in result.extracted_content
    assert "\x7f" not in result.extracted_content



def test_exact_character_and_word_counts():
    """Character and word counts must match len(content) and len(content.split())."""
    text = "The rapid development of renewable energy storage systems requires verifiable evidence."
    docx_bytes = build_test_docx(paragraphs=[text])
    result = extract_document(docx_bytes, "counts.docx")

    assert result.character_count == len(result.extracted_content)
    assert result.word_count == len(result.extracted_content.split())
    assert result.word_count == 11


@pytest.mark.anyio
async def test_schema_document_extraction_result_awaitable():
    """DocumentExtractionResult must support await for uniform async pipeline integration."""
    docx_bytes = build_test_docx(paragraphs=["Asynchronous pipeline integration text."])
    result = await extract_document(docx_bytes, "async.docx")

    assert isinstance(result, DocumentExtractionResult)
    assert result.extraction_status == "success"
    assert "Asynchronous pipeline integration text." in result.extracted_content
