"""Retrieve eCFR data (agencies and titles) from eCFR API and store in PostgreSQL database."""

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import anthropic
import defusedxml.ElementTree as ET
import httpx
from aiolimiter import AsyncLimiter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Agency, AgencyCFRReference, CFRReference, TitleMetadata


def parse_date(date_string: str | None) -> date | None:
    """Parse ISO 8601 date string to date object."""
    if date_string is None:
        return None
    return date.fromisoformat(date_string)


async def extract_text_from_xml(xml_content: str, anthropic_client: anthropic.AsyncAnthropic) -> str:
    """Extract text content from XML and generate a summary using Claude Haiku."""
    try:
        root = ET.fromstring(xml_content)
        text_parts = []
        for element in root.iter():
            if element.text:
                text_parts.append(element.text.strip())
            if element.tail:
                text_parts.append(element.tail.strip())
        text = " ".join(part for part in text_parts if part)

        if not text:
            return ""

        try:
            message = await anthropic_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100000,
                messages=[
                    {
                        "role": "user",
                        "content": f"""Please provide a concise summary of the following federal regulation text.
The summary should be less than 500 words and capture the key points, requirements, and scope of the regulation.
Highlight any content that would indicate that the regulation hurts business. Use HTML to format the summary, not Markdown.


Text:
{text[:100000]}""",
                    }
                ],
            )

            summary = message.content[0].text
            return summary  # noqa: TRY300

        except Exception as e:  # I hate this as much as you do.
            print(f"  Warning: Failed to generate summary with Claude: {e}")
            # Fall back to truncated text if summarization fails (max 1MB)
            max_size = 1_048_576  # 1MB in characters
            return text[:max_size] if len(text) > max_size else text

    except ET.ParseError:
        return ""


async def fetch_cfr_xml_content(
    client: httpx.AsyncClient,
    limiter: AsyncLimiter,
    anthropic_client: anthropic.AsyncAnthropic,
    cfr_date: str,
    title: int,
    chapter: str | None = None,
    part: int | None = None,
    subchapter: str | None = None,
) -> str | None:
    """Fetch XML content for a CFR reference from eCFR API and generate summary."""
    base_url = f"https://www.ecfr.gov/api/versioner/v1/full/{cfr_date}/title-{title}.xml"

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
            return await extract_text_from_xml(response.text, anthropic_client)

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
    """Get existing CFR reference or create a new one."""
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
    """Insert or update an agency and recursively handle its children."""
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
    """Insert or update CFR title metadata."""
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

    session.flush()

    return title


async def fetch_and_store_title_metadata(session: Session) -> None:
    """Fetch CFR title metadata from eCFR API and store in database."""
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
    """Fetch agencies from eCFR API and store in database."""
    print("Fetching agencies from eCFR API...")
    async with httpx.AsyncClient() as client:
        response = await client.get("https://www.ecfr.gov/api/admin/v1/agencies.json", timeout=30)
        response.raise_for_status()
        data = response.json()

    print("Inserting agencies...")
    agencies = data.get("agencies", [])
    for agency_data in agencies:
        upsert_agency(session, agency_data)

    print(f"Successfully inserted {len(agencies)} top-level agencies")


async def fetch_and_populate_cfr_content(session: Session) -> None:
    """Fetch XML content for all CFR references and populate the content field with AI-generated summaries.

    Note: This will update ALL CFR references, including those that already have content.
          Existing summaries will be regenerated and overwritten.
    """
    print("\nFetching XML content for CFR references and generating summaries...")
    print("Note: This will regenerate summaries for ALL CFR references, including those with existing content.")

    stmt = select(CFRReference)
    cfr_refs = session.execute(stmt).scalars().all()

    print(f"Found {len(cfr_refs)} CFR references to process.")

    limiter = AsyncLimiter(max_rate=100, time_period=60)

    updated_count = 0
    failed_count = 0
    skipped_count = 0

    anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async with httpx.AsyncClient() as client:
        for idx, cfr_ref in enumerate(cfr_refs, 1):
            print(
                f"  Processing {idx}/{len(cfr_refs)}: Title {cfr_ref.title}, "
                f"Chapter {cfr_ref.chapter}, Part {cfr_ref.part}..."
            )

            stmt = select(TitleMetadata).where(TitleMetadata.number == cfr_ref.title)
            title_metadata = session.execute(stmt).scalar_one_or_none()

            if title_metadata is None or title_metadata.up_to_date_as_of is None:
                print(f"    Warning: No up_to_date_as_of date found for title {cfr_ref.title}, skipping")
                skipped_count += 1
                continue

            cfr_date = title_metadata.up_to_date_as_of.isoformat()

            content = await fetch_cfr_xml_content(
                client=client,
                limiter=limiter,
                anthropic_client=anthropic_client,
                cfr_date=cfr_date,
                title=cfr_ref.title,
                chapter=cfr_ref.chapter,
                part=cfr_ref.part,
                subchapter=cfr_ref.subchapter,
            )

            if content:
                cfr_ref.content = content
                updated_count += 1
                print(f"    Successfully generated summary ({len(content)} characters, date: {cfr_date})")
            else:
                failed_count += 1
                print("    Failed to generate summary")

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


async def ingest_ecfr_data(
    fetch_titles: bool = True,
    fetch_agencies: bool = True,
    fetch_cfr_content: bool = True,
) -> None:
    """Async main function for fetching data."""
    print("Connecting to database...")
    engine = create_engine(settings.ecfr_database_url, echo=False)

    try:
        with Session(engine) as session:
            if fetch_titles:
                print("\n=== Fetching Titles ===")
                await fetch_and_store_title_metadata(session)
            else:
                print("\n=== Skipping Titles (not requested) ===")

            if fetch_agencies:
                print("\n=== Fetching Agencies ===")
                await fetch_and_store_agencies(session)
            else:
                print("\n=== Skipping Agencies (not requested) ===")

            if fetch_cfr_content:
                print("\n=== Fetching CFR Content ===")
                await fetch_and_populate_cfr_content(session)
            else:
                print("\n=== Skipping CFR Content (not requested) ===")

            session.commit()
    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        engine.dispose()


def main() -> None:
    """Parse CLI arguments and run data ingestion."""
    parser = argparse.ArgumentParser(
        description="Fetch eCFR data (titles, agencies, and/or CFR content) from eCFR API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--titles",
        action="store_true",
        help="Fetch and store CFR title metadata",
    )
    parser.add_argument(
        "--agencies",
        action="store_true",
        help="Fetch and store agencies with their CFR references",
    )
    parser.add_argument(
        "--cfr-references",
        action="store_true",
        dest="cfr_references",
        help="Fetch XML content and generate AI summaries for CFR references",
    )

    args = parser.parse_args()

    # If no specific flags are provided, fetch everything
    if not (args.titles or args.agencies or args.cfr_references):
        print("No specific flags provided - fetching everything (titles, agencies, and CFR content)")
        fetch_titles = True
        fetch_agencies = True
        fetch_cfr_content = True
    else:
        fetch_titles = args.titles
        fetch_agencies = args.agencies
        fetch_cfr_content = args.cfr_references

    asyncio.run(ingest_ecfr_data(fetch_titles, fetch_agencies, fetch_cfr_content))


if __name__ == "__main__":
    main()
