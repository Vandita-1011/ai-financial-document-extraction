"""
Unit tests for document_validation_service.validate_document().

These tests do NOT require a running database or the full FastAPI app.
They patch settings.MAX_UPLOAD_PAGES so the test suite is self-contained.

Run from backend/:
    pytest tests/test_validation.py -v
"""

from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Bootstrap minimal environment variables so config.py doesn't sys.exit()
# before a single test runs.
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used-in-validation")

from app.services.document_validation_service import (  # noqa: E402
    validate_document,
    ERROR_EMPTY_FILE,
    ERROR_PAGE_LIMIT,
    ERROR_UNREADABLE,
    ERROR_UNSUPPORTED_TYPE,
)


# ---------------------------------------------------------------------------
# Helpers — minimal in-memory file factories
# ---------------------------------------------------------------------------

def _make_pdf(num_pages: int = 1) -> bytes:
    """Return bytes of a minimal valid PDF with *num_pages* blank pages."""
    import fitz

    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_png(width: int = 10, height: int = 10) -> bytes:
    """Return bytes of a minimal valid PNG image."""
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_jpeg(width: int = 10, height: int = 10) -> bytes:
    """Return bytes of a minimal valid JPEG image."""
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(0, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestValidateDocumentPDF(unittest.TestCase):

    def test_valid_single_page_pdf_passes(self):
        pdf = _make_pdf(num_pages=1)
        result = validate_document(pdf, "invoice.pdf", "application/pdf")

        self.assertEqual(result["file_type"], "application/pdf")
        self.assertTrue(result["is_supported"])
        self.assertTrue(result["is_readable"])
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(result["status"], "PASS")
        self.assertIsNone(result["error_code"])
        self.assertIsNone(result["error_message"])

    def test_valid_multi_page_pdf_within_limit_passes(self):
        pdf = _make_pdf(num_pages=3)
        with patch("app.services.document_validation_service.settings") as mock_cfg:
            mock_cfg.MAX_UPLOAD_PAGES = 3
            result = validate_document(pdf, "report.pdf", "application/pdf")

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["page_count"], 3)

    def test_pdf_exceeding_page_limit_fails(self):
        pdf = _make_pdf(num_pages=4)
        with patch("app.services.document_validation_service.settings") as mock_cfg:
            mock_cfg.MAX_UPLOAD_PAGES = 3
            result = validate_document(pdf, "long.pdf", "application/pdf")

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error_code"], ERROR_PAGE_LIMIT)
        self.assertEqual(result["page_count"], 4)
        self.assertTrue(result["is_readable"])   # readable but too long
        self.assertTrue(result["is_supported"])

    def test_empty_pdf_bytes_fails_with_empty_file(self):
        result = validate_document(b"", "empty.pdf", "application/pdf")

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error_code"], ERROR_EMPTY_FILE)
        self.assertFalse(result["is_readable"])

    def test_corrupted_pdf_bytes_fails_with_unreadable(self):
        # Starts with %PDF magic but is otherwise garbage
        bad_bytes = b"%PDF-1.4 this is not a real pdf \x00\xff\xfe"
        result = validate_document(bad_bytes, "corrupt.pdf", "application/pdf")

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error_code"], ERROR_UNREADABLE)
        self.assertFalse(result["is_readable"])
        self.assertTrue(result["is_supported"])


class TestValidateDocumentImage(unittest.TestCase):

    def test_valid_png_passes(self):
        png = _make_png()
        result = validate_document(png, "photo.png", "image/png")

        self.assertEqual(result["file_type"], "image/png")
        self.assertTrue(result["is_supported"])
        self.assertTrue(result["is_readable"])
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(result["status"], "PASS")
        self.assertIsNone(result["error_code"])

    def test_valid_jpeg_passes(self):
        jpg = _make_jpeg()
        result = validate_document(jpg, "scan.jpg", "image/jpeg")

        self.assertEqual(result["file_type"], "image/jpeg")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["page_count"], 1)

    def test_corrupted_png_bytes_fails_with_unreadable(self):
        # PNG magic header followed by random garbage
        bad_bytes = b"\x89PNG\r\n\x1a\n" + b"\xde\xad\xbe\xef" * 20
        result = validate_document(bad_bytes, "bad.png", "image/png")

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error_code"], ERROR_UNREADABLE)
        self.assertFalse(result["is_readable"])

    def test_empty_image_bytes_fails_with_empty_file(self):
        result = validate_document(b"", "empty.png", "image/png")

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error_code"], ERROR_EMPTY_FILE)

    def test_image_page_count_is_always_1(self):
        png = _make_png()
        result = validate_document(png, "img.png", "image/png")
        self.assertEqual(result["page_count"], 1)


class TestValidateDocumentUnsupportedTypes(unittest.TestCase):

    def test_docx_content_type_fails(self):
        result = validate_document(
            b"PK\x03\x04fake docx content",
            "document.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error_code"], ERROR_UNSUPPORTED_TYPE)
        self.assertFalse(result["is_supported"])

    def test_plain_text_fails(self):
        result = validate_document(b"hello world", "notes.txt", "text/plain")
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error_code"], ERROR_UNSUPPORTED_TYPE)

    def test_csv_fails(self):
        result = validate_document(b"col1,col2\n1,2\n", "data.csv", "text/csv")
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error_code"], ERROR_UNSUPPORTED_TYPE)


class TestMagicByteDetection(unittest.TestCase):
    """
    The service must trust actual file bytes over the filename / content_type
    header — e.g. a DOCX file renamed to .pdf must still fail.
    """

    def test_docx_bytes_reported_as_pdf_content_type_fails(self):
        # PK\x03\x04 is the ZIP/DOCX/XLSX magic — not a real PDF
        docx_bytes = b"PK\x03\x04" + b"\x00" * 100
        result = validate_document(docx_bytes, "invoice.pdf", "application/pdf")

        # Sniffed as non-PDF — must fail with UNSUPPORTED_FILE_TYPE
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error_code"], ERROR_UNSUPPORTED_TYPE)

    def test_valid_pdf_bytes_with_wrong_content_type_passes(self):
        # A genuine PDF accidentally labelled as octet-stream still passes
        pdf = _make_pdf(num_pages=1)
        result = validate_document(pdf, "upload", "application/octet-stream")

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["file_type"], "application/pdf")

    def test_valid_png_bytes_with_wrong_content_type_passes(self):
        png = _make_png()
        result = validate_document(png, "upload", "application/octet-stream")

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["file_type"], "image/png")


class TestResultShape(unittest.TestCase):
    """Ensure every result dict contains exactly the Section 4.1 mandatory keys."""

    REQUIRED_KEYS = {"file_type", "is_supported", "is_readable", "page_count", "status"}

    def _assert_has_required_keys(self, result: dict) -> None:
        for key in self.REQUIRED_KEYS:
            self.assertIn(key, result, f"Missing required key: {key!r}")

    def test_pass_result_has_required_keys(self):
        pdf = _make_pdf()
        result = validate_document(pdf, "a.pdf", "application/pdf")
        self._assert_has_required_keys(result)

    def test_failed_result_has_required_keys(self):
        result = validate_document(b"", "a.pdf", "application/pdf")
        self._assert_has_required_keys(result)

    def test_status_is_string_not_bool(self):
        pdf = _make_pdf()
        result = validate_document(pdf, "a.pdf", "application/pdf")
        self.assertIsInstance(result["status"], str)

    def test_page_count_is_int(self):
        pdf = _make_pdf(2)
        result = validate_document(pdf, "a.pdf", "application/pdf")
        self.assertIsInstance(result["page_count"], int)


if __name__ == "__main__":
    unittest.main()
