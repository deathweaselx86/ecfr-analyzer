"""Integration tests for agency API endpoints."""


class TestListAgencies:
    """Test GET /api/v1/agencies/ endpoint."""

    def test_list_agencies_default(self, client, sample_agency):
        """Test listing agencies with default parameters."""
        response = client.get("/api/v1/agencies/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == sample_agency.id
        assert data[0]["name"] == sample_agency.name
        assert data[0]["slug"] == sample_agency.slug

    def test_list_agencies_empty(self, client):
        """Test listing agencies when none exist."""
        response = client.get("/api/v1/agencies/")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_agencies_pagination(self, client, db_session):
        """Test pagination parameters."""
        # Create multiple agencies
        from app.models import Agency

        agencies = []
        for i in range(5):
            agency = Agency(
                name=f"Agency {i}",
                display_name=f"Agency {i}",
                sortable_name=f"Agency {i:02d}",
                slug=f"agency-{i}",
            )
            agencies.append(agency)
        db_session.add_all(agencies)
        db_session.commit()

        # Test limit
        response = client.get("/api/v1/agencies/?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Test skip
        response = client.get("/api/v1/agencies/?skip=2&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "Agency 2"

    def test_list_agencies_filter_by_parent(self, client, sample_agency, sample_child_agency):
        """Test filtering agencies by parent_id."""
        # List top-level agencies (default)
        response = client.get("/api/v1/agencies/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == sample_agency.id

        # List child agencies
        response = client.get(f"/api/v1/agencies/?parent_id={sample_agency.id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == sample_child_agency.id
        assert data[0]["parent_id"] == sample_agency.id

    def test_list_agencies_sorted(self, client, db_session):
        """Test that agencies are sorted by sortable_name."""
        from app.models import Agency

        # Create agencies with different sortable names
        agency_z = Agency(
            name="Zebra Agency",
            display_name="Zebra Agency",
            sortable_name="Zebra",
            slug="zebra-agency",
        )
        agency_a = Agency(
            name="Alpha Agency",
            display_name="Alpha Agency",
            sortable_name="Alpha",
            slug="alpha-agency",
        )
        db_session.add_all([agency_z, agency_a])
        db_session.commit()

        response = client.get("/api/v1/agencies/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["sortable_name"] == "Alpha"
        assert data[1]["sortable_name"] == "Zebra"


class TestGetAgencyById:
    """Test GET /api/v1/agencies/{agency_id} endpoint."""

    def test_get_agency_success(self, client, sample_agency):
        """Test getting an agency by ID."""
        response = client.get(f"/api/v1/agencies/{sample_agency.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_agency.id
        assert data["name"] == sample_agency.name
        assert data["display_name"] == sample_agency.display_name
        assert data["slug"] == sample_agency.slug

    def test_get_agency_not_found(self, client):
        """Test getting a non-existent agency."""
        response = client.get("/api/v1/agencies/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_agency_with_children(self, client, sample_agency, sample_child_agency):
        """Test that getting an agency includes its children."""
        response = client.get(f"/api/v1/agencies/{sample_agency.id}")
        assert response.status_code == 200
        data = response.json()
        assert "children" in data
        assert len(data["children"]) == 1
        assert data["children"][0]["id"] == sample_child_agency.id

    def test_get_agency_with_cfr_references(self, client, sample_agency, sample_cfr_reference, linked_agency_cfr):
        """Test that getting an agency includes its CFR references."""
        response = client.get(f"/api/v1/agencies/{sample_agency.id}")
        assert response.status_code == 200
        data = response.json()
        assert "cfr_references" in data
        assert len(data["cfr_references"]) == 1
        assert data["cfr_references"][0]["id"] == sample_cfr_reference.id
        assert data["cfr_references"][0]["title"] == sample_cfr_reference.title


class TestGetAgencyBySlug:
    """Test GET /api/v1/agencies/slug/{slug} endpoint."""

    def test_get_agency_by_slug_success(self, client, sample_agency):
        """Test getting an agency by slug."""
        response = client.get(f"/api/v1/agencies/slug/{sample_agency.slug}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_agency.id
        assert data["slug"] == sample_agency.slug

    def test_get_agency_by_slug_not_found(self, client):
        """Test getting an agency with non-existent slug."""
        response = client.get("/api/v1/agencies/slug/non-existent-slug")
        assert response.status_code == 404

    def test_get_agency_by_slug_with_relationships(
        self, client, sample_agency, sample_child_agency, sample_cfr_reference, linked_agency_cfr
    ):
        """Test that getting by slug includes all relationships."""
        response = client.get(f"/api/v1/agencies/slug/{sample_agency.slug}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["children"]) == 1
        assert len(data["cfr_references"]) == 1
