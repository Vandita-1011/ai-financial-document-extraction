"""
OCR / text-extraction service.

Extracts text per page from a *pre-validated* document (PDF, JPEG, or PNG).

Strategy
--------
PDF pages
    1. Native text extraction via PyMuPDF ``page.get_text()``.
    2. If the native result is below a minimum character threshold (the page is
       likely scanned / image-only), render the page to a pixmap and run
       EasyOCR as a fallback.  ``ocr_used = True`` for that page.

JPEG / PNG
    Always run EasyOCR directly (single page, ``ocr_used = True``).

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

Note on EasyOCR
---------------
EasyOCR downloads its OCR model weights (~a few hundred MB) on first run.
The ``easyocr.Reader`` instance is lazy-initialized as a module singleton
to avoid the heavy initialization cost on every request.
"""

from __future__ import annotations

import io
from typing import TypedDict

import fitz  # PyMuPDF
import numpy as np
from PIL import Image

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Tuning constants ────────────────────────────────────────────────────────

# Pages whose native-extracted text is shorter than this threshold are treated
# as scanned/image-only and sent through EasyOCR instead.
_NATIVE_TEXT_MIN_CHARS: int = 10

# DPI used when rasterising a PDF page for OCR (higher = better quality,
# slower; 200 is a good balance for A4 / letter documents).
_OCR_RENDER_DPI: int = 200


# ── Lazy-initialized EasyOCR Singleton ───────────────────────────────────────

_EASYOCR_READER = None


def _get_ocr_reader():
    """Lazy-initialize and return the shared EasyOCR Reader instance."""
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        import easyocr
        logger.info("Initializing EasyOCR reader (one-time model load)...")
        _EASYOCR_READER = easyocr.Reader(["en"], gpu=False)
    return _EASYOCR_READER


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
            # Page appears to be scanned — render and run EasyOCR
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
    """Render *page* to a PIL image and run EasyOCR on it."""
    zoom = _OCR_RENDER_DPI / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)

    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return _run_ocr(img, page_num)


# ── Image extraction ──────────────────────────────────────────────────────────

def _extract_image(file_bytes: bytes) -> list[PageResult]:
    """Run EasyOCR on a JPEG or PNG image (always a single page)."""
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    text = _run_ocr(img, page_num=1)
    return [PageResult(page_number=1, text=text, ocr_used=True)]


# ── Shared EasyOCR helper ─────────────────────────────────────────────────────

def _run_ocr(img: Image.Image, page_num: int) -> str:
    """Run EasyOCR on *img* and return the cleaned text string.

    Never raises on empty scan — returns empty string and logs a warning so
    the caller can continue processing remaining pages.
    """
    try:
        reader = _get_ocr_reader()
        img_np = np.array(img)
        ocr_results = reader.readtext(img_np, detail=0, paragraph=True)
        text = " ".join(ocr_results).strip()
    except Exception as exc:
        logger.warning(
            "Page %d: EasyOCR failed (%s). Returning empty string.",
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
