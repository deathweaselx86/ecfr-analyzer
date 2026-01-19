"""Integration tests for web frontend routes."""

from unittest.mock import AsyncMock, patch

import pytest


class TestHomePage:
    """Test GET / endpoint."""

    def test_home_page_success(self, client, sample_agency, sample_title):
        """Test home page renders with statistics."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"CFR Analyzer" in response.content
        # Check that stats are displayed
        assert str(sample_title.number).encode() in response.content or b"1" in response.content

    def test_home_page_empty_db(self, client):
        """Test home page renders even with no data."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"CFR Analyzer" in response.content


class TestAgenciesPage:
    """Test GET /agencies endpoint."""

    def test_agencies_page_list(self, client, sample_agency):
        """Test agencies page displays list of agencies."""
        response = client.get("/agencies")
        assert response.status_code == 200
        assert sample_agency.display_name.encode() in response.content

    def test_agencies_page_with_filter(self, client, sample_agency):
        """Test agencies page with filter parameter."""
        response = client.get(f"/agencies?filter={sample_agency.name[:5]}")
        assert response.status_code == 200
        assert sample_agency.display_name.encode() in response.content

    def test_agencies_page_no_filter_match(self, client, sample_agency):
        """Test agencies page with filter that matches nothing."""
        response = client.get("/agencies?filter=xyz123nonexistent")
        assert response.status_code == 200
        # Should render but with no agencies
        assert sample_agency.display_name.encode() not in response.content

    def test_agencies_page_parent_only_filter(self, client, sample_agency, sample_child_agency):
        """Test agencies page shows only parent agencies by default."""
        response = client.get("/agencies?parent_only=true")
        assert response.status_code == 200
        assert sample_agency.display_name.encode() in response.content
        # Child agency should not appear in parent-only list
        assert sample_child_agency.display_name.encode() not in response.content

    def test_agencies_page_include_children(self, client, sample_agency, sample_child_agency):
        """Test agencies page can include child agencies."""
        response = client.get("/agencies?parent_only=false")
        assert response.status_code == 200
        assert sample_agency.display_name.encode() in response.content
        assert sample_child_agency.display_name.encode() in response.content


class TestAgencyDetails:
    """Test GET /agencies/{agency_id}/details endpoint."""

    def test_agency_details_success(self, client, sample_agency):
        """Test agency details page renders."""
        response = client.get(f"/agencies/{sample_agency.id}/details")
        assert response.status_code == 200
        assert sample_agency.display_name.encode() in response.content

    def test_agency_details_not_found(self, client):
        """Test agency details with non-existent ID."""
        response = client.get("/agencies/99999/details")
        assert response.status_code == 404

    def test_agency_details_with_cfr_refs(self, client, sample_agency, sample_cfr_reference, linked_agency_cfr):
        """Test agency details shows CFR references."""
        response = client.get(f"/agencies/{sample_agency.id}/details")
        assert response.status_code == 200
        assert sample_agency.display_name.encode() in response.content
        # Check for CFR reference information
        assert str(sample_cfr_reference.title).encode() in response.content


class TestTitlesPage:
    """Test GET /titles endpoint."""

    def test_titles_page_list(self, client, sample_title):
        """Test titles page displays list of titles."""
        response = client.get("/titles")
        assert response.status_code == 200
        assert sample_title.name.encode() in response.content
        assert str(sample_title.number).encode() in response.content

    def test_titles_page_exclude_reserved(self, client, sample_title, sample_reserved_title):
        """Test titles page excludes reserved titles by default."""
        response = client.get("/titles")
        assert response.status_code == 200
        assert sample_title.name.encode() in response.content
        assert sample_reserved_title.name.encode() not in response.content

    def test_titles_page_include_reserved(self, client, sample_title, sample_reserved_title):
        """Test titles page can include reserved titles."""
        response = client.get("/titles?include_reserved=true")
        assert response.status_code == 200
        assert sample_title.name.encode() in response.content
        assert sample_reserved_title.name.encode() in response.content

    def test_titles_page_with_filter(self, client, sample_title):
        """Test titles page with filter parameter."""
        response = client.get(f"/titles?filter={sample_title.name[:5]}")
        assert response.status_code == 200
        assert sample_title.name.encode() in response.content


class TestSearchPage:
    """Test GET /search endpoint."""

    def test_search_page_renders(self, client):
        """Test search page renders."""
        response = client.get("/search")
        assert response.status_code == 200

    def test_search_page_with_query(self, client):
        """Test search page with query parameter."""
        response = client.get("/search?q=test+query")
        assert response.status_code == 200


class TestSearchResults:
    """Test GET /search/results endpoint."""

    @pytest.mark.asyncio
    async def test_search_results_success(self, client):
        """Test search results with mocked eCFR API response."""
        mock_response_data = {
            "results": [
                {
                    "hierarchy": {"title": 7, "chapter": "I", "part": 100, "section": "1.1"},
                    "hierarchy_headings": {"chapter": "I", "part": "100", "section": "1.1"},
                    "headings": {"section": "Test Regulation"},
                    "full_text_excerpt": "This is a test excerpt",
                    "score": 0.95,
                    "type": "section",
                    "reserved": False,
                }
            ],
            "metadata": {
                "total": 1,
                "page": 1,
                "per_page": 20,
            },
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                json=lambda: mock_response_data,
                raise_for_status=lambda: None,
            )

            response = client.get("/search/results?q=test")
            assert response.status_code == 200
            assert b"Test Regulation" in response.content
            assert b"test excerpt" in response.content

    @pytest.mark.asyncio
    async def test_search_results_api_error(self, client):
        """Test search results when eCFR API fails."""
        import httpx

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.HTTPError("API Error")

            response = client.get("/search/results?q=test")
            assert response.status_code == 200
            # Should render error message
            assert b"error" in response.content.lower()

    @pytest.mark.asyncio
    async def test_search_results_pagination(self, client):
        """Test search results with pagination parameters."""
        mock_response_data = {
            "results": [],
            "metadata": {"total": 0, "page": 2, "per_page": 10},
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                json=lambda: mock_response_data,
                raise_for_status=lambda: None,
            )

            response = client.get("/search/results?q=test&page=2&per_page=10")
            assert response.status_code == 200


class TestCFRDetail:
    """Test GET /cfr/{cfr_id} endpoint."""

    @pytest.mark.asyncio
    async def test_cfr_detail_success(self, client, sample_cfr_reference, sample_title):
        """Test CFR detail page renders."""
        with patch("httpx.AsyncClient.get") as mock_get:
            # Mock the corrections API call
            mock_get.return_value = AsyncMock(
                status_code=200,
                json=lambda: {"ecfr_corrections": []},
                raise_for_status=lambda: None,
            )

            response = client.get(f"/cfr/{sample_cfr_reference.id}")
            assert response.status_code == 200
            assert str(sample_cfr_reference.title).encode() in response.content

    def test_cfr_detail_not_found(self, client):
        """Test CFR detail with non-existent ID."""
        response = client.get("/cfr/99999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cfr_detail_with_content(self, client, sample_cfr_reference, sample_title):
        """Test CFR detail displays content."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                json=lambda: {"ecfr_corrections": []},
                raise_for_status=lambda: None,
            )

            response = client.get(f"/cfr/{sample_cfr_reference.id}")
            assert response.status_code == 200
            # Check that content is displayed (first 500 chars)
            assert b"Sample Regulation" in response.content

    @pytest.mark.asyncio
    async def test_cfr_detail_with_corrections(self, client, sample_cfr_reference, sample_title):
        """Test CFR detail displays historical corrections."""
        mock_corrections = {
            "ecfr_corrections": [
                {
                    "corrective_action": "Test correction",
                    "error_occurred": "2024-01-01",
                    "error_corrected": "2024-01-15",
                    "fr_citation": "89 FR 12345",
                    "cfr_references": [{"cfr_reference": "7 CFR 100.1"}],
                }
            ]
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                json=lambda: mock_corrections,
                raise_for_status=lambda: None,
            )

            response = client.get(f"/cfr/{sample_cfr_reference.id}")
            assert response.status_code == 200
            assert b"Historical Corrections" in response.content
            assert b"Test correction" in response.content

    @pytest.mark.asyncio
    async def test_cfr_detail_with_agencies(
        self, client, sample_agency, sample_cfr_reference, linked_agency_cfr, sample_title
    ):
        """Test CFR detail shows associated agencies."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                json=lambda: {"ecfr_corrections": []},
                raise_for_status=lambda: None,
            )

            response = client.get(f"/cfr/{sample_cfr_reference.id}")
            assert response.status_code == 200
            assert b"Associated Agencies" in response.content
            assert sample_agency.display_name.encode() in response.content
