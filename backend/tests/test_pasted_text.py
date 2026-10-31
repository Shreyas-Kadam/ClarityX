"""Automated Test Suite for Pasted Text Extraction (Checkpoint 4.2).

Tests:
1. Valid pasted text extraction and normalization.
2. Optional user-provided title handling and sanitization.
3. Automatic title generation from the first non-empty line (including Markdown heading stripping and truncation).
4. Empty and whitespace-only text rejection.
5. Short but meaningful text extraction.
6. Maximum character length boundary and exceeded limit rejection.
7. Multibyte UTF-8 byte limit enforcement (multibyte Unicode exceeding byte limit while within char limit).
8. Unicode text and script preservation (emojis, CJK, Arabic, Hindi, accents, quotes).
9. Line ending normalization (CRLF and CR to LF).
10. Null byte (\x00) and dangerous control character removal while preserving tabs and newlines.
11. Paragraph breaks and interior whitespace preservation.
12. Exact character and word count calculations.
13. Metadata correctness (source_type, extraction_method, extraction_status).
14. Schema validation for PastedTextExtractRequest (forbids extra fields, validates title and text).
"""

import pytest
from pydantic import ValidationError

from app.core.exceptions import (
    ContentSizeExceededError,
    ExtractionError,
)
from app.schemas.source import (
    PastedTextExtractRequest,
    PastedTextExtractionResult,
)
from app.services.extraction_service import (
    PastedTextExtractor,
    extract_pasted_text,
)


def test_valid_pasted_text_basic():
    """Standard pasted text should be cleanly extracted with default metadata."""
    sample_text = "This is a simple paragraph submitted as research context. It discusses basic facts."
    result = extract_pasted_text(sample_text)

    assert isinstance(result, PastedTextExtractionResult)
    assert result.extracted_content == sample_text
    assert result.source_type == "pasted_text"
    assert result.extraction_method == "direct"
    assert result.extraction_status == "success"
    assert result.error_message is None
    assert result.character_count == len(sample_text)
    assert result.word_count == 13
    assert result.title == sample_text[:255]


def test_user_provided_title():
    """User-provided title should override automatic generation and be trimmed."""
    text = "The quick brown fox jumps over the lazy dog."
    result = extract_pasted_text(text, title="  Custom Investigation Title  ")

    assert result.title == "Custom Investigation Title"
    assert result.extracted_content == text


def test_automatic_title_generation_from_first_line():
    """Title should be derived from the first non-empty line."""
    text = """

    # Breakthrough in Quantum Computing

    Researchers at the laboratory announced a new superconducting qubit architecture
    with unprecedented coherence times.
    """
    result = extract_pasted_text(text)

    # Heading marker '# ' should be cleanly stripped from the title
    assert result.title == "Breakthrough in Quantum Computing"
    assert "superconducting qubit" in result.extracted_content


def test_automatic_title_generation_truncation():
    """Generated title should be safely capped at 255 characters."""
    long_first_line = "A" * 300
    text = f"{long_first_line}\nSecond line of the document."
    result = extract_pasted_text(text)

    assert len(result.title) == 255
    assert result.title == "A" * 255


def test_title_fallback_when_first_line_has_no_alphanumeric():
    """Fallback title is used if first line is stripped of heading markers and empty."""
    text = "### \nActual body text starting on second line."
    result = extract_pasted_text(text)

    assert result.title == "Actual body text starting on second line."


def test_empty_input_rejection():
    """Completely empty input must raise ExtractionError with status 422."""
    with pytest.raises(ExtractionError) as exc_info:
        extract_pasted_text("")
    assert exc_info.value.status_code == 422
    assert "empty or whitespace only" in exc_info.value.message.lower()


def test_whitespace_only_input_rejection():
    """Whitespace-only text (spaces, newlines, tabs) must raise ExtractionError."""
    with pytest.raises(ExtractionError) as exc_info:
        extract_pasted_text("   \n\t\r\n   ")
    assert exc_info.value.status_code == 422
    assert "empty or whitespace only" in exc_info.value.message.lower()


def test_short_meaningful_text():
    """Short meaningful phrases (e.g. status updates) must be accepted without arbitrary minimums."""
    short_text = "Meeting canceled."
    result = extract_pasted_text(short_text)

    assert result.extracted_content == "Meeting canceled."
    assert result.character_count == 17
    assert result.word_count == 2
    assert result.extraction_status == "success"


def test_whitespace_only_title_rejection():
    """Providing a whitespace-only title must raise ExtractionError."""
    with pytest.raises(ExtractionError) as exc_info:
        extract_pasted_text("Valid text content here.", title="   \t  ")
    assert exc_info.value.status_code == 422
    assert "title must not be whitespace only" in exc_info.value.message.lower()


def test_line_ending_normalization():
    """CRLF and CR line endings must be normalized to standard LF."""
    raw_text = "Line 1\r\nLine 2\rLine 3\nLine 4"
    result = extract_pasted_text(raw_text)

    assert result.extracted_content == "Line 1\nLine 2\nLine 3\nLine 4"
    assert "\r" not in result.extracted_content


def test_null_byte_removal():
    """Null bytes (\\x00) must be stripped to prevent PostgreSQL driver errors."""
    raw_text = "Clean\x00 text with \x00null bytes embedded."
    result = extract_pasted_text(raw_text)

    assert "\x00" not in result.extracted_content
    assert result.extracted_content == "Clean text with null bytes embedded."


def test_dangerous_control_characters_removal():
    """Dangerous non-printable control characters must be stripped while tabs and newlines are preserved."""
    # \x07 (bell), \x08 (backspace), \x1b (escape), \x7f (DEL)
    raw_text = "Important:\tTab preserved\nNewline preserved.\x07\x08\x1b\x7fDone."
    result = extract_pasted_text(raw_text)

    assert "\t" in result.extracted_content
    assert "\n" in result.extracted_content
    assert "\x07" not in result.extracted_content
    assert "\x08" not in result.extracted_content
    assert "\x1b" not in result.extracted_content
    assert "\x7f" not in result.extracted_content
    assert result.extracted_content == "Important:\tTab preserved\nNewline preserved.Done."


def test_paragraph_and_whitespace_preservation():
    """Paragraph breaks (double newlines) and interior indentation must be preserved."""
    raw_text = "Paragraph 1.\n\nParagraph 2 with    interior spaces.\n\n\tIndented Paragraph 3."
    result = extract_pasted_text(raw_text)

    assert result.extracted_content == raw_text
    assert "Paragraph 1.\n\nParagraph 2 with    interior spaces.\n\n\tIndented Paragraph 3." == result.extracted_content


def test_unicode_preservation_multilingual():
    """Diverse multilingual scripts, diacritics, and emojis must be preserved exactly."""
    multilingual = (
        "English with 'smart quotes' and em—dash.\n"
        "French: Résumé de l'événement.\n"
        "German: Über die Brücke.\n"
        "Japanese: 量子コンピューティングの研究。\n"
        "Arabic: الذكاء الاصطناعي وتحليل الفجوات.\n"
        "Hindi: सूचना अंतराल का पता लगाना।\n"
        "Emojis: 🚀 🔬 💡 📊"
    )
    result = extract_pasted_text(multilingual)

    assert result.extracted_content == multilingual
    assert "Résumé" in result.extracted_content
    assert "量子コンピューティング" in result.extracted_content
    assert "الذكاء الاصطناعي" in result.extracted_content
    assert "सूचना अंतराल" in result.extracted_content
    assert "🚀 🔬 💡 📊" in result.extracted_content


def test_character_count_boundary_exact_max():
    """Exact 1,048,576 character string should succeed."""
    max_len = 1_048_576
    sample = "A" * max_len
    result = extract_pasted_text(sample)

    assert result.character_count == max_len
    assert len(result.extracted_content) == max_len


def test_character_limit_exceeded():
    """Text exceeding 1,048,576 characters must raise ContentSizeExceededError."""
    oversized = "A" * (1_048_576 + 1)
    with pytest.raises(ContentSizeExceededError) as exc_info:
        extract_pasted_text(oversized)

    assert exc_info.value.status_code == 413
    assert "exceeds maximum allowable limit" in exc_info.value.message.lower()


def test_utf8_byte_limit_exceeded_with_multibyte_unicode():
    """Multibyte Unicode exceeding UTF-8 byte limit must raise ContentSizeExceededError even if char count is lower."""
    # Each '🚀' emoji is 4 UTF-8 bytes and 1 Python character.
    # 300,000 emojis = 300,000 characters (well below 1,048,576 char limit),
    # but 300,000 * 4 = 1,200,000 bytes (exceeds 1,048,576 byte limit).
    emojis = "🚀" * 300_000
    assert len(emojis) < 1_048_576
    assert len(emojis.encode("utf-8")) > 1_048_576

    with pytest.raises(ContentSizeExceededError) as exc_info:
        extract_pasted_text(emojis)

    assert exc_info.value.status_code == 413
    assert "exceeds maximum allowable limit" in exc_info.value.message.lower()


def test_async_await_compatibility():
    """PastedTextExtractionResult must be awaitable for seamless async caller interoperability."""
    async def run_async():
        return await extract_pasted_text("Async compatible content for testing.")

    import anyio
    result = anyio.run(run_async)
    assert result.extracted_content == "Async compatible content for testing."
    assert result.source_type == "pasted_text"


# ---------------------------------------------------------------------------
# Schema Validation Tests (PastedTextExtractRequest)
# ---------------------------------------------------------------------------


def test_pasted_text_request_schema_valid():
    """Valid request schema should instantiate without error."""
    req = PastedTextExtractRequest(text="Valid text payload", title="Optional Title")
    assert req.text == "Valid text payload"
    assert req.title == "Optional Title"


def test_pasted_text_request_schema_forbids_extra_fields():
    """Extra unexpected fields in the request body must be rejected."""
    with pytest.raises(ValidationError):
        PastedTextExtractRequest(text="Valid text", extra_field="forbidden")


def test_pasted_text_request_schema_rejects_empty():
    """Empty or whitespace-only text must be rejected at schema validation time."""
    with pytest.raises(ValidationError):
        PastedTextExtractRequest(text="")

    with pytest.raises(ValidationError):
        PastedTextExtractRequest(text="   \n\t  ")


def test_pasted_text_request_schema_rejects_whitespace_title():
    """Whitespace-only title must be rejected by schema validator."""
    with pytest.raises(ValidationError):
        PastedTextExtractRequest(text="Valid text", title="   ")
