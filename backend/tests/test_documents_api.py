"""
API integration tests for backend/app/api/routes/documents.py.

Covers:
  - GET  /api/v1/health
  - POST /api/v1/documents/process  (all 4 document types + error paths)
  - GET  /api/v1/documents
  - GET  /api/v1/documents/{document_name}

All external I/O (Groq, OCR, DB) is mocked so these tests run without
real credentials or a live database.
"""
from __future__ import annotations

import io
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_mock_db() -> MagicMock:
    db = MagicMock()
    db.add.return_value = None
    db.commit.return_value = None
    db.refresh.return_value = None
    return db


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    mock_db = _make_mock_db()

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
    b"xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n"
    b"0000000058 00000 n\n0000000115 00000 n\n"
    b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF"
)

_OCR_RESULT = {
    "ocr_used": False,
    "pages": [{"page_number": 1, "text": "Invoice #001 Total: 100", "ocr_used": False}],
}

_BASE_VALIDATION_PASS = {
    "status": "PASS",
    "file_type": "pdf",
    "is_supported": True,
    "is_readable": True,
    "page_count": 1,
    "error_code": None,
    "error_message": None,
}

_FIN_VAL_PASS = {
    "overall_status": "PASS",
    "checks": [],
    "warnings": [],
}


def _make_doc_result(doc_type: str) -> MagicMock:
    mock = MagicMock()
    mock.result_json = {
        "document_name": f"test_{doc_type}.pdf",
        "document_type": doc_type,
        "processing_status": "COMPLETED",
    }
    return mock


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_returns_200(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200

    def test_returns_ok_status(self, client):
        r = client.get("/api/v1/health")
        assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /api/v1/documents/process happy paths
# ---------------------------------------------------------------------------

class TestProcessDocumentHappyPaths:

    def _post_document(self, client, doc_type):
        return client.post(
            "/api/v1/documents/process",
            files={"file": ("doc.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
            data={"document_type": doc_type},
        )

    @patch("app.api.routes.documents.repo_save_document")
    @patch("app.api.routes.documents.validate_invoice", return_value=_FIN_VAL_PASS)
    @patch("app.api.routes.documents.extract_invoice_fields")
    @patch("app.api.routes.documents.extract_text", return_value=_OCR_RESULT)
    @patch("app.api.routes.documents.validate_document", return_value=_BASE_VALIDATION_PASS)
    def test_invoice_returns_200(self, mv, mo, me, mf, ms, client):
        me.return_value.model_dump.return_value = {"document_type": "invoice", "extracted_data": {}}
        r = self._post_document(client, "invoice")
        assert r.status_code == 200

    @patch("app.api.routes.documents.repo_save_document")
    @patch("app.api.routes.documents.validate_invoice", return_value=_FIN_VAL_PASS)
    @patch("app.api.routes.documents.extract_invoice_fields")
    @patch("app.api.routes.documents.extract_text", return_value=_OCR_RESULT)
    @patch("app.api.routes.documents.validate_document", return_value=_BASE_VALIDATION_PASS)
    def test_invoice_response_has_required_keys(self, mv, mo, me, mf, ms, client):
        me.return_value.model_dump.return_value = {"document_type": "invoice", "extracted_data": {}}
        r = self._post_document(client, "invoice")
        body = r.json()
        for key in ("document_name", "document_type", "file_validation", "extracted_data", "validation", "processing_status", "processing_metadata"):
            assert key in body, f"Missing key: {key}"

    @patch("app.api.routes.documents.repo_save_document")
    @patch("app.api.routes.documents.validate_balance_sheet", return_value=_FIN_VAL_PASS)
    @patch("app.api.routes.documents.extract_balance_sheet_fields")
    @patch("app.api.routes.documents.extract_text", return_value=_OCR_RESULT)
    @patch("app.api.routes.documents.validate_document", return_value=_BASE_VALIDATION_PASS)
    def test_balance_sheet_returns_200(self, mv, mo, me, mf, ms, client):
        me.return_value.model_dump.return_value = {"document_type": "balance_sheet", "extracted_data": {}}
        r = self._post_document(client, "balance_sheet")
        assert r.status_code == 200

    @patch("app.api.routes.documents.repo_save_document")
    @patch("app.api.routes.documents.validate_pl", return_value=_FIN_VAL_PASS)
    @patch("app.api.routes.documents.extract_pl_fields")
    @patch("app.api.routes.documents.extract_text", return_value=_OCR_RESULT)
    @patch("app.api.routes.documents.validate_document", return_value=_BASE_VALIDATION_PASS)
    def test_profit_and_loss_returns_200(self, mv, mo, me, mf, ms, client):
        me.return_value.model_dump.return_value = {"document_type": "profit_and_loss", "extracted_data": {}}
        r = self._post_document(client, "profit_and_loss")
        assert r.status_code == 200

    @patch("app.api.routes.documents.repo_save_document")
    @patch("app.api.routes.documents.validate_cash_flow", return_value=_FIN_VAL_PASS)
    @patch("app.api.routes.documents.extract_cash_flow_fields")
    @patch("app.api.routes.documents.extract_text", return_value=_OCR_RESULT)
    @patch("app.api.routes.documents.validate_document", return_value=_BASE_VALIDATION_PASS)
    def test_cash_flow_returns_200(self, mv, mo, me, mf, ms, client):
        me.return_value.model_dump.return_value = {"document_type": "cash_flow_statement", "extracted_data": {}}
        r = self._post_document(client, "cash_flow")
        assert r.status_code == 200

    @patch("app.api.routes.documents.repo_save_document")
    @patch("app.api.routes.documents.validate_pl", return_value=_FIN_VAL_PASS)
    @patch("app.api.routes.documents.extract_pl_fields")
    @patch("app.api.routes.documents.extract_text", return_value=_OCR_RESULT)
    @patch("app.api.routes.documents.validate_document", return_value=_BASE_VALIDATION_PASS)
    def test_pl_alias_accepted(self, mv, mo, me, mf, ms, client):
        me.return_value.model_dump.return_value = {"document_type": "profit_and_loss", "extracted_data": {}}
        r = self._post_document(client, "p&l")
        assert r.status_code == 200
        assert r.json()["document_type"] == "profit_and_loss"

    @patch("app.api.routes.documents.repo_save_document")
    @patch("app.api.routes.documents.validate_cash_flow", return_value=_FIN_VAL_PASS)
    @patch("app.api.routes.documents.extract_cash_flow_fields")
    @patch("app.api.routes.documents.extract_text", return_value=_OCR_RESULT)
    @patch("app.api.routes.documents.validate_document", return_value=_BASE_VALIDATION_PASS)
    def test_processing_status_is_completed(self, mv, mo, me, mf, ms, client):
        me.return_value.model_dump.return_value = {"document_type": "cash_flow_statement", "extracted_data": {}}
        r = self._post_document(client, "cash_flow_statement")
        assert r.json()["processing_status"] == "COMPLETED"

    @patch("app.api.routes.documents.repo_save_document")
    @patch("app.api.routes.documents.validate_invoice", return_value=_FIN_VAL_PASS)
    @patch("app.api.routes.documents.extract_invoice_fields")
    @patch("app.api.routes.documents.extract_text", return_value=_OCR_RESULT)
    @patch("app.api.routes.documents.validate_document", return_value=_BASE_VALIDATION_PASS)
    def test_processing_metadata_has_processing_time_ms(self, mv, mo, me, mf, ms, client):
        me.return_value.model_dump.return_value = {"document_type": "invoice", "extracted_data": {}}
        r = self._post_document(client, "invoice")
        assert "processing_time_ms" in r.json()["processing_metadata"]


# ---------------------------------------------------------------------------
# POST /api/v1/documents/process error paths
# ---------------------------------------------------------------------------

class TestProcessDocumentErrorPaths:

    def _post(self, client, doc_type="invoice", file_bytes=_MINIMAL_PDF):
        return client.post(
            "/api/v1/documents/process",
            files={"file": ("doc.pdf", io.BytesIO(file_bytes), "application/pdf")},
            data={"document_type": doc_type},
        )

    @patch("app.api.routes.documents.validate_document")
    def test_file_validation_failure_returns_400(self, mock_val_doc, client):
        mock_val_doc.return_value = {
            "status": "FAIL",
            "file_type": "pdf",
            "is_supported": False,
            "is_readable": False,
            "page_count": 0,
            "error_code": "INVALID_FORMAT",
            "error_message": "File format not supported.",
        }
        r = self._post(client)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_FORMAT"

    @patch("app.api.routes.documents.validate_document", return_value=_BASE_VALIDATION_PASS)
    def test_unsupported_doc_type_returns_400(self, mv, client):
        r = self._post(client, doc_type="spreadsheet")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "UNSUPPORTED_DOCUMENT_TYPE"

    @patch("app.api.routes.documents.extract_invoice_fields", side_effect=Exception("Groq down"))
    @patch("app.api.routes.documents.extract_text", return_value=_OCR_RESULT)
    @patch("app.api.routes.documents.validate_document", return_value=_BASE_VALIDATION_PASS)
    def test_unhandled_exception_returns_500(self, mv, mo, me, client):
        r = self._post(client, doc_type="invoice")
        assert r.status_code == 500
        assert r.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"

    @patch("app.api.routes.documents.extract_invoice_fields")
    @patch("app.api.routes.documents.extract_text", return_value=_OCR_RESULT)
    @patch("app.api.routes.documents.validate_document", return_value=_BASE_VALIDATION_PASS)
    def test_extraction_error_returns_500(self, mv, mo, me, client):
        from app.services.extraction_service import ExtractionError
        me.side_effect = ExtractionError("Model unavailable")
        r = self._post(client, doc_type="invoice")
        assert r.status_code == 500
        assert r.json()["error"]["code"] == "EXTRACTION_FAILED"


# ---------------------------------------------------------------------------
# GET /api/v1/documents
# ---------------------------------------------------------------------------

class TestListDocuments:

    @patch("app.api.routes.documents.repo_get_all")
    def test_empty_db_returns_200_with_empty_list(self, mock_get_all, client):
        mock_get_all.return_value = []
        r = client.get("/api/v1/documents")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 0
        assert body["documents"] == []

    @patch("app.api.routes.documents.repo_get_all")
    def test_returns_all_documents(self, mock_get_all, client):
        mock_get_all.return_value = [_make_doc_result("invoice"), _make_doc_result("balance_sheet")]
        r = client.get("/api/v1/documents")
        body = r.json()
        assert body["count"] == 2
        assert len(body["documents"]) == 2


# ---------------------------------------------------------------------------
# GET /api/v1/documents/{document_name}
# ---------------------------------------------------------------------------

class TestGetDocumentByName:

    @patch("app.api.routes.documents.repo_get_by_name")
    def test_existing_document_returns_200(self, mock_get, client):
        mock_get.return_value = _make_doc_result("invoice")
        r = client.get("/api/v1/documents/my_invoice.pdf")
        assert r.status_code == 200

    @patch("app.api.routes.documents.repo_get_by_name", return_value=None)
    def test_missing_document_returns_404(self, mock_get, client):
        r = client.get("/api/v1/documents/ghost.pdf")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
