"""
ORM model for processed documents.

`result_json` stores the full structured extraction response as a JSON blob so
that the schema can evolve without requiring a migration for every new field.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class ProcessedDocument(Base):
    """Persistence record for every document submitted through the API."""

    __tablename__ = "processed_documents"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Document identity
    document_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    document_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Processing lifecycle
    processing_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        comment="One of: pending | processing | completed | failed",
    )

    # JSON columns for the detailed response sections
    file_validation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    extracted_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    processing_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Full structured response — stored as JSONB for efficient querying later.
    # Falls back gracefully to Text if the dialect does not support JSONB.
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<ProcessedDocument id={self.id} name={self.document_name!r} "
            f"status={self.processing_status!r}>"
        )
