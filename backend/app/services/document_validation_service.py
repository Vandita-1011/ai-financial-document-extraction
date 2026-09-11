"""
Document input-validation service.

Validates an uploaded file *before* any OCR or AI extraction is attempted.
Checks (in order):
  1. Supported MIME type  (PDF / JPEG / PNG only)
  2. Non-empty content    (zero-byte upload)
  3. File readability     (PDF: PyMuPDF open; image: Pillow verify)
  4. Page-count limit     (≤ MAX_UPLOAD_PAGES from config; images always = 1)

Returns a dict that matches the case study's ``file_validation`` shape
(Section 4.1).  On failure, also carries ``error_code`` and ``error_message``
for the calling route to construct the Section 5.3 error response.
"""

from __future__ import annotations

import io
from typing import Literal

import fitz  # PyMuPDF
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Supported MIME types ────────────────────────────────────────────────────

SUPPORTED_TYPES: frozenset[str] = frozenset(
    {"application/pdf", "image/jpeg", "image/png"}
)

# ── Fixed error codes (one per failure mode, Section 5.3) ──────────────────

ERROR_UNSUPPORTED_TYPE = "UNSUPPORTED_FILE_TYPE"
ERROR_EMPTY_FILE = "EMPTY_FILE"
ERROR_UNREADABLE = "UNREADABLE_FILE"
ERROR_PAGE_LIMIT = "PAGE_LIMIT_EXCEEDED"


# ── Public API ──────────────────────────────────────────────────────────────

def validate_document(
    file_bytes: bytes,
    filename: str,
    content_type: str,
) -> dict:
    """Validate *file_bytes* and return a ``file_validation`` result dict.

    Parameters
    ----------
    file_bytes:
        Raw bytes of the uploaded file.
    filename:
        Original filename supplied by the client (used only for logging;
        validation trusts bytes over filename/extension).
    content_type:
        MIME type reported by the client.  We attempt to detect the true type
        from the bytes when the reported type is unsupported or ambiguous.

    Returns
    -------
    dict with keys:
        file_type       – effective MIME type (str)
        is_supported    – bool
        is_readable     – bool
        page_count      – int (0 when unreadable, 1 for images)
        status          – "PASS" | "FAILED"
        error_code      – str | None  (None on PASS)
        error_message   – str | None  (None on PASS)
    """
    logger.debug("Validating upload: filename=%r content_type=%r size=%d",
                 filename, content_type, len(file_bytes))

    # ── Step 1: Empty file check (must precede MIME sniffing) ──────────────
    # An empty upload has no magic bytes to sniff, so we check length first.
    if not file_bytes:
        return _result(
            file_type=content_type or "application/octet-stream",
            is_supported=False,
            is_readable=False,
            page_count=0,
            error_code=ERROR_EMPTY_FILE,
            error_message="The uploaded file is empty.",
        )

    # ── Step 2: Determine effective MIME type ───────────────────────────────
    # Trust content_type when it's already a known supported value; otherwise
    # sniff the bytes so a renamed / mis-labelled file is caught correctly.
    effective_type = _resolve_content_type(file_bytes, content_type)

    if effective_type not in SUPPORTED_TYPES:
        return _result(
            file_type=effective_type,
            is_supported=False,
            is_readable=False,
            page_count=0,
            error_code=ERROR_UNSUPPORTED_TYPE,
            error_message="Only PDF / JPG / PNG documents are supported.",
        )

    # ── Step 3 + 4: Readability & page count ───────────────────────────────
    if effective_type == "application/pdf":
        return _validate_pdf(file_bytes, effective_type)
    else:
        return _validate_image(file_bytes, effective_type)


# ── Internal helpers ────────────────────────────────────────────────────────

def _resolve_content_type(file_bytes: bytes, reported: str) -> str:
    """Return the true MIME type, sniffed from the file magic bytes.

    Magic bytes are authoritative:
    - If the sniffed type is a recognised supported type, use it.
    - If the sniffed type is *not* recognised (e.g. a DOCX disguised as a PDF),
      return the sniffed value so the UNSUPPORTED_FILE_TYPE path fires — even
      if the reported content_type claimed a supported format.
    - If both sniffed and reported are unknown, fall back to reported so the
      caller sees a meaningful type string in the error.
    """
    sniffed = _sniff_mime(file_bytes)

    # Sniffed is a supported type — authoritative, use it directly.
    if sniffed in SUPPORTED_TYPES:
        return sniffed

    # Sniffed is NOT a supported type.
    # If the reported type claimed a *supported* format but bytes disagree,
    # trust the bytes (return sniffed) so the file is rejected as unsupported
    # rather than falling through to a misleading UNREADABLE_FILE error.
    if reported in SUPPORTED_TYPES:
        return sniffed  # e.g. "application/octet-stream" — will fail type check

    # Both sniffed and reported are unknown — return reported for a cleaner
    # error message (preserves whatever the client sent).
    return reported if reported else "application/octet-stream"


def _sniff_mime(file_bytes: bytes) -> str:
    """Return a MIME type by inspecting the first few magic bytes."""
    if file_bytes[:4] == b"%PDF":
        return "application/pdf"
    if file_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    # Not a recognised type — return a generic value
    return "application/octet-stream"


def _validate_pdf(file_bytes: bytes, file_type: str) -> dict:
    """Attempt to open the PDF with PyMuPDF and check the page count."""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_count: int = doc.page_count
        doc.close()
    except Exception as exc:
        logger.debug("PDF readability check failed: %s", exc)
        return _result(
            file_type=file_type,
            is_supported=True,
            is_readable=False,
            page_count=0,
            error_code=ERROR_UNREADABLE,
            error_message="The PDF could not be opened. It may be corrupted.",
        )

    if page_count == 0:
        return _result(
            file_type=file_type,
            is_supported=True,
            is_readable=False,
            page_count=0,
            error_code=ERROR_UNREADABLE,
            error_message="The PDF contains no pages and cannot be processed.",
        )

    max_pages: int = settings.MAX_UPLOAD_PAGES
    if page_count > max_pages:
        return _result(
            file_type=file_type,
            is_supported=True,
            is_readable=True,
            page_count=page_count,
            error_code=ERROR_PAGE_LIMIT,
            error_message=(
                f"Document has {page_count} pages; "
                f"the maximum allowed is {max_pages}."
            ),
        )

    return _result(
        file_type=file_type,
        is_supported=True,
        is_readable=True,
        page_count=page_count,
    )


def _validate_image(file_bytes: bytes, file_type: str) -> dict:
    """Attempt to verify the image bytes with Pillow."""
    try:
        # Image.open is lazy; .verify() forces a full integrity check.
        # After verify() the file object is consumed, so we re-open to check
        # that at least one frame/page exists (always 1 for JPEG/PNG).
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
    except (UnidentifiedImageError, Exception) as exc:
        logger.debug("Image readability check failed: %s", exc)
        return _result(
            file_type=file_type,
            is_supported=True,
            is_readable=False,
            page_count=0,
            error_code=ERROR_UNREADABLE,
            error_message="The image file could not be opened. It may be corrupted.",
        )

    # Images are always a single page
    page_count = 1
    max_pages: int = settings.MAX_UPLOAD_PAGES

    # MAX_UPLOAD_PAGES could theoretically be set to 0 in config, guard anyway
    if page_count > max_pages:
        return _result(
            file_type=file_type,
            is_supported=True,
            is_readable=True,
            page_count=page_count,
            error_code=ERROR_PAGE_LIMIT,
            error_message=(
                f"Document has {page_count} page; "
                f"the maximum allowed is {max_pages}."
            ),
        )

    return _result(
        file_type=file_type,
        is_supported=True,
        is_readable=True,
        page_count=page_count,
    )


def _result(
    *,
    file_type: str,
    is_supported: bool,
    is_readable: bool,
    page_count: int,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict:
    """Build the canonical file_validation result dict."""
    passed = is_supported and is_readable and error_code is None
    status: Literal["PASS", "FAILED"] = "PASS" if passed else "FAILED"

    return {
        # ── Section 4.1 mandatory fields ──────────────────────────────────
        "file_type": file_type,
        "is_supported": is_supported,
        "is_readable": is_readable,
        "page_count": page_count,
        "status": status,
        # ── Internal fields for the route layer (Section 5.3) ─────────────
        # Not serialised into the public response — the route extracts these
        # to build the {"error": {"code": ..., "message": ...}} envelope.
        "error_code": error_code,
        "error_message": error_message,
    }
