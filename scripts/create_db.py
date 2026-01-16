"""Create database schema for eCFR analyzer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine

from app.config import settings
from app.models import Base


def create_tables(database_url: str) -> None:
    """Create all database tables."""
    print("Connecting to database...")
    engine = create_engine(database_url, echo=False)

    print("Creating tables...")
    Base.metadata.create_all(engine)

    engine.dispose()
    print("Database schema created successfully!")


def main() -> None:
    """Main entry point for creating database schema."""
    create_tables(settings.ecfr_database_url)


if __name__ == "__main__":
    main()
