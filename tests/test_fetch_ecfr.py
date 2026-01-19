"""Tests for eCFR data ingestion script."""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add scripts directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fetch_ecfr import (
    extract_text_from_xml,
    fetch_cfr_xml_content,
    get_or_create_cfr_reference,
    parse_date,
    upsert_agency,
    upsert_title_metadata,
)


class TestParseDate:
    """Test parse_date function."""

    def test_parse_date_valid(self):
        """Test parsing valid ISO date string."""
        result = parse_date("2024-01-15")
        assert result == date(2024, 1, 15)

    def test_parse_date_none(self):
        """Test parsing None returns None."""
        result = parse_date(None)
        assert result is None

    def test_parse_date_invalid(self):
        """Test parsing invalid date raises ValueError."""
        with pytest.raises(ValueError):
            parse_date("not-a-date")


class TestExtractTextFromXml:
    """Test extract_text_from_xml function."""

    @pytest.mark.asyncio
    async def test_extract_text_success(self):
        """Test successful text extraction and summarization."""
        xml_content = """<?xml version="1.0"?>
        <root>
            <section>This is a regulation about food safety.</section>
            <paragraph>It requires inspections.</paragraph>
        </root>"""

        mock_anthropic = AsyncMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Summary of food safety regulation")]
        mock_anthropic.messages.create.return_value = mock_message

        result = await extract_text_from_xml(xml_content, mock_anthropic)

        assert result == "Summary of food safety regulation"
        mock_anthropic.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_text_empty_xml(self):
        """Test extraction from empty XML."""
        xml_content = """<?xml version="1.0"?><root></root>"""

        mock_anthropic = AsyncMock()
        result = await extract_text_from_xml(xml_content, mock_anthropic)

        assert result == ""
        mock_anthropic.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_text_api_failure_fallback(self):
        """Test fallback to truncated text when API fails."""
        xml_content = """<?xml version="1.0"?>
        <root>
            <section>This is a long regulation text that needs to be summarized.</section>
        </root>"""

        mock_anthropic = AsyncMock()
        mock_anthropic.messages.create.side_effect = Exception("API Error")

        result = await extract_text_from_xml(xml_content, mock_anthropic)

        # Should fall back to truncated text
        assert isinstance(result, str)
        assert len(result) > 0
        assert "regulation text" in result.lower()

    @pytest.mark.asyncio
    async def test_extract_text_fallback_truncation(self):
        """Test that fallback truncates to 1MB."""
        # Create a very long text (> 1MB)
        long_text = "x" * 2_000_000  # 2MB
        xml_content = f"""<?xml version="1.0"?><root><text>{long_text}</text></root>"""

        mock_anthropic = AsyncMock()
        mock_anthropic.messages.create.side_effect = Exception("API Error")

        result = await extract_text_from_xml(xml_content, mock_anthropic)

        # Should be truncated to 1MB
        assert len(result) <= 1_048_576

    @pytest.mark.asyncio
    async def test_extract_text_invalid_xml(self):
        """Test handling of invalid XML."""
        xml_content = "Not valid XML at all"

        mock_anthropic = AsyncMock()
        result = await extract_text_from_xml(xml_content, mock_anthropic)

        assert result == ""


class TestFetchCfrXmlContent:
    """Test fetch_cfr_xml_content function."""

    @pytest.mark.asyncio
    async def test_fetch_cfr_xml_success(self):
        """Test successful XML content fetch."""
        mock_client = AsyncMock()
        mock_limiter = AsyncMock()
        mock_anthropic = AsyncMock()

        mock_response = AsyncMock()
        mock_response.text = """<?xml version="1.0"?><root><text>Test content</text></root>"""
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Summary of regulation")]
        mock_anthropic.messages.create.return_value = mock_message

        result = await fetch_cfr_xml_content(
            client=mock_client,
            limiter=mock_limiter,
            anthropic_client=mock_anthropic,
            cfr_date="2024-01-15",
            title=7,
            chapter="I",
            part=100,
        )

        assert result == "Summary of regulation"
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_cfr_xml_http_error(self):
        """Test handling HTTP error during fetch."""
        import httpx

        mock_client = AsyncMock()
        mock_limiter = AsyncMock()
        mock_anthropic = AsyncMock()

        mock_client.get.side_effect = httpx.HTTPError("Network error")

        result = await fetch_cfr_xml_content(
            client=mock_client,
            limiter=mock_limiter,
            anthropic_client=mock_anthropic,
            cfr_date="2024-01-15",
            title=7,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_cfr_xml_with_params(self):
        """Test fetch with all parameters."""
        mock_client = AsyncMock()
        mock_limiter = AsyncMock()
        mock_anthropic = AsyncMock()

        mock_response = AsyncMock()
        mock_response.text = """<?xml version="1.0"?><root><text>Content</text></root>"""
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Summary")]
        mock_anthropic.messages.create.return_value = mock_message

        result = await fetch_cfr_xml_content(
            client=mock_client,
            limiter=mock_limiter,
            anthropic_client=mock_anthropic,
            cfr_date="2024-01-15",
            title=7,
            chapter="I",
            part=100,
            subchapter="A",
        )

        assert result == "Summary"
        # Verify the URL construction included all parameters
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["chapter"] == "I"
        assert call_args[1]["params"]["part"] == "100"
        assert call_args[1]["params"]["subchapter"] == "A"


class TestGetOrCreateCfrReference:
    """Test get_or_create_cfr_reference function."""

    def test_get_existing_cfr_reference(self, db_session, sample_cfr_reference):
        """Test getting an existing CFR reference."""
        result = get_or_create_cfr_reference(
            session=db_session,
            title=sample_cfr_reference.title,
            chapter=sample_cfr_reference.chapter,
            part=sample_cfr_reference.part,
            subchapter=sample_cfr_reference.subchapter,
        )

        assert result.id == sample_cfr_reference.id
        assert result.title == sample_cfr_reference.title

    def test_create_new_cfr_reference(self, db_session):
        """Test creating a new CFR reference."""
        result = get_or_create_cfr_reference(
            session=db_session,
            title=40,
            chapter="II",
            part=200,
            subchapter="B",
        )

        assert result.id is not None
        assert result.title == 40
        assert result.chapter == "II"
        assert result.part == 200
        assert result.subchapter == "B"


class TestUpsertTitleMetadata:
    """Test upsert_title_metadata function."""

    def test_insert_new_title(self, db_session):
        """Test inserting a new title."""
        title_data = {
            "number": 50,
            "name": "Wildlife and Fisheries",
            "latest_amended_on": "2024-01-01",
            "latest_issue_date": "2024-01-15",
            "up_to_date_as_of": "2024-02-01",
            "reserved": False,
        }

        result = upsert_title_metadata(db_session, title_data)

        assert result.number == 50
        assert result.name == "Wildlife and Fisheries"
        assert result.reserved is False

    def test_update_existing_title(self, db_session, sample_title):
        """Test updating an existing title."""
        title_data = {
            "number": sample_title.number,
            "name": "Updated Name",
            "latest_amended_on": "2024-06-01",
            "latest_issue_date": "2024-07-01",
            "up_to_date_as_of": "2024-07-15",
            "reserved": True,
        }

        result = upsert_title_metadata(db_session, title_data)

        assert result.number == sample_title.number
        assert result.name == "Updated Name"
        assert result.reserved is True


class TestUpsertAgency:
    """Test upsert_agency function."""

    def test_insert_new_agency(self, db_session):
        """Test inserting a new agency."""
        agency_data = {
            "name": "Test Agency",
            "short_name": "TA",
            "display_name": "Test Agency Display",
            "sortable_name": "Test Agency Sort",
            "slug": "test-agency",
            "cfr_references": [],
            "children": [],
        }

        result = upsert_agency(db_session, agency_data)

        assert result.slug == "test-agency"
        assert result.name == "Test Agency"
        assert result.parent_id is None

    def test_update_existing_agency(self, db_session, sample_agency):
        """Test updating an existing agency."""
        agency_data = {
            "name": "Updated Name",
            "short_name": "UN",
            "display_name": "Updated Display",
            "sortable_name": "Updated Sort",
            "slug": sample_agency.slug,
            "cfr_references": [],
            "children": [],
        }

        result = upsert_agency(db_session, agency_data)

        assert result.id == sample_agency.id
        assert result.name == "Updated Name"
        assert result.display_name == "Updated Display"

    def test_insert_agency_with_children(self, db_session):
        """Test inserting agency with child agencies."""
        agency_data = {
            "name": "Parent Agency",
            "display_name": "Parent Agency",
            "sortable_name": "Parent",
            "slug": "parent-agency",
            "cfr_references": [],
            "children": [
                {
                    "name": "Child Agency",
                    "display_name": "Child Agency",
                    "sortable_name": "Child",
                    "slug": "child-agency",
                    "cfr_references": [],
                    "children": [],
                }
            ],
        }

        result = upsert_agency(db_session, agency_data)

        assert result.slug == "parent-agency"
        db_session.refresh(result)
        assert len(result.children) == 1
        assert result.children[0].slug == "child-agency"
        assert result.children[0].parent_id == result.id

    def test_insert_agency_with_cfr_references(self, db_session):
        """Test inserting agency with CFR references."""
        agency_data = {
            "name": "Agency with CFR",
            "display_name": "Agency with CFR",
            "sortable_name": "Agency",
            "slug": "agency-with-cfr",
            "cfr_references": [
                {
                    "title": 40,
                    "chapter": "I",
                    "part": 50,
                    "subchapter": "C",
                }
            ],
            "children": [],
        }

        result = upsert_agency(db_session, agency_data)

        assert result.slug == "agency-with-cfr"
        db_session.refresh(result)
        assert len(result.cfr_references) == 1
        assert result.cfr_references[0].title == 40
