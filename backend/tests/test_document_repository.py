"""
Integration tests for DocumentRepository against the real hosted database.
"""

import uuid
import pytest
from app.core.database import SessionLocal
from app.repositories import document_repository
from app.models.document import ProcessedDocument


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_save_get_by_name_and_get_all(db):
    unique_id = str(uuid.uuid4())[:8]
    test_doc_name = f"test_invoice_{unique_id}.pdf"
    test_type = "application/pdf"
    test_status = "completed"
    test_result_json = {
        "file_validation": {"status": "PASS"},
        "extracted_data": {"invoice_number": f"INV-{unique_id}"},
        "validation": {"overall_status": "PASS"},
    }

    created_doc = None
    try:
        # 1. Test save_document
        created_doc = document_repository.save_document(
            db=db,
            document_name=test_doc_name,
            document_type=test_type,
            processing_status=test_status,
            result_json=test_result_json,
        )

        assert created_doc.id is not None
        assert created_doc.document_name == test_doc_name
        assert created_doc.document_type == test_type
        assert created_doc.processing_status == test_status
        assert created_doc.result_json == test_result_json
        assert created_doc.processed_at is not None

        # 2. Test get_by_name
        fetched_doc = document_repository.get_by_name(db=db, document_name=test_doc_name)
        assert fetched_doc is not None
        assert fetched_doc.id == created_doc.id
        assert fetched_doc.document_name == test_doc_name
        assert fetched_doc.result_json == test_result_json

        # 3. Test get_all
        all_docs = document_repository.get_all(db=db)
        assert isinstance(all_docs, list)
        assert len(all_docs) >= 1
        fetched_ids = [d.id for d in all_docs]
        assert created_doc.id in fetched_ids

    finally:
        # Cleanup test row
        if created_doc and created_doc.id:
            db.delete(created_doc)
            db.commit()
