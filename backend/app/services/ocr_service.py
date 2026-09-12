"""
OCR / text-extraction service.

Extracts text per page from a *pre-validated* document (PDF, JPEG, or PNG).

Strategy
--------
PDF pages
    1. Native text extraction via PyMuPDF ``page.get_text()``.
    2. If the native result is below a minimum character threshold (the page is
       likely scanned / image-only), render the page to a pixmap and run
       Tesseract OCR as a fallback. ``ocr_used = True`` for that page.

JPEG / PNG
    Always run Tesseract OCR directly (single page, ``ocr_used = True``).

Return value
------------
A dict with two keys::

    {
        "pages": [
            {"page_number": 1, "text": "...", "ocr_used": False},
            ...
        ],
        "ocr_used": False   # True if ANY page used OCR
    }
"""

from __future__ import annotations

import io
from typing import TypedDict

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Tuning constants ────────────────────────────────────────────────────────

# Pages whose native-extracted text is shorter than this threshold are treated
# as scanned/image-only and sent through Tesseract OCR instead.
_NATIVE_TEXT_MIN_CHARS: int = 10

# DPI used when rasterising a PDF page for OCR (150 DPI balances text clarity
# for financial documents with minimal RAM footprint on memory-constrained hosts).
_OCR_RENDER_DPI: int = 150


# ── Public types ─────────────────────────────────────────────────────────────

class PageResult(TypedDict):
    page_number: int
    text: str
    ocr_used: bool


class ExtractionResult(TypedDict):
    pages: list[PageResult]
    ocr_used: bool


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text(file_bytes: bytes, file_type: str) -> ExtractionResult:
    """Extract text from *file_bytes*, dispatching by *file_type*.

    Parameters
    ----------
    file_bytes:
        Raw bytes of an already-validated document.
    file_type:
        Effective MIME type: ``"application/pdf"``, ``"image/jpeg"``, or
        ``"image/png"``.

    Returns
    -------
    ExtractionResult
        ``pages`` list (one entry per page) plus top-level ``ocr_used`` flag.
    """
    if file_type == "application/pdf":
        pages = _extract_pdf(file_bytes)
    else:
        # JPEG or PNG — always single page, always OCR
        pages = _extract_image(file_bytes)

    any_ocr = any(p["ocr_used"] for p in pages)
    logger.info(
        "Extraction complete: %d page(s), ocr_used=%s",
        len(pages),
        any_ocr,
    )
    return {"pages": pages, "ocr_used": any_ocr}


# ── PDF extraction ────────────────────────────────────────────────────────────

def _extract_pdf(file_bytes: bytes) -> list[PageResult]:
    """Extract text from every page of a PDF, falling back to OCR per page."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    results: list[PageResult] = []

    for page_index in range(doc.page_count):
        page_num = page_index + 1
        page = doc[page_index]

        native_text = page.get_text().strip()

        if len(native_text) >= _NATIVE_TEXT_MIN_CHARS:
            logger.debug("Page %d: native text extracted (%d chars).",
                         page_num, len(native_text))
            results.append(
                PageResult(page_number=page_num, text=native_text, ocr_used=False)
            )
        else:
            # Page appears to be scanned — render and run Tesseract OCR
            logger.debug(
                "Page %d: native text too short (%d chars) → falling back to OCR.",
                page_num,
                len(native_text),
            )
            ocr_text = _ocr_pdf_page(page, page_num)
            results.append(
                PageResult(page_number=page_num, text=ocr_text, ocr_used=True)
            )

    doc.close()
    return results


def _ocr_pdf_page(page: fitz.Page, page_num: int) -> str:
    """Render *page* to a PIL image and run Tesseract OCR on it."""
    zoom = _OCR_RENDER_DPI / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)

    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return _run_ocr(img, page_num)


# ── Image extraction ──────────────────────────────────────────────────────────

def _extract_image(file_bytes: bytes) -> list[PageResult]:
    """Run Tesseract OCR on a JPEG or PNG image (always a single page)."""
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    text = _run_ocr(img, page_num=1)
    return [PageResult(page_number=1, text=text, ocr_used=True)]


# ── Shared Tesseract OCR helper ───────────────────────────────────────────────

def _run_ocr(img: Image.Image, page_num: int) -> str:
    """Run Tesseract OCR on *img* and return the cleaned text string.

    Never raises on empty scan or Tesseract failure — returns empty string and logs
    a warning so the caller can continue processing remaining pages.
    """
    try:
        text = pytesseract.image_to_string(img, config="--oem 3 --psm 6").strip()
    except Exception as exc:
        logger.warning(
            "Page %d: Tesseract OCR failed (%s). Returning empty string.",
            page_num,
            exc,
        )
        return ""

    if not text:
        logger.warning(
            "Page %d: OCR produced empty output — the scan may be low quality "
            "or the page is blank.",
            page_num,
        )

    return text
