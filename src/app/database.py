"""Database connection and session management."""

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def get_database_url() -> str:
    """Get database URL from environment variable.

    Returns:
        Database URL string

    Raises:
        ValueError: If ECFR_DATABASE_URL is not set
    """
    database_url = os.environ.get("ECFR_DATABASE_URL")
    if not database_url:
        msg = "ECFR_DATABASE_URL environment variable is required"
        raise ValueError(msg)
    return database_url


# Create engine
engine = create_engine(get_database_url(), echo=False)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session]:
    """FastAPI dependency for database sessions.

    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
