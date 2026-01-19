"""Pytest fixtures and configuration for ecfr-analyzer tests."""

import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add src directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from app.database import get_db
from app.main import app
from app.models import Agency, AgencyCFRReference, Base, CFRReference, TitleMetadata


@pytest.fixture(scope="function")
def db_engine():
    """Create a test database engine.

    Uses PostgreSQL test database from TEST_DATABASE_URL environment variable.
    Falls back to ECFR_DATABASE_URL if TEST_DATABASE_URL is not set.

    Note: SQLite is not supported due to PostgreSQL-specific features (TSVECTOR, Computed columns).
    """
    import os

    # Get test database URL from environment
    test_db_url = os.getenv("TEST_DATABASE_URL") or os.getenv("ECFR_DATABASE_URL")

    if not test_db_url:
        pytest.skip("No test database URL configured. Set TEST_DATABASE_URL or ECFR_DATABASE_URL environment variable.")

    if "sqlite" in test_db_url.lower():
        pytest.skip("SQLite is not supported for tests due to PostgreSQL-specific features (TSVECTOR).")

    engine = create_engine(test_db_url, echo=False)

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Drop all tables and close connections
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a database session for testing."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Create a FastAPI test client with database session override."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_title(db_session) -> TitleMetadata:
    """Create a sample title metadata for testing."""
    title = TitleMetadata(
        number=7,
        name="Agriculture",
        latest_amended_on=date(2024, 1, 1),
        latest_issue_date=date(2024, 1, 1),
        up_to_date_as_of=date(2024, 1, 15),
        reserved=False,
        keywords="farming, food, agriculture",
    )
    db_session.add(title)
    db_session.commit()
    db_session.refresh(title)
    return title


@pytest.fixture
def sample_reserved_title(db_session) -> TitleMetadata:
    """Create a sample reserved title metadata for testing."""
    title = TitleMetadata(
        number=99,
        name="Reserved",
        latest_amended_on=None,
        latest_issue_date=None,
        up_to_date_as_of=None,
        reserved=True,
        keywords=None,
    )
    db_session.add(title)
    db_session.commit()
    db_session.refresh(title)
    return title


@pytest.fixture
def sample_agency(db_session) -> Agency:
    """Create a sample agency for testing."""
    agency = Agency(
        name="Department of Agriculture",
        short_name="USDA",
        display_name="U.S. Department of Agriculture",
        sortable_name="Agriculture, Department of",
        slug="agriculture-department",
        parent_id=None,
    )
    db_session.add(agency)
    db_session.commit()
    db_session.refresh(agency)
    return agency


@pytest.fixture
def sample_child_agency(db_session, sample_agency) -> Agency:
    """Create a sample child agency for testing."""
    child_agency = Agency(
        name="Food Safety and Inspection Service",
        short_name="FSIS",
        display_name="Food Safety and Inspection Service",
        sortable_name="Food Safety and Inspection Service",
        slug="food-safety-inspection-service",
        parent_id=sample_agency.id,
    )
    db_session.add(child_agency)
    db_session.commit()
    db_session.refresh(child_agency)
    return child_agency


@pytest.fixture
def sample_cfr_reference(db_session) -> CFRReference:
    """Create a sample CFR reference for testing."""
    cfr = CFRReference(
        title=7,
        chapter="I",
        part=100,
        subchapter="A",
        content="<h1>Sample Regulation</h1><p>This is a test regulation about agricultural products.</p>",
    )
    db_session.add(cfr)
    db_session.commit()
    db_session.refresh(cfr)
    return cfr


@pytest.fixture
def sample_empty_cfr_reference(db_session) -> CFRReference:
    """Create a sample CFR reference with no content for testing."""
    cfr = CFRReference(
        title=21,
        chapter="II",
        part=200,
        subchapter="B",
        content=None,
    )
    db_session.add(cfr)
    db_session.commit()
    db_session.refresh(cfr)
    return cfr


@pytest.fixture
def linked_agency_cfr(db_session, sample_agency, sample_cfr_reference):
    """Create a link between an agency and a CFR reference."""
    link = AgencyCFRReference(
        agency_id=sample_agency.id,
        cfr_reference_id=sample_cfr_reference.id,
    )
    db_session.add(link)
    db_session.commit()
    return link
