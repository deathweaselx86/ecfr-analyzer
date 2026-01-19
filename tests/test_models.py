"""Unit tests for SQLAlchemy models."""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Agency, AgencyCFRReference, CFRReference, TitleMetadata


class TestTitleMetadata:
    """Test TitleMetadata model."""

    def test_create_title_metadata(self, db_session):
        """Test creating a title metadata record."""
        title = TitleMetadata(
            number=50,
            name="Wildlife and Fisheries",
            latest_amended_on=date(2024, 6, 1),
            latest_issue_date=date(2024, 7, 1),
            up_to_date_as_of=date(2024, 7, 15),
            reserved=False,
            keywords="wildlife, fisheries, conservation",
        )
        db_session.add(title)
        db_session.commit()

        assert title.number == 50
        assert title.name == "Wildlife and Fisheries"
        assert title.reserved is False
        assert title.keywords == "wildlife, fisheries, conservation"
        assert title.created_at is not None
        assert title.updated_at is not None

    def test_create_reserved_title(self, db_session):
        """Test creating a reserved title."""
        title = TitleMetadata(
            number=100,
            name="Reserved",
            reserved=True,
        )
        db_session.add(title)
        db_session.commit()

        assert title.reserved is True
        assert title.latest_amended_on is None
        assert title.keywords is None

    def test_title_metadata_unique_number(self, db_session, sample_title):
        """Test that title numbers must be unique."""
        duplicate_title = TitleMetadata(
            number=sample_title.number,
            name="Duplicate",
            reserved=False,
        )
        db_session.add(duplicate_title)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_title_cfr_references_relationship(self, db_session, sample_title, sample_cfr_reference):
        """Test the relationship between TitleMetadata and CFRReference."""
        # The CFRReference should be accessible through the relationship
        stmt = select(TitleMetadata).where(TitleMetadata.number == sample_title.number)
        title = db_session.execute(stmt).scalar_one()

        # Check that the relationship loads CFR references
        cfr_refs = title.cfr_references
        assert len(cfr_refs) == 1
        assert cfr_refs[0].id == sample_cfr_reference.id


class TestAgency:
    """Test Agency model."""

    def test_create_agency(self, db_session):
        """Test creating an agency."""
        agency = Agency(
            name="Environmental Protection Agency",
            short_name="EPA",
            display_name="U.S. Environmental Protection Agency",
            sortable_name="Environmental Protection Agency",
            slug="epa",
        )
        db_session.add(agency)
        db_session.commit()

        assert agency.id is not None
        assert agency.name == "Environmental Protection Agency"
        assert agency.short_name == "EPA"
        assert agency.slug == "epa"
        assert agency.parent_id is None
        assert agency.created_at is not None

    def test_agency_unique_slug(self, db_session, sample_agency):
        """Test that agency slugs must be unique."""
        duplicate_agency = Agency(
            name="Different Name",
            display_name="Different Display",
            sortable_name="Different Sort",
            slug=sample_agency.slug,
        )
        db_session.add(duplicate_agency)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_agency_parent_child_relationship(self, db_session, sample_agency, sample_child_agency):
        """Test the parent-child relationship between agencies."""
        # Refresh to load relationships
        db_session.refresh(sample_agency)
        db_session.refresh(sample_child_agency)

        # Check parent relationship
        assert sample_child_agency.parent_id == sample_agency.id
        assert sample_child_agency.parent.id == sample_agency.id

        # Check children relationship
        assert len(sample_agency.children) == 1
        assert sample_agency.children[0].id == sample_child_agency.id

    def test_agency_cfr_references_relationship(
        self, db_session, sample_agency, sample_cfr_reference, linked_agency_cfr
    ):
        """Test the many-to-many relationship between agencies and CFR references."""
        db_session.refresh(sample_agency)

        # Check that the agency has the CFR reference
        assert len(sample_agency.cfr_references) == 1
        assert sample_agency.cfr_references[0].id == sample_cfr_reference.id


class TestCFRReference:
    """Test CFRReference model."""

    def test_create_cfr_reference(self, db_session):
        """Test creating a CFR reference."""
        cfr = CFRReference(
            title=40,
            chapter="I",
            part=50,
            subchapter="C",
            content="<p>Environmental regulations content</p>",
        )
        db_session.add(cfr)
        db_session.commit()

        assert cfr.id is not None
        assert cfr.title == 40
        assert cfr.chapter == "I"
        assert cfr.part == 50
        assert cfr.subchapter == "C"
        assert cfr.content is not None

    def test_cfr_reference_unique_constraint(self, db_session, sample_cfr_reference):
        """Test that the combination of title, chapter, part, subchapter must be unique."""
        duplicate_cfr = CFRReference(
            title=sample_cfr_reference.title,
            chapter=sample_cfr_reference.chapter,
            part=sample_cfr_reference.part,
            subchapter=sample_cfr_reference.subchapter,
            content="Different content",
        )
        db_session.add(duplicate_cfr)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_cfr_reference_nullable_fields(self, db_session):
        """Test that chapter, part, subchapter, and content can be null."""
        cfr = CFRReference(
            title=45,
            chapter=None,
            part=None,
            subchapter=None,
            content=None,
        )
        db_session.add(cfr)
        db_session.commit()

        assert cfr.id is not None
        assert cfr.title == 45
        assert cfr.chapter is None
        assert cfr.part is None
        assert cfr.content is None

    def test_cfr_agencies_relationship(self, db_session, sample_agency, sample_cfr_reference, linked_agency_cfr):
        """Test the many-to-many relationship between CFR references and agencies."""
        db_session.refresh(sample_cfr_reference)

        # Check that the CFR reference has the agency
        assert len(sample_cfr_reference.agencies) == 1
        assert sample_cfr_reference.agencies[0].id == sample_agency.id


class TestAgencyCFRReference:
    """Test AgencyCFRReference junction table."""

    def test_create_agency_cfr_link(self, db_session, sample_agency, sample_cfr_reference):
        """Test creating a link between agency and CFR reference."""
        link = AgencyCFRReference(
            agency_id=sample_agency.id,
            cfr_reference_id=sample_cfr_reference.id,
        )
        db_session.add(link)
        db_session.commit()

        # Verify the link was created
        stmt = select(AgencyCFRReference).where(
            AgencyCFRReference.agency_id == sample_agency.id,
            AgencyCFRReference.cfr_reference_id == sample_cfr_reference.id,
        )
        result = db_session.execute(stmt).scalar_one_or_none()
        assert result is not None

    def test_multiple_agencies_same_cfr(self, db_session, sample_agency, sample_cfr_reference):
        """Test that multiple agencies can reference the same CFR."""
        agency2 = Agency(
            name="Second Agency",
            display_name="Second Agency Display",
            sortable_name="Second Agency",
            slug="second-agency",
        )
        db_session.add(agency2)
        db_session.commit()

        link1 = AgencyCFRReference(
            agency_id=sample_agency.id,
            cfr_reference_id=sample_cfr_reference.id,
        )
        link2 = AgencyCFRReference(
            agency_id=agency2.id,
            cfr_reference_id=sample_cfr_reference.id,
        )
        db_session.add_all([link1, link2])
        db_session.commit()

        db_session.refresh(sample_cfr_reference)
        assert len(sample_cfr_reference.agencies) == 2
