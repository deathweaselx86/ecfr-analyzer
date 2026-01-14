"""SQLAlchemy models for eCFR analyzer."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class Agency(Base):
    """Agency model representing federal agencies and sub-agencies."""

    __tablename__ = "agencies"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    short_name = Column(String, nullable=True)
    display_name = Column(String, nullable=False)
    sortable_name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True)
    parent_id = Column(Integer, ForeignKey("agencies.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationships
    children = relationship("Agency", backref="parent", remote_side=[id])
    cfr_references = relationship("CFRReference", secondary="agency_cfr_references", back_populates="agencies")

    __table_args__ = (
        Index("idx_agencies_parent_id", "parent_id"),
        Index("idx_agencies_slug", "slug"),
    )


class CFRReference(Base):
    """CFR (Code of Federal Regulations) reference model."""

    __tablename__ = "cfr_references"

    id = Column(Integer, primary_key=True)
    title = Column(Integer, nullable=False)
    chapter = Column(String, nullable=True)
    part = Column(Integer, nullable=True)
    subchapter = Column(String, nullable=True)

    # Relationships
    agencies = relationship("Agency", secondary="agency_cfr_references", back_populates="cfr_references")

    __table_args__ = (UniqueConstraint("title", "chapter", "part", "subchapter"),)


class AgencyCFRReference(Base):
    """Junction table linking agencies to CFR references."""

    __tablename__ = "agency_cfr_references"

    agency_id = Column(Integer, ForeignKey("agencies.id", ondelete="CASCADE"), primary_key=True)
    cfr_reference_id = Column(Integer, ForeignKey("cfr_references.id", ondelete="CASCADE"), primary_key=True)

    __table_args__ = (
        Index("idx_agency_cfr_agency", "agency_id"),
        Index("idx_agency_cfr_reference", "cfr_reference_id"),
    )


class Title(Base):
    """CFR Title model representing Code of Federal Regulations titles."""

    __tablename__ = "titles"

    number = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    latest_amended_on = Column(Date, nullable=True)
    latest_issue_date = Column(Date, nullable=True)
    up_to_date_as_of = Column(Date, nullable=True)
    reserved = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
