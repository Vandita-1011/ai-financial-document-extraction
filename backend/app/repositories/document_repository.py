"""
Document Repository for ProcessedDocument CRUD operations.
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.models.document import ProcessedDocument


def save_document(
    db: Session,
    document_name: str,
    document_type: str,
    processing_status: str,
    result_json: dict,
) -> ProcessedDocument:
    """Create and commit a new ProcessedDocument row.
    
    result_json holds the entire assembled response.
    processed_at is set to current UTC time.
    """
    now = datetime.now(timezone.utc)
    doc = ProcessedDocument(
        document_name=document_name,
        document_type=document_type,
        processing_status=processing_status,
        result_json=result_json,
        file_validation=result_json.get("file_validation") if isinstance(result_json, dict) else None,
        extracted_data=result_json.get("extracted_data") if isinstance(result_json, dict) else None,
        validation=result_json.get("validation") if isinstance(result_json, dict) else None,
        processing_metadata=result_json.get("processing_metadata") if isinstance(result_json, dict) else None,
        processed_at=now,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def get_by_name(db: Session, document_name: str) -> Optional[ProcessedDocument]:
    """Return the most recent ProcessedDocument for the given document_name, or None."""
    stmt = (
        select(ProcessedDocument)
        .where(ProcessedDocument.document_name == document_name)
        .order_by(desc(ProcessedDocument.id))
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_all(db: Session) -> List[ProcessedDocument]:
    """Return all processed documents ordered by ID descending."""
    stmt = select(ProcessedDocument).order_by(desc(ProcessedDocument.id))
    return list(db.execute(stmt).scalars().all())
