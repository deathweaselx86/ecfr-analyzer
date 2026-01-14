"""Agency API routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Agency
from app.schemas import AgencyDetailSchema, AgencySchema

router = APIRouter(prefix="/agencies", tags=["agencies"])


@router.get("/", response_model=list[AgencySchema])
def list_agencies(
    skip: int = 0,
    limit: int = 100,
    parent_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[Agency]:
    """List all agencies with pagination and optional parent filter.

    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        parent_id: Filter by parent agency ID (None for top-level agencies)
        db: Database session

    Returns:
        List of agencies
    """
    stmt = select(Agency)

    if parent_id is not None:
        stmt = stmt.where(Agency.parent_id == parent_id)
    else:
        # If no parent_id specified, default to top-level agencies
        stmt = stmt.where(Agency.parent_id.is_(None))

    stmt = stmt.offset(skip).limit(limit).order_by(Agency.sortable_name)

    result = db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{agency_id}", response_model=AgencyDetailSchema)
def get_agency(agency_id: int, db: Session = Depends(get_db)) -> Agency:
    """Get a single agency by ID with all relationships.

    Args:
        agency_id: Agency ID
        db: Database session

    Returns:
        Agency with relationships

    Raises:
        HTTPException: If agency not found
    """
    stmt = (
        select(Agency)
        .where(Agency.id == agency_id)
        .options(selectinload(Agency.children), selectinload(Agency.cfr_references))
    )

    result = db.execute(stmt)
    agency = result.scalar_one_or_none()

    if agency is None:
        raise HTTPException(status_code=404, detail="Agency not found")

    return agency


@router.get("/slug/{slug}", response_model=AgencyDetailSchema)
def get_agency_by_slug(slug: str, db: Session = Depends(get_db)) -> Agency:
    """Get a single agency by slug with all relationships.

    Args:
        slug: Agency slug
        db: Database session

    Returns:
        Agency with relationships

    Raises:
        HTTPException: If agency not found
    """
    stmt = (
        select(Agency)
        .where(Agency.slug == slug)
        .options(selectinload(Agency.children), selectinload(Agency.cfr_references))
    )

    result = db.execute(stmt)
    agency = result.scalar_one_or_none()

    if agency is None:
        raise HTTPException(status_code=404, detail="Agency not found")

    return agency
