"""
SQLAlchemy engine, session factory, and FastAPI dependency for database access.
"""

from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Engine & Session factory
# ---------------------------------------------------------------------------

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,          # verify connections before checkout
    pool_size=5,
    max_overflow=10,
    echo=(settings.APP_ENV == "development"),  # SQL echo only in dev
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ---------------------------------------------------------------------------
# Declarative base (shared by all ORM models)
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ---------------------------------------------------------------------------
# Table initialisation
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables that haven't been created yet.

    Called once at application startup from main.py.
    """
    # Import models here so their metadata is registered with Base before
    # create_all is called.
    from app.models import document  # noqa: F401

    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified / created successfully.")
    except Exception as exc:
        logger.error("Failed to initialise database tables: %s", exc)
        raise


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """Yield a database session and ensure it is closed after the request."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
