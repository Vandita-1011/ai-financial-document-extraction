"""
Unit tests for ocr_service.extract_text() and extraction_service functions.
"""

from __future__ import annotations

import io
import json
import os
import unittest
from pathlib import Path

import pytest

# ── Minimal env stub so config.py doesn't sys.exit() ─────────────────────────
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used-in-ocr")

from app.services.ocr_service import extract_text  # noqa: E402
from app.services.extraction_service import (
    extract_invoice_fields,
    extract_balance_sheet_fields,
    extract_pl_fields,
    extract_cash_flow_fields,
    ExtractionError,
)
from app.schemas.extraction import (
    ExtractionResult,
    BalanceSheetExtractionResult,
    PLExtractionResult,
    CashFlowExtractionResult,
)


# ── Fixture builders (pure Python, no files on disk) ─────────────────────────

def _native_pdf(text: str = "Invoice Total 1234") -> bytes:
    """Minimal PDF with real selectable text."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), text, fontsize=14)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _image_png(text: str = "Invoice Total 1234", width: int = 500, height: int = 80) -> bytes:
    """PNG containing rendered text — simulates a scanned image."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    draw.text((10, 20), text, fill=(0, 0, 0), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _image_jpeg(text: str = "Invoice Total 1234") -> bytes:
    """JPEG version of the same rendered text image."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (500, 80), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    draw.text((10, 20), text, fill=(0, 0, 0), font=font)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _image_only_pdf(png_bytes: bytes) -> bytes:
    """PDF whose only page content is an embedded image (no text layer)."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    rect = fitz.Rect(72, 72, 523, 200)
    page.insert_image(rect, stream=png_bytes)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _multi_page_pdf(text: str, png_bytes: bytes) -> bytes:
    """2-page PDF: page 1 has native text, page 2 is image-only."""
    import fitz
    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 72), text, fontsize=14)
    p2 = doc.new_page(width=595, height=842)
    p2.insert_image(fitz.Rect(72, 72, 523, 200), stream=png_bytes)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _blank_pdf() -> bytes:
    """PDF with a page that has no text and no image (blank)."""
    import fitz
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


# ── Skip guard ────────────────────────────────────────────────────────────────

def _easyocr_available() -> bool:
    try:
        import easyocr  # noqa: F401
        return True
    except ImportError:
        return False


SKIP_IF_NO_EASYOCR = pytest.mark.skipif(
    not _easyocr_available(),
    reason="EasyOCR package is not installed."
)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestNativePDF(unittest.TestCase):
    """PDF with real selectable text — must NOT invoke OCR."""

    def test_ocr_used_is_false(self):
        result = extract_text(_native_pdf(), "application/pdf")
        self.assertFalse(result["ocr_used"],
                         "Native-text PDF should NOT use OCR")

    def test_single_page_returned(self):
        result = extract_text(_native_pdf(), "application/pdf")
        self.assertEqual(len(result["pages"]), 1)

    def test_page_number_is_1(self):
        result = extract_text(_native_pdf(), "application/pdf")
        self.assertEqual(result["pages"][0]["page_number"], 1)

    def test_page_ocr_used_false(self):
        result = extract_text(_native_pdf(), "application/pdf")
        self.assertFalse(result["pages"][0]["ocr_used"])

    def test_text_contains_content(self):
        result = extract_text(_native_pdf("Hello World"), "application/pdf")
        self.assertIn("Hello World", result["pages"][0]["text"])


@SKIP_IF_NO_EASYOCR
class TestScannedPNG(unittest.TestCase):
    """PNG image — always uses EasyOCR."""

    def test_ocr_used_is_true(self):
        result = extract_text(_image_png(), "image/png")
        self.assertTrue(result["ocr_used"])

    def test_single_page_returned(self):
        result = extract_text(_image_png(), "image/png")
        self.assertEqual(len(result["pages"]), 1)

    def test_page_ocr_used_true(self):
        result = extract_text(_image_png(), "image/png")
        self.assertTrue(result["pages"][0]["ocr_used"])

    def test_page_number_is_1(self):
        result = extract_text(_image_png(), "image/png")
        self.assertEqual(result["pages"][0]["page_number"], 1)

    def test_text_field_is_string(self):
        result = extract_text(_image_png(), "image/png")
        self.assertIsInstance(result["pages"][0]["text"], str)


@SKIP_IF_NO_EASYOCR
class TestScannedJPEG(unittest.TestCase):
    """JPEG image — always uses EasyOCR."""

    def test_ocr_used_is_true(self):
        result = extract_text(_image_jpeg(), "image/jpeg")
        self.assertTrue(result["ocr_used"])

    def test_single_page_returned(self):
        result = extract_text(_image_jpeg(), "image/jpeg")
        self.assertEqual(len(result["pages"]), 1)


@SKIP_IF_NO_EASYOCR
class TestScannedPDF(unittest.TestCase):
    """PDF whose page has only an embedded image — should fall back to OCR."""

    def setUp(self):
        png = _image_png()
        self.result = extract_text(_image_only_pdf(png), "application/pdf")

    def test_ocr_used_is_true(self):
        self.assertTrue(self.result["ocr_used"],
                        "Image-only PDF page must trigger OCR fallback")

    def test_page_ocr_used_true(self):
        self.assertTrue(self.result["pages"][0]["ocr_used"])

    def test_single_page_returned(self):
        self.assertEqual(len(self.result["pages"]), 1)

    def test_text_is_string(self):
        self.assertIsInstance(self.result["pages"][0]["text"], str)


@SKIP_IF_NO_EASYOCR
class TestMultiPagePDF(unittest.TestCase):
    """2-page PDF: p1 native text, p2 image-only."""

    def setUp(self):
        png = _image_png()
        pdf = _multi_page_pdf("Selectable text on page one", png)
        self.result = extract_text(pdf, "application/pdf")

    def test_two_pages_returned(self):
        self.assertEqual(len(self.result["pages"]), 2)

    def test_page1_native_no_ocr(self):
        self.assertFalse(self.result["pages"][0]["ocr_used"],
                         "Page 1 has native text — should NOT use OCR")

    def test_page2_image_uses_ocr(self):
        self.assertTrue(self.result["pages"][1]["ocr_used"],
                        "Page 2 is image-only — must use OCR")

    def test_toplevel_ocr_used_true(self):
        self.assertTrue(self.result["ocr_used"],
                        "At least one page used OCR → top-level flag must be True")

    def test_page1_has_text(self):
        self.assertIn("page one", self.result["pages"][0]["text"].lower())

    def test_page_numbers_correct(self):
        self.assertEqual(self.result["pages"][0]["page_number"], 1)
        self.assertEqual(self.result["pages"][1]["page_number"], 2)


class TestBlankPDF(unittest.TestCase):
    """Blank page (no text, no image) — OCR fallback returns empty string gracefully."""

    def test_does_not_raise(self):
        result = extract_text(_blank_pdf(), "application/pdf")
        self.assertEqual(len(result["pages"]), 1)
        self.assertIsInstance(result["pages"][0]["text"], str)


class TestResultShape(unittest.TestCase):
    """Verify the top-level dict always has the correct keys and types."""

    def _result(self):
        return extract_text(_native_pdf(), "application/pdf")

    def test_has_pages_key(self):
        self.assertIn("pages", self._result())

    def test_has_ocr_used_key(self):
        self.assertIn("ocr_used", self._result())

    def test_ocr_used_is_bool(self):
        self.assertIsInstance(self._result()["ocr_used"], bool)

    def test_pages_is_list(self):
        self.assertIsInstance(self._result()["pages"], list)

    def test_page_entry_has_required_keys(self):
        page = self._result()["pages"][0]
        for key in ("page_number", "text", "ocr_used"):
            self.assertIn(key, page, f"Missing key {key!r} in page entry")

    def test_page_number_is_int(self):
        page = self._result()["pages"][0]
        self.assertIsInstance(page["page_number"], int)

    def test_page_text_is_str(self):
        page = self._result()["pages"][0]
        self.assertIsInstance(page["text"], str)

    def test_page_ocr_used_is_bool(self):
        page = self._result()["pages"][0]
        self.assertIsInstance(page["ocr_used"], bool)


# ── AI Extraction Service Tests ───────────────────────────────────────────────

from unittest.mock import MagicMock, patch


class TestInvoiceAIExtraction(unittest.TestCase):
    """Unit tests for extract_invoice_fields()."""

    def test_empty_ocr_text_returns_empty_result(self):
        result = extract_invoice_fields("")
        self.assertIsInstance(result, ExtractionResult)
        self.assertEqual(result.document_type, "invoice")
        self.assertIsNone(result.extracted_data.invoice_number)
        self.assertEqual(len(result.line_items), 0)

    def test_extract_invoice_fields_parsing(self):
        mock_response_json = json.dumps({
            "document_type": "invoice",
            "extracted_data": {
                "invoice_number": "INV-2026-001",
                "invoice_date": "2026-01-15",
                "vendor_name": "Acme Solutions Inc",
                "customer_name": "Global Tech Corp",
                "currency": "USD",
                "subtotal": 1000.0,
                "tax_amount": 100.0,
                "discount": None,
                "total_amount": 1100.0,
                "additional_fields": {"po_number": "PO-98765"}
            },
            "line_items": [
                {
                    "description": "Cloud Hosting Service",
                    "quantity": 1.0,
                    "unit_price": 1000.0,
                    "line_total": 1000.0
                }
            ],
            "evidence": {
                "invoice_number": {"source_text": "INVOICE #: INV-2026-001", "page_number": 1},
                "total_amount": {"source_text": "TOTAL: $1,100.00", "page_number": 1}
            }
        })

        with patch("app.services.extraction_service._call_groq", return_value=mock_response_json):
            page_texts = [{"page_number": 1, "text": "INVOICE #: INV-2026-001 TOTAL: $1,100.00", "ocr_used": False}]
            result = extract_invoice_fields(page_texts=page_texts)

            self.assertIsInstance(result, ExtractionResult)
            self.assertEqual(result.extracted_data.invoice_number, "INV-2026-001")
            self.assertEqual(result.extracted_data.vendor_name, "Acme Solutions Inc")
            self.assertEqual(result.extracted_data.total_amount, 1100.0)
            self.assertEqual(result.extracted_data.additional_fields.get("po_number"), "PO-98765")
            self.assertEqual(len(result.line_items), 1)
            self.assertEqual(result.line_items[0].description, "Cloud Hosting Service")
            self.assertEqual(result.evidence["invoice_number"].page_number, 1)

    def test_malformed_json_raises_extraction_error(self):
        with patch("app.services.extraction_service._call_groq", return_value="Invalid non-json response"):
            with self.assertRaises(ExtractionError):
                extract_invoice_fields(ocr_text="Some invoice text")


class TestBalanceSheetAIExtraction(unittest.TestCase):
    """Unit tests for extract_balance_sheet_fields()."""

    def test_empty_ocr_text_returns_empty_result(self):
        result = extract_balance_sheet_fields("")
        self.assertIsInstance(result, BalanceSheetExtractionResult)
        self.assertEqual(result.document_type, "balance_sheet")
        self.assertIsNone(result.extracted_data.total_assets)

    def test_extract_balance_sheet_fields_parsing(self):
        mock_json = json.dumps({
            "document_type": "balance_sheet",
            "extracted_data": {
                "company_name": "Sample Corp",
                "as_at_date": "2026-12-31",
                "currency": "USD",
                "total_assets": 500000.0,
                "total_liabilities": 200000.0,
                "total_equity": 300000.0,
                "total_capital_and_liabilities": 500000.0,
                "additional_fields": {}
            },
            "asset_items": [{"category": "Current", "name": "Cash", "amount": 100000.0}],
            "liability_items": [{"category": "Current", "name": "Accounts Payable", "amount": 50000.0}],
            "evidence": {
                "total_assets": {"source_text": "Total Assets: 500,000", "page_number": 1}
            }
        })
        with patch("app.services.extraction_service._call_groq", return_value=mock_json):
            res = extract_balance_sheet_fields("Balance Sheet text")
            self.assertIsInstance(res, BalanceSheetExtractionResult)
            self.assertEqual(res.extracted_data.total_assets, 500000.0)
            self.assertEqual(res.extracted_data.total_capital_and_liabilities, 500000.0)
            self.assertEqual(len(res.asset_items), 1)


class TestPLAIExtraction(unittest.TestCase):
    """Unit tests for extract_pl_fields()."""

    def test_empty_ocr_text_returns_empty_result(self):
        result = extract_pl_fields("")
        self.assertIsInstance(result, PLExtractionResult)
        self.assertEqual(result.document_type, "profit_and_loss")
        self.assertIsNone(result.extracted_data.total_income)

    def test_extract_pl_fields_parsing(self):
        mock_json = json.dumps({
            "document_type": "profit_and_loss",
            "extracted_data": {
                "company_name": "Sample Corp",
                "period": "FY 2026",
                "currency": "USD",
                "revenue": 1000000.0,
                "interest_earned": 5000.0,
                "other_income": 15000.0,
                "total_income": 20000.0,
                "additional_fields": {}
            },
            "line_items": [{"category": "Income", "description": "Interest", "amount": 5000.0}],
            "evidence": {}
        })
        with patch("app.services.extraction_service._call_groq", return_value=mock_json):
            res = extract_pl_fields("P&L text")
            self.assertIsInstance(res, PLExtractionResult)
            self.assertEqual(res.extracted_data.revenue, 1000000.0)
            self.assertEqual(res.extracted_data.total_income, 20000.0)


class TestCashFlowAIExtraction(unittest.TestCase):
    """Unit tests for extract_cash_flow_fields()."""

    def test_empty_ocr_text_returns_empty_result(self):
        result = extract_cash_flow_fields("")
        self.assertIsInstance(result, CashFlowExtractionResult)
        self.assertEqual(result.document_type, "cash_flow_statement")
        self.assertIsNone(result.extracted_data.net_change_in_cash)

    def test_extract_cash_flow_fields_parsing(self):
        mock_json = json.dumps({
            "document_type": "cash_flow_statement",
            "extracted_data": {
                "company_name": "Sample Corp",
                "period": "FY 2026",
                "currency": "USD",
                "operating_cash_flow": 120000.0,
                "investing_cash_flow": -40000.0,
                "financing_cash_flow": -10000.0,
                "fx_translation_adjustment": 0.0,
                "net_change_in_cash": 70000.0,
                "opening_cash": 30000.0,
                "closing_cash": 100000.0,
                "additional_fields": {}
            },
            "line_items": [],
            "evidence": {}
        })
        with patch("app.services.extraction_service._call_groq", return_value=mock_json):
            res = extract_cash_flow_fields("Cash Flow text")
            self.assertIsInstance(res, CashFlowExtractionResult)
            self.assertEqual(res.extracted_data.operating_cash_flow, 120000.0)
            self.assertEqual(res.extracted_data.investing_cash_flow, -40000.0)
            self.assertEqual(res.extracted_data.closing_cash, 100000.0)


if __name__ == "__main__":
    unittest.main()
