"""Web frontend routes for browsing agencies, titles, and CFR content."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import get_db
from app.models import Agency, CFRReference, TitleMetadata

router = APIRouter(tags=["web"])

# Setup templates
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


def calculate_word_count(content: str | None) -> int:
    """Calculate word count from content string."""
    if not content:
        return 0
    return len(content.split())


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Home page with statistics and quick search."""
    # Get stats
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
    """Basic"""
    # Build query
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

    # Add counts to agencies
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

    # Calculate total word count for all CFR references
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
    """Titles listing page with filters."""
    stmt = select(TitleMetadata)

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
def search_results(request: Request, q: str, limit: int = 20, db: Session = Depends(get_db)) -> HTMLResponse:
    """Full-text search results using PostgreSQL tsvector."""
    # Perform full-text search
    stmt = (
        select(CFRReference)
        .options(selectinload(CFRReference.agencies))
        .where(CFRReference.search_vector.op("@@")(func.plainto_tsquery("english", q)))
        .order_by(func.ts_rank(CFRReference.search_vector, func.plainto_tsquery("english", q)).desc())
        .limit(limit)
    )

    results_raw = db.execute(stmt).scalars().all()

    # Add word count and snippet to results
    results = []
    for cfr in results_raw:
        word_count = calculate_word_count(cfr.content)

        # Create snippet using ts_headline for context around matches
        # MaxWords=70 gives roughly 512 characters, MinWords=50, MaxFragments=3 for multiple matches
        snippet = ""
        if cfr.content:
            snippet_stmt = select(
                func.ts_headline(
                    "english",
                    cfr.content,
                    func.plainto_tsquery("english", q),
                    "MaxWords=70, MinWords=50, MaxFragments=3, StartSel=<mark>, StopSel=</mark>",
                )
            ).where(CFRReference.id == cfr.id)
            snippet = db.execute(snippet_stmt).scalar_one()

        # Get rank
        rank_stmt = select(func.ts_rank(CFRReference.search_vector, func.plainto_tsquery("english", q))).where(
            CFRReference.id == cfr.id
        )
        rank = db.execute(rank_stmt).scalar_one()

        results.append({
            "id": cfr.id,
            "title": cfr.title,
            "chapter": cfr.chapter,
            "part": cfr.part,
            "subchapter": cfr.subchapter,
            "snippet": snippet,
            "word_count": word_count,
            "rank": float(rank),
            "agencies": cfr.agencies[:10],  # Limit to 10 agencies
        })

    return templates.TemplateResponse(
        "search_results.html", {"request": request, "version": settings.api_version, "query": q, "results": results}
    )


@router.get("/cfr/{cfr_id}", response_class=HTMLResponse, include_in_schema=False)
def cfr_detail(request: Request, cfr_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    """CFR reference detail page."""
    stmt = select(CFRReference).options(selectinload(CFRReference.agencies)).where(CFRReference.id == cfr_id)
    cfr = db.execute(stmt).scalar_one_or_none()

    if not cfr:
        raise HTTPException(status_code=404, detail="CFR reference not found")

    word_count = calculate_word_count(cfr.content)

    return templates.TemplateResponse(
        "cfr_detail.html", {"request": request, "version": settings.api_version, "cfr": cfr, "word_count": word_count}
    )
