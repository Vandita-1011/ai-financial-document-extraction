"""
Pydantic schemas for document request/response payloads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# File validation (Section 4.1)
# ---------------------------------------------------------------------------

class FileValidation(BaseModel):
    """Exact shape of the ``file_validation`` block in the case study response.

    Section 4.1 — produced by document_validation_service and embedded in the
    full mandatory response (Section 5.2).
    """

    file_type: str
    """MIME type of the uploaded file as determined from its bytes."""

    is_supported: bool
    """True when the file is application/pdf, image/jpeg, or image/png."""

    is_readable: bool
    """True when the file could be opened and parsed without errors."""

    page_count: int
    """Number of pages (0 when unreadable, always 1 for images)."""

    status: Literal["PASS", "FAILED"]
    """PASS only when is_supported, is_readable, and page_count ≤ MAX_UPLOAD_PAGES."""


# ---------------------------------------------------------------------------
# Error envelope (Section 5.3)
# ---------------------------------------------------------------------------

class ValidationErrorDetail(BaseModel):
    """Inner ``error`` object returned when file validation fails."""

    code: str
    """Machine-readable error code.

    Fixed set:
      UNSUPPORTED_FILE_TYPE  – MIME type not in PDF / JPG / PNG
      EMPTY_FILE             – zero-byte upload
      UNREADABLE_FILE        – file cannot be opened / is corrupted
      PAGE_LIMIT_EXCEEDED    – page count exceeds MAX_UPLOAD_PAGES
    """

    message: str
    """Human-readable explanation suitable for display to the end user."""


class ValidationErrorResponse(BaseModel):
    """Top-level Section 5.3 error envelope returned by the route layer."""

    error: ValidationErrorDetail


# ---------------------------------------------------------------------------
# Document record response (populated in later tasks)
# ---------------------------------------------------------------------------

class DocumentResponse(BaseModel):
    """Response schema for a persisted processed-document record."""

    id: int
    document_name: str
    document_type: str | None
    processing_status: str
    result_json: dict[str, Any] | None
    processed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
