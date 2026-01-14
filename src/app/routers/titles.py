"""Title API routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Title
from app.schemas import TitleSchema

router = APIRouter(prefix="/titles", tags=["titles"])


@router.get("/", response_model=list[TitleSchema])
def list_titles(
    skip: int = 0,
    limit: int = 100,
    include_reserved: bool = False,
    db: Session = Depends(get_db),
) -> list[Title]:
    """List all CFR titles with pagination.

    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        include_reserved: Whether to include reserved titles
        db: Database session

    Returns:
        List of titles
    """
    stmt = select(Title)

    if not include_reserved:
        stmt = stmt.where(Title.reserved == False)  # noqa: E712

    stmt = stmt.offset(skip).limit(limit).order_by(Title.number)

    result = db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{title_number}", response_model=TitleSchema)
def get_title(title_number: int, db: Session = Depends(get_db)) -> Title:
    """Get a single title by number.

    Args:
        title_number: Title number
        db: Database session

    Returns:
        Title information

    Raises:
        HTTPException: If title not found
    """
    stmt = select(Title).where(Title.number == title_number)

    result = db.execute(stmt)
    title = result.scalar_one_or_none()

    if title is None:
        raise HTTPException(status_code=404, detail="Title not found")

    return title
