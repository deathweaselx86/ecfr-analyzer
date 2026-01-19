"""Integration tests for title API endpoints."""


class TestListTitles:
    """Test GET /api/v1/titles/ endpoint."""

    def test_list_titles_default(self, client, sample_title):
        """Test listing titles with default parameters."""
        response = client.get("/api/v1/titles/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["number"] == sample_title.number
        assert data[0]["name"] == sample_title.name
        assert data[0]["keywords"] == sample_title.keywords

    def test_list_titles_empty(self, client):
        """Test listing titles when none exist."""
        response = client.get("/api/v1/titles/")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_titles_exclude_reserved(self, client, sample_title, sample_reserved_title):
        """Test that reserved titles are excluded by default."""
        response = client.get("/api/v1/titles/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["number"] == sample_title.number
        assert data[0]["reserved"] is False

    def test_list_titles_include_reserved(self, client, sample_title, sample_reserved_title):
        """Test including reserved titles."""
        response = client.get("/api/v1/titles/?include_reserved=true")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        # Find the reserved title
        reserved = next((t for t in data if t["reserved"]), None)
        assert reserved is not None
        assert reserved["number"] == sample_reserved_title.number

    def test_list_titles_pagination(self, client, db_session):
        """Test pagination parameters."""

        from app.models import TitleMetadata

        # Create multiple titles
        titles = []
        for i in range(1, 6):
            title = TitleMetadata(
                number=i,
                name=f"Title {i}",
                reserved=False,
            )
            titles.append(title)
        db_session.add_all(titles)
        db_session.commit()

        # Test limit
        response = client.get("/api/v1/titles/?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["number"] == 1
        assert data[1]["number"] == 2

        # Test skip
        response = client.get("/api/v1/titles/?skip=2&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["number"] == 3
        assert data[1]["number"] == 4

    def test_list_titles_sorted_by_number(self, client, db_session):
        """Test that titles are sorted by number."""
        from app.models import TitleMetadata

        # Create titles in random order
        title_50 = TitleMetadata(number=50, name="Title 50", reserved=False)
        title_10 = TitleMetadata(number=10, name="Title 10", reserved=False)
        title_30 = TitleMetadata(number=30, name="Title 30", reserved=False)
        db_session.add_all([title_50, title_10, title_30])
        db_session.commit()

        response = client.get("/api/v1/titles/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["number"] == 10
        assert data[1]["number"] == 30
        assert data[2]["number"] == 50


class TestGetTitle:
    """Test GET /api/v1/titles/{title_number} endpoint."""

    def test_get_title_success(self, client, sample_title):
        """Test getting a title by number."""
        response = client.get(f"/api/v1/titles/{sample_title.number}")
        assert response.status_code == 200
        data = response.json()
        assert data["number"] == sample_title.number
        assert data["name"] == sample_title.name
        assert data["reserved"] == sample_title.reserved
        assert data["keywords"] == sample_title.keywords

    def test_get_title_not_found(self, client):
        """Test getting a non-existent title."""
        response = client.get("/api/v1/titles/999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_reserved_title(self, client, sample_reserved_title):
        """Test getting a reserved title."""
        response = client.get(f"/api/v1/titles/{sample_reserved_title.number}")
        assert response.status_code == 200
        data = response.json()
        assert data["number"] == sample_reserved_title.number
        assert data["reserved"] is True
        assert data["latest_amended_on"] is None

    def test_get_title_with_dates(self, client, sample_title):
        """Test that date fields are properly serialized."""
        response = client.get(f"/api/v1/titles/{sample_title.number}")
        assert response.status_code == 200
        data = response.json()
        assert "latest_amended_on" in data
        assert "latest_issue_date" in data
        assert "up_to_date_as_of" in data
        # Check date format (should be ISO 8601)
        if data["latest_amended_on"]:
            assert isinstance(data["latest_amended_on"], str)
            assert "-" in data["latest_amended_on"]

    def test_get_title_with_keywords(self, client, sample_title):
        """Test getting a title with keywords."""
        response = client.get(f"/api/v1/titles/{sample_title.number}")
        assert response.status_code == 200
        data = response.json()
        assert data["keywords"] == "farming, food, agriculture"
