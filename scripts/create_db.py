"""Create database schema for eCFR analyzer."""

import os
import sys
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine

from app.models import Base


def create_tables(database_url: str) -> None:
    """Create all database tables.

    Args:
        database_url: PostgreSQL connection string
    """
    print("Connecting to database...")
    engine = create_engine(database_url, echo=False)

    print("Creating tables...")
    Base.metadata.create_all(engine)

    engine.dispose()
    print("Database schema created successfully!")


def main() -> None:
    """Main entry point for creating database schema."""
    # Get database URL from environment variable
    database_url = os.environ.get("ECFR_DATABASE_URL")
    if not database_url:
        msg = "ECFR_DATABASE_URL environment variable is required"
        raise ValueError(msg)

    create_tables(database_url)


if __name__ == "__main__":
    main()
