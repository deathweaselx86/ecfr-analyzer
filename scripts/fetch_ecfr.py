"""Retrieve eCFR data (agencies and titles) from eCFR API and store in PostgreSQL database."""

import os
import sys
from datetime import date
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import requests
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Agency, AgencyCFRReference, CFRReference, Title


def parse_date(date_string: str | None) -> date | None:
    """Parse ISO 8601 date string to date object.

    Args:
        date_string: ISO 8601 date string or None

    Returns:
        date object or None
    """
    if date_string is None:
        return None
    return date.fromisoformat(date_string)


def get_or_create_cfr_reference(
    session: Session,
    title: int,
    chapter: str,
    part: int | None,
    subchapter: str | None,
) -> CFRReference:
    """Get existing CFR reference or create a new one.

    Args:
        session: SQLAlchemy session
        title: CFR title number
        chapter: CFR chapter
        part: Optional CFR part
        subchapter: Optional CFR subchapter

    Returns:
        CFRReference instance
    """
    # Try to find existing CFR reference
    stmt = select(CFRReference).where(
        CFRReference.title == title,
        CFRReference.chapter == chapter,
        CFRReference.part == part,
        CFRReference.subchapter == subchapter,
    )
    cfr_ref = session.execute(stmt).scalar_one_or_none()

    if cfr_ref is None:
        # Create new CFR reference
        cfr_ref = CFRReference(
            title=title,
            chapter=chapter,
            part=part,
            subchapter=subchapter,
        )
        session.add(cfr_ref)
        session.flush()  # Flush to get the ID

    return cfr_ref


def upsert_agency(
    session: Session,
    agency_data: dict[str, object],
    parent_id: int | None = None,
) -> Agency:
    """Insert or update an agency and recursively handle its children.

    Args:
        session: SQLAlchemy session
        agency_data: Dictionary containing agency data from API
        parent_id: Optional ID of parent agency

    Returns:
        Agency instance
    """
    slug = agency_data["slug"]

    # Try to find existing agency by slug
    stmt = select(Agency).where(Agency.slug == slug)
    agency = session.execute(stmt).scalar_one_or_none()

    if agency is None:
        # Create new agency
        agency = Agency(
            name=agency_data["name"],
            short_name=agency_data.get("short_name") or None,
            display_name=agency_data["display_name"],
            sortable_name=agency_data["sortable_name"],
            slug=slug,
            parent_id=parent_id,
        )
        session.add(agency)
    else:
        # Update existing agency
        agency.name = agency_data["name"]
        agency.short_name = agency_data.get("short_name") or None
        agency.display_name = agency_data["display_name"]
        agency.sortable_name = agency_data["sortable_name"]
        agency.parent_id = parent_id

    session.flush()  # Flush to get the ID

    # Handle CFR references
    cfr_refs_data = agency_data.get("cfr_references", [])
    for cfr_ref_data in cfr_refs_data:
        cfr_ref = get_or_create_cfr_reference(
            session,
            title=cfr_ref_data.get("title"),
            chapter=cfr_ref_data.get("chapter"),
            part=cfr_ref_data.get("part"),
            subchapter=cfr_ref_data.get("subchapter"),
        )

        # Check if association already exists
        stmt = select(AgencyCFRReference).where(
            AgencyCFRReference.agency_id == agency.id,
            AgencyCFRReference.cfr_reference_id == cfr_ref.id,
        )
        existing_assoc = session.execute(stmt).scalar_one_or_none()

        if existing_assoc is None:
            # Create association
            assoc = AgencyCFRReference(
                agency_id=agency.id,
                cfr_reference_id=cfr_ref.id,
            )
            session.add(assoc)

    # Recursively handle children
    children = agency_data.get("children", [])
    for child_data in children:
        upsert_agency(session, child_data, parent_id=agency.id)

    return agency


def upsert_title(session: Session, title_data: dict[str, object]) -> Title:
    """Insert or update a CFR title.

    Args:
        session: SQLAlchemy session
        title_data: Dictionary containing title data from API

    Returns:
        Title instance
    """
    number = title_data["number"]

    # Try to find existing title by number
    stmt = select(Title).where(Title.number == number)
    title = session.execute(stmt).scalar_one_or_none()

    if title is None:
        title = Title(
            number=number,
            name=title_data["name"],
            latest_amended_on=parse_date(title_data.get("latest_amended_on")),
            latest_issue_date=parse_date(title_data.get("latest_issue_date")),
            up_to_date_as_of=parse_date(title_data.get("up_to_date_as_of")),
            reserved=title_data.get("reserved", False),
        )
        session.add(title)
    else:
        title.name = title_data["name"]
        title.latest_amended_on = parse_date(title_data.get("latest_amended_on"))
        title.latest_issue_date = parse_date(title_data.get("latest_issue_date"))
        title.up_to_date_as_of = parse_date(title_data.get("up_to_date_as_of"))
        title.reserved = title_data.get("reserved", False)

    session.flush()  # Flush to ensure data is written

    return title


def fetch_and_store_titles(session: Session) -> None:
    """Fetch CFR titles from eCFR API and store in database.

    Args:
        session: SQLAlchemy session
    """
    print("Fetching titles from eCFR API...")
    response = requests.get("https://www.ecfr.gov/api/versioner/v1/titles.json", timeout=30)
    response.raise_for_status()
    data = response.json()

    # Insert titles
    print("Inserting titles...")
    titles = data.get("titles", [])
    for title_data in titles:
        upsert_title(session, title_data)

    print(f"Successfully inserted/updated {len(titles)} titles")

    # Display metadata
    meta = data.get("meta", {})
    print(f"Metadata: date={meta.get('date')}, import_in_progress={meta.get('import_in_progress')}")


def fetch_and_store_agencies(session: Session) -> None:
    """Fetch agencies from eCFR API and store in database.

    Args:
        session: SQLAlchemy session
    """
    print("Fetching agencies from eCFR API...")
    response = requests.get("https://www.ecfr.gov/api/admin/v1/agencies.json", timeout=30)
    response.raise_for_status()
    data = response.json()

    # Insert agencies
    print("Inserting agencies...")
    agencies = data.get("agencies", [])
    for agency_data in agencies:
        upsert_agency(session, agency_data)

    print(f"Successfully inserted {len(agencies)} top-level agencies")


def main() -> None:
    """Main entry point for the script."""
    # Get database URL from environment variable
    database_url = os.environ.get("ECFR_DATABASE_URL")
    if not database_url:
        msg = "ECFR_DATABASE_URL environment variable is required"
        raise ValueError(msg)

    # Connect to database
    print("Connecting to database...")
    engine = create_engine(database_url, echo=False)

    try:
        with Session(engine) as session:
            fetch_and_store_titles(session)
            print()
            fetch_and_store_agencies(session)

            session.commit()
            print("\nAll data successfully fetched and stored!")

    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
