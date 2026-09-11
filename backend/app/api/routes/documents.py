"""
API routes for document processing, retrieval, and health.

POST /api/v1/documents/process – orchestrates validation, OCR, extraction, financial validation, and persistence.
GET  /api/v1/documents/{document_name} – retrieves a processed document by name.
GET  /api/v1/documents – lists all processed documents.
GET  /api/v1/health – lightweight health check.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.repositories.document_repository import (
    get_all as repo_get_all,
    get_by_name as repo_get_by_name,
    save_document as repo_save_document,
)
from app.services.document_validation_service import validate_document
from app.services.extraction_service import (
    ExtractionError,
    extract_balance_sheet_fields,
    extract_cash_flow_fields,
    extract_invoice_fields,
    extract_pl_fields,
)
from app.services.financial_validation_service import (
    validate_balance_sheet,
    validate_cash_flow,
    validate_invoice,
    validate_pl,
)
from app.services.ocr_service import extract_text

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1")

# Supported document type mapping
VALID_DOCUMENT_TYPES = {
    "invoice": "invoice",
    "balance_sheet": "balance_sheet",
    "profit_and_loss": "profit_and_loss",
    "p&l": "profit_and_loss",
    "cash_flow": "cash_flow_statement",
    "cash_flow_statement": "cash_flow_statement",
}


@router.get(
    "/health",
    summary="Service health check",
    response_description="Returns {status: ok} when the service is running.",
    tags=["health"],
)
async def health_check() -> JSONResponse:
    """Lightweight liveness probe."""
    return JSONResponse(content={"status": "ok"}, status_code=200)


@router.post(
    "/documents/process",
    summary="Process document upload",
    response_description="Returns validation, extraction, financial validation, and metadata.",
    tags=["documents"],
)
async def process_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Orchestrate file validation, OCR, AI extraction, financial validation, and persistence."""
    start_time = time.time()
    filename = file.filename or "uploaded_document"
    content_type = file.content_type or "application/octet-stream"

    logger.info(
        "Processing document upload: filename=%r, document_type=%r",
        filename,
        document_type,
    )

    # 1. Read file bytes
    try:
        file_bytes = await file.read()
    except Exception as exc:
        logger.error("Failed to read uploaded file bytes: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "FILE_READ_ERROR",
                    "message": f"Could not read uploaded file: {exc}",
                }
            },
        )

    # 2. File Validation
    validation_dict = validate_document(file_bytes, filename, content_type)

    if validation_dict.get("status") != "PASS" or validation_dict.get("error_code"):
        err_code = validation_dict.get("error_code") or "INVALID_DOCUMENT"
        err_msg = validation_dict.get("error_message") or "File validation failed."
        logger.warning(
            "Document validation failed for %r: code=%s, msg=%s",
            filename,
            err_code,
            err_msg,
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": {"code": err_code, "message": err_msg}},
        )

    # Clean file validation result for public output (Section 4.1)
    public_file_validation = {
        "file_type": validation_dict["file_type"],
        "is_supported": validation_dict["is_supported"],
        "is_readable": validation_dict["is_readable"],
        "page_count": validation_dict["page_count"],
        "status": validation_dict["status"],
    }

    # Normalize document_type
    normalized_doc_type = VALID_DOCUMENT_TYPES.get(document_type.lower().strip())
    if not normalized_doc_type:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "UNSUPPORTED_DOCUMENT_TYPE",
                    "message": (
                        f"Unsupported document_type '{document_type}'. Supported types: "
                        "invoice, balance_sheet, profit_and_loss, cash_flow."
                    ),
                }
            },
        )

    # 3. Pipeline execution (OCR -> Extract -> Financial Validate -> Persist)
    try:
        # OCR / Text extraction
        ocr_result = extract_text(file_bytes, public_file_validation["file_type"])
        page_texts = ocr_result.get("pages", [])
        ocr_used = ocr_result.get("ocr_used", False)

        # Dispatch extraction & financial validation
        if normalized_doc_type == "invoice":
            ext_res = extract_invoice_fields(page_texts=page_texts)
            extracted_dict = ext_res.model_dump()
            fin_val_dict = validate_invoice(extracted_dict.get("extracted_data", {}))
        elif normalized_doc_type == "balance_sheet":
            ext_res = extract_balance_sheet_fields(page_texts=page_texts)
            extracted_dict = ext_res.model_dump()
            fin_val_dict = validate_balance_sheet(extracted_dict.get("extracted_data", {}))
        elif normalized_doc_type == "profit_and_loss":
            ext_res = extract_pl_fields(page_texts=page_texts)
            extracted_dict = ext_res.model_dump()
            fin_val_dict = validate_pl(extracted_dict.get("extracted_data", {}))
        elif normalized_doc_type == "cash_flow_statement":
            ext_res = extract_cash_flow_fields(page_texts=page_texts)
            extracted_dict = ext_res.model_dump()
            fin_val_dict = validate_cash_flow(extracted_dict.get("extracted_data", {}))

        processing_time_ms = round((time.time() - start_time) * 1000, 2)

        # Assemble full Section 5.2 response
        full_response = {
            "document_name": filename,
            "document_type": normalized_doc_type,
            "file_validation": public_file_validation,
            "extracted_data": extracted_dict,
            "validation": fin_val_dict,
            "processing_status": "COMPLETED",
            "processing_metadata": {
                "processing_time_ms": processing_time_ms,
                "ocr_used": ocr_used,
                "pages_processed": public_file_validation["page_count"],
            },
        }

        # 4. Save to repository
        repo_save_document(
            db=db,
            document_name=filename,
            document_type=normalized_doc_type,
            processing_status="COMPLETED",
            result_json=full_response,
        )

        return JSONResponse(content=full_response, status_code=200)

    except ExtractionError as exc:
        logger.error("Extraction error processing %r: %s", filename, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"code": "EXTRACTION_FAILED", "message": str(exc)}},
        )
    except Exception as exc:
        logger.error("Unhandled error during document processing: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": f"An unexpected error occurred: {exc}",
                }
            },
        )


@router.get(
    "/documents/{document_name:path}",
    summary="Get processed document by name",
    tags=["documents"],
)
async def get_document_by_name(
    document_name: str,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Retrieve the most recent processed document payload by name."""
    doc = repo_get_by_name(db, document_name)
    if not doc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "DOCUMENT_NOT_FOUND",
                    "message": f"Document '{document_name}' not found.",
                }
            },
        )
    return JSONResponse(content=doc.result_json, status_code=200)


@router.get(
    "/documents",
    summary="List all processed documents",
    tags=["documents"],
)
async def list_documents(
    db: Session = Depends(get_db),
) -> JSONResponse:
    """List all processed documents."""
    docs = repo_get_all(db)
    items = [doc.result_json for doc in docs]
    return JSONResponse(content={"documents": items, "count": len(items)}, status_code=200)
