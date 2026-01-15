"""Retrieve eCFR data (agencies and titles) from eCFR API and store in PostgreSQL database."""

import asyncio
import sys
from datetime import date
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import defusedxml.ElementTree as ET
import httpx
from aiolimiter import AsyncLimiter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Agency, AgencyCFRReference, CFRReference, TitleMetadata


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


def extract_text_from_xml(xml_content: str) -> str:
    """Extract text content from XML, stripping all tags.
       This will truncate documents that are > 1048575 characters,
       as that is the maximum length of a PostgreSQL tsvector column.

    Args:
        xml_content: XML string content

    Returns:
        Plain text content with tags removed
    """
    try:
        root = ET.fromstring(xml_content)
        text_parts = []
        for element in root.iter():
            if element.text:
                text_parts.append(element.text.strip())
            if element.tail:
                text_parts.append(element.tail.strip())
        text = " ".join(part for part in text_parts if part)
        if len(text) > 1048575:
            text = text[:1048575]
        return text  # noqa: TRY300
    except ET.ParseError:
        return ""


async def fetch_cfr_xml_content(
    client: httpx.AsyncClient,
    limiter: AsyncLimiter,
    cfr_date: str,
    title: int,
    chapter: str | None = None,
    part: int | None = None,
    subchapter: str | None = None,
) -> str | None:
    """Fetch XML content for a CFR reference from eCFR API and extract text.

    Returns:
        Extracted text content or None if fetch fails
    """
    # Build the API URL based on available parameters
    base_url = f"https://www.ecfr.gov/api/versioner/v1/full/{cfr_date}/title-{title}.xml"

    # Build query parameters for more specific retrieval
    params = {}
    if chapter:
        params["chapter"] = chapter
    if part:
        params["part"] = str(part)
    if subchapter:
        params["subchapter"] = subchapter

    try:
        async with limiter:
            response = await client.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            return extract_text_from_xml(response.text)

    except httpx.HTTPError as e:
        print(f"  Warning: Failed to fetch XML for title {title}, chapter {chapter}, part {part}: {e}")
        return None


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
        cfr_ref = CFRReference(
            title=title,
            chapter=chapter,
            part=part,
            subchapter=subchapter,
        )
        session.add(cfr_ref)
        session.flush()

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

    stmt = select(Agency).where(Agency.slug == slug)
    agency = session.execute(stmt).scalar_one_or_none()

    if agency is None:
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
        agency.name = agency_data["name"]
        agency.short_name = agency_data.get("short_name") or None
        agency.display_name = agency_data["display_name"]
        agency.sortable_name = agency_data["sortable_name"]
        agency.parent_id = parent_id

    session.flush()

    cfr_refs_data = agency_data.get("cfr_references", [])
    for cfr_ref_data in cfr_refs_data:
        cfr_ref = get_or_create_cfr_reference(
            session,
            title=cfr_ref_data.get("title"),
            chapter=cfr_ref_data.get("chapter"),
            part=cfr_ref_data.get("part"),
            subchapter=cfr_ref_data.get("subchapter"),
        )

        stmt = select(AgencyCFRReference).where(
            AgencyCFRReference.agency_id == agency.id,
            AgencyCFRReference.cfr_reference_id == cfr_ref.id,
        )
        existing_assoc = session.execute(stmt).scalar_one_or_none()

        if existing_assoc is None:
            assoc = AgencyCFRReference(
                agency_id=agency.id,
                cfr_reference_id=cfr_ref.id,
            )
            session.add(assoc)

    children = agency_data.get("children", [])
    for child_data in children:
        upsert_agency(session, child_data, parent_id=agency.id)

    return agency


def upsert_title_metadata(session: Session, title_data: dict[str, object]) -> TitleMetadata:
    """Insert or update CFR title metadata.

    Args:
        session: SQLAlchemy session
        title_data: Dictionary containing title data from API

    Returns:
        TitleMetadata instance
    """
    number = title_data["number"]

    stmt = select(TitleMetadata).where(TitleMetadata.number == number)
    title = session.execute(stmt).scalar_one_or_none()

    if title is None:
        title = TitleMetadata(
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


async def fetch_and_store_title_metadata(session: Session) -> None:
    """Fetch CFR title metadata from eCFR API and store in database.

    Args:
        session: SQLAlchemy session
    """
    print("Fetching titles from eCFR API...")
    async with httpx.AsyncClient() as client:
        response = await client.get("https://www.ecfr.gov/api/versioner/v1/titles.json", timeout=30)
        response.raise_for_status()
        data = response.json()

    print("Inserting titles...")
    titles = data.get("titles", [])
    for title_data in titles:
        upsert_title_metadata(session, title_data)

    print(f"Successfully inserted/updated {len(titles)} titles")


async def fetch_and_store_agencies(session: Session) -> None:
    """Fetch agencies from eCFR API and store in database.

    Args:
        session: SQLAlchemy session
    """
    print("Fetching agencies from eCFR API...")
    async with httpx.AsyncClient() as client:
        response = await client.get("https://www.ecfr.gov/api/admin/v1/agencies.json", timeout=30)
        response.raise_for_status()
        data = response.json()

    # Insert agencies
    print("Inserting agencies...")
    agencies = data.get("agencies", [])
    for agency_data in agencies:
        upsert_agency(session, agency_data)

    print(f"Successfully inserted {len(agencies)} top-level agencies")


async def fetch_and_populate_cfr_content(session: Session) -> None:
    """Fetch XML content for all CFR references and populate the content field.

    Args:
        session: SQLAlchemy session
    """
    print("\nFetching XML content for CFR references...")

    # Get all CFR references that don't have content
    stmt = select(CFRReference).where(
        (CFRReference.content == None) | (CFRReference.content == "")  # noqa: E711
    )
    cfr_refs = session.execute(stmt).scalars().all()

    # Rate limiting: 100 calls per 60 seconds
    limiter = AsyncLimiter(max_rate=100, time_period=60)

    updated_count = 0
    failed_count = 0
    skipped_count = 0

    async with httpx.AsyncClient() as client:
        for idx, cfr_ref in enumerate(cfr_refs, 1):
            print(
                f"  Processing {idx}/{len(cfr_refs)}: Title {cfr_ref.title}, "
                f"Chapter {cfr_ref.chapter}, Part {cfr_ref.part}..."
            )

            # Get the TitleMetadata for this CFR reference's title
            stmt = select(TitleMetadata).where(TitleMetadata.number == cfr_ref.title)
            title_metadata = session.execute(stmt).scalar_one_or_none()

            if title_metadata is None or title_metadata.up_to_date_as_of is None:
                print(f"    Warning: No up_to_date_as_of date found for title {cfr_ref.title}, skipping")
                skipped_count += 1
                continue

            cfr_date = title_metadata.up_to_date_as_of.isoformat()

            # Fetch XML content
            content = await fetch_cfr_xml_content(
                client=client,
                limiter=limiter,
                cfr_date=cfr_date,
                title=cfr_ref.title,
                chapter=cfr_ref.chapter,
                part=cfr_ref.part,
                subchapter=cfr_ref.subchapter,
            )

            if content:
                cfr_ref.content = content
                updated_count += 1
                print(f"    Successfully fetched {len(content)} characters (date: {cfr_date})")
            else:
                failed_count += 1
                print("    Failed to fetch content")

            # Commit every 10 records to avoid losing progress
            if idx % 10 == 0:
                session.commit()
                print(f"  Progress saved ({idx}/{len(cfr_refs)})")

    # Final commit
    session.commit()

    print("\nContent population complete:")
    print(f"  Updated: {updated_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Skipped: {skipped_count}")


async def ingest_ecfr_data() -> None:
    """Async main function for fetching data."""
    print("Connecting to database...")
    engine = create_engine(settings.ecfr_database_url, echo=False)

    try:
        with Session(engine) as session:
            await fetch_and_store_title_metadata(session)
            await fetch_and_store_agencies(session)
            await fetch_and_populate_cfr_content(session)

            session.commit()
    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        engine.dispose()


def main() -> None:
    asyncio.run(ingest_ecfr_data())


if __name__ == "__main__":
    main()
