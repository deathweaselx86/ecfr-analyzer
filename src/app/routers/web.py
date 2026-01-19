"""Web frontend routes for browsing agencies, titles, and CFR content."""

from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import get_db
from app.models import Agency, CFRReference, TitleMetadata

router = APIRouter(tags=["web"])

templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


def calculate_word_count(content: str | None) -> int:
    """Calculate word count from content string."""
    if not content:
        return 0
    return len(content.split())


def extract_first_sentences(text: str | None, num_sentences: int = 2) -> str:
    """Extract the first N sentences from text.

    Args:
        text: The text to extract sentences from
        num_sentences: Number of sentences to extract

    Returns:
        The first N sentences, or empty string if text is None/empty
    """
    if not text:
        return ""

    import re

    text = re.sub(r"<[^>]+>", "", text)

    # Split on sentence boundaries (. ! ?)
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())

    first_sentences = sentences[:num_sentences]

    return " ".join(first_sentences)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Home page with statistics and quick search."""
    total_agencies = db.execute(select(func.count(Agency.id))).scalar_one()
    total_titles = db.execute(select(func.count(TitleMetadata.number))).scalar_one()
    total_cfr_refs = db.execute(select(func.count(CFRReference.id))).scalar_one()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "version": settings.api_version,
            "stats": {
                "total_agencies": total_agencies,
                "total_titles": total_titles,
                "total_cfr_refs": total_cfr_refs,
            },
        },
    )


@router.get("/agencies", response_class=HTMLResponse, include_in_schema=False)
def agencies_page(
    request: Request,
    filter: str | None = None,  # noqa: A002
    parent_only: bool = True,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Get all agencies"""
    stmt = select(Agency).options(selectinload(Agency.cfr_references), selectinload(Agency.children))

    if parent_only:
        stmt = stmt.where(Agency.parent_id.is_(None))

    if filter:
        stmt = stmt.where(
            (Agency.display_name.ilike(f"%{filter}%"))
            | (Agency.name.ilike(f"%{filter}%"))
            | (Agency.slug.ilike(f"%{filter}%"))
        )

    stmt = stmt.order_by(Agency.sortable_name)

    agencies_result = db.execute(stmt).scalars().all()

    agencies_with_counts = []
    for agency in agencies_result:
        agencies_with_counts.append({
            **agency.__dict__,
            "children_count": len(agency.children) if agency.children else 0,
            "cfr_count": len(agency.cfr_references) if agency.cfr_references else 0,
        })

    return templates.TemplateResponse(
        "agencies.html", {"request": request, "version": settings.api_version, "agencies": agencies_with_counts}
    )


@router.get("/agencies/{agency_id}/details", response_class=HTMLResponse, include_in_schema=False)
def agency_details(request: Request, agency_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    """Get detailed agency information including CFR references and word count."""
    stmt = (
        select(Agency)
        .options(selectinload(Agency.cfr_references), selectinload(Agency.children), selectinload(Agency.parent))
        .where(Agency.id == agency_id)
    )
    agency = db.execute(stmt).scalar_one_or_none()

    if not agency:
        raise HTTPException(status_code=404, detail="Agency not found")

    total_word_count = 0
    for cfr_ref in agency.cfr_references:
        total_word_count += calculate_word_count(cfr_ref.content)

    return templates.TemplateResponse(
        "agency_details.html",
        {"request": request, "version": settings.api_version, "agency": agency, "word_count": total_word_count},
    )


@router.get("/titles", response_class=HTMLResponse, include_in_schema=False)
def titles_page(
    request: Request,
    filter: str | None = None,  # noqa: A002
    include_reserved: bool = False,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Titles listing page with filters and associated CFR references."""
    stmt = select(TitleMetadata).options(selectinload(TitleMetadata.cfr_references))

    if not include_reserved:
        stmt = stmt.where(TitleMetadata.reserved == False)  # noqa: E712

    if filter:
        stmt = stmt.where(
            (TitleMetadata.name.ilike(f"%{filter}%")) | (TitleMetadata.number.cast(str).ilike(f"%{filter}%"))
        )

    stmt = stmt.order_by(TitleMetadata.number)

    titles = db.execute(stmt).scalars().all()

    return templates.TemplateResponse(
        "titles.html", {"request": request, "version": settings.api_version, "titles": titles}
    )


@router.get("/search", response_class=HTMLResponse, include_in_schema=False)
def search_page(request: Request, q: str | None = None) -> HTMLResponse:
    """Search page."""
    return templates.TemplateResponse("search.html", {"request": request, "version": settings.api_version, "query": q})


@router.get("/search/results", response_class=HTMLResponse, include_in_schema=False)
async def search_results(  # noqa: C901
    request: Request, q: str, page: int = 1, per_page: int = 20, db: Session = Depends(get_db)
) -> HTMLResponse:
    """Full-text search results using eCFR.gov API."""
    api_url = "https://www.ecfr.gov/api/search/v1/results"
    params: dict[str, str | int] = {"query": q, "page": page, "per_page": per_page}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as e:
        return templates.TemplateResponse(
            "search_results.html",
            {
                "request": request,
                "version": settings.api_version,
                "query": q,
                "results": [],
                "error": f"Search API error: {e}",
                "metadata": {},
            },
        )

    results = []
    for result in data.get("results", []):
        hierarchy = result.get("hierarchy", {})
        headings = result.get("hierarchy_headings", {})

        title_parts = []
        if hierarchy.get("title"):
            title_parts.append(f"Title {hierarchy['title']}")
        if headings.get("chapter"):
            title_parts.append(f"Chapter {headings['chapter']}")
        if headings.get("part"):
            title_parts.append(f"Part {headings['part']}")
        if headings.get("section"):
            title_parts.append(f"§ {headings['section']}")

        title_str = " - ".join(title_parts) if title_parts else "Unknown"

        heading = result.get("headings", {}).get("section") or result.get("headings", {}).get("part") or ""

        cfr_summary = ""
        cfr_id = None
        if hierarchy.get("title") and hierarchy.get("part"):
            title_str = str(hierarchy.get("title"))
            part_str = str(hierarchy.get("part"))

            stmt = select(CFRReference).where(
                CFRReference.title == title_str,
                CFRReference.part == part_str,
            )

            if hierarchy.get("chapter"):
                stmt = stmt.where(CFRReference.chapter == str(hierarchy.get("chapter")))
            if hierarchy.get("subchapter"):
                stmt = stmt.where(CFRReference.subchapter == str(hierarchy.get("subchapter")))

            cfr_ref = db.execute(stmt).scalars().first()
            if cfr_ref:
                cfr_id = cfr_ref.id
                if cfr_ref.content:
                    cfr_summary = extract_first_sentences(cfr_ref.content, num_sentences=2)

        results.append({
            "title": hierarchy.get("title"),
            "chapter": hierarchy.get("chapter"),
            "part": hierarchy.get("part"),
            "section": hierarchy.get("section"),
            "subchapter": hierarchy.get("subchapter"),
            "title_str": title_str,
            "heading": heading,
            "snippet": result.get("full_text_excerpt", ""),
            "score": result.get("score", 0),
            "type": result.get("type", ""),
            "reserved": result.get("reserved", False),
            "cfr_summary": cfr_summary,
            "cfr_id": cfr_id,
        })

    metadata = data.get("metadata", {})

    return templates.TemplateResponse(
        "search_results.html",
        {
            "request": request,
            "version": settings.api_version,
            "query": q,
            "results": results,
            "metadata": metadata,
            "page": page,
            "per_page": per_page,
        },
    )


@router.get("/search/local", response_class=HTMLResponse, include_in_schema=False)
def local_search_results(
    request: Request, q: str, page: int = 1, per_page: int = 20, db: Session = Depends(get_db)
) -> HTMLResponse:
    """Search local AI summaries using PostgreSQL full-text search."""
    offset = (page - 1) * per_page

    tsquery = func.plainto_tsquery("english", q)

    stmt = (
        select(
            CFRReference,
            func.ts_rank(CFRReference.search_vector, tsquery).label("rank"),
            func.ts_headline(
                "english",
                func.coalesce(CFRReference.content, ""),
                tsquery,
                "MaxWords=50, MinWords=25, MaxFragments=1",
            ).label("headline"),
        )
        .where(CFRReference.search_vector.op("@@")(tsquery))
        .order_by(text("rank DESC"))
        .offset(offset)
        .limit(per_page)
    )

    search_results = db.execute(stmt).all()

    count_stmt = select(func.count(CFRReference.id)).where(CFRReference.search_vector.op("@@")(tsquery))
    total_count = db.execute(count_stmt).scalar_one()

    results = []
    for cfr, rank, headline in search_results:
        db.refresh(cfr, ["agencies"])

        title_parts = []
        if cfr.title:
            title_parts.append(f"Title {cfr.title}")
        if cfr.chapter:
            title_parts.append(f"Chapter {cfr.chapter}")
        if cfr.part:
            title_parts.append(f"Part {cfr.part}")
        if cfr.subchapter:
            title_parts.append(f"Subchapter {cfr.subchapter}")

        title_str = " - ".join(title_parts) if title_parts else "Unknown"

        results.append({
            "cfr_id": cfr.id,
            "title": cfr.title,
            "chapter": cfr.chapter,
            "part": cfr.part,
            "subchapter": cfr.subchapter,
            "title_str": title_str,
            "snippet": headline,
            "rank": float(rank),
            "agencies": cfr.agencies,
        })

    total_pages = (total_count + per_page - 1) // per_page

    metadata = {
        "total_count": total_count,
        "current_page": page,
        "total_pages": total_pages,
        "per_page": per_page,
    }

    return templates.TemplateResponse(
        "local_search_results.html",
        {
            "request": request,
            "version": settings.api_version,
            "query": q,
            "results": results,
            "metadata": metadata,
            "page": page,
            "per_page": per_page,
        },
    )


@router.get("/cfr/{cfr_id}", response_class=HTMLResponse, include_in_schema=False)
async def cfr_detail(request: Request, cfr_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    """CFR reference detail page with historical corrections."""
    stmt = select(CFRReference).options(selectinload(CFRReference.agencies)).where(CFRReference.id == cfr_id)
    cfr = db.execute(stmt).scalar_one_or_none()

    if not cfr:
        raise HTTPException(status_code=404, detail="CFR reference not found")

    word_count = calculate_word_count(cfr.content)

    stmt = select(TitleMetadata).where(TitleMetadata.number == cfr.title)
    title_metadata = db.execute(stmt).scalar_one_or_none()

    xml_url = None
    if title_metadata and title_metadata.up_to_date_as_of:
        cfr_date = title_metadata.up_to_date_as_of.isoformat()
        xml_url = f"https://www.ecfr.gov/api/versioner/v1/full/{cfr_date}/title-{cfr.title}.xml"

        params = []
        if cfr.chapter:
            params.append(f"chapter={cfr.chapter}")
        if cfr.part:
            params.append(f"part={cfr.part}")
        if cfr.subchapter:
            params.append(f"subchapter={cfr.subchapter}")

        if params:
            xml_url += "?" + "&".join(params)

    corrections = []
    try:
        async with httpx.AsyncClient() as client:
            corrections_url = f"https://www.ecfr.gov/api/admin/v1/corrections/title/{cfr.title}.json"
            response = await client.get(corrections_url, timeout=10)
            response.raise_for_status()
            corrections_data = response.json()
            corrections = corrections_data.get("ecfr_corrections", [])
    except httpx.HTTPError:
        pass

    return templates.TemplateResponse(
        "cfr_detail.html",
        {
            "request": request,
            "version": settings.api_version,
            "cfr": cfr,
            "word_count": word_count,
            "xml_url": xml_url,
            "corrections": corrections,
        },
    )
