# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ecfr-analyzer is a web application for analyzing federal regulations by agency. It fetches data from the eCFR (electronic Code of Federal Regulations) API and provides a REST API for querying agencies, titles, and CFR references.

## Architecture

### Application Layer (src/app/)
All application code lives under `src/app/`:

- **Models** (`src/app/models.py`): SQLAlchemy ORM models defining database schema
  - `Agency`: Federal agencies with hierarchical parent-child relationships
  - `CFRReference`: CFR title/chapter/part/subchapter references
  - `AgencyCFRReference`: Many-to-many junction table
  - `Title`: CFR titles with metadata (amendment dates, reserved status)
  - All models include SQLAlchemy relationships for ORM queries

- **API** (`src/app/main.py`): FastAPI app with CORS middleware
- **Database** (`src/app/database.py`): Session management and dependency injection
- **Schemas** (`src/app/schemas.py`): Pydantic models for API request/response validation
- **Routers**:
  - `src/app/routers/agencies.py`: Agency endpoints with filtering, pagination, relationship loading
  - `src/app/routers/titles.py`: Title endpoints with reserved title filtering

### Data Ingestion Scripts
- **`scripts/create_db.py`**: Creates database schema from SQLAlchemy models
- **`scripts/fetch_ecfr.py`**: Fetches both titles and agencies from eCFR API and populates database
  - Uses upsert logic (ON CONFLICT) for re-runs
  - Handles hierarchical agency data recursively
  - Parses ISO 8601 dates for Title model

### Path Management
All scripts add `src/` to Python path using:
```python
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
```
This allows imports like `from app.models import Agency` from scripts directory.

## Development Environment

Uses `uv` for dependency management. Python 3.10-3.14 supported.

### Initial Setup
```bash
make install  # Creates virtual environment, installs dependencies, sets up pre-commit hooks
```

### Environment Variables
- `ECFR_DATABASE_URL`: PostgreSQL connection string (required for all database operations)
  - Format: `postgresql://user:password@localhost:5432/dbname`

## Common Commands

### Database Operations
```bash
export ECFR_DATABASE_URL="postgresql://user:password@localhost:5432/dbname"
make createdb  # Create database schema
make fetch     # Fetch eCFR data (titles and agencies)
```

### API Development
```bash
make serve     # Run FastAPI dev server at http://0.0.0.0:8000
# Endpoints:
#   GET /              - API info
#   GET /health        - Health check
#   GET /docs          - Swagger UI
#   GET /api/v1/agencies/           - List agencies (paginated, filterable by parent_id)
#   GET /api/v1/agencies/{id}       - Get agency with children and CFR references
#   GET /api/v1/agencies/slug/{slug} - Get agency by slug
#   GET /api/v1/titles/             - List titles (filterable by reserved status)
#   GET /api/v1/titles/{number}     - Get specific title
```

### Code Quality
```bash
make check              # Run all quality checks: lock file consistency, pre-commit, mypy, deptry
uv run pre-commit run -a  # Run pre-commit hooks on all files
uv run mypy             # Type checking (src/ directory only)
uv run deptry src       # Check for obsolete dependencies
```

### Testing
```bash
make test               # Run pytest with coverage
uv run python -m pytest tests  # Run all tests without coverage
uv run python -m pytest tests/test_foo.py::test_foo  # Run a single test
tox                     # Run tests across multiple Python versions
```

### Building and Documentation
```bash
make build              # Build wheel file
make docs               # Build and serve documentation locally
make docs-test          # Test if documentation builds without errors
```

## Key Dependencies

**Production:**
- `fastapi>=0.115.0` - Web framework
- `uvicorn>=0.34.0` - ASGI server
- `sqlalchemy>=2.0.0` - ORM and database toolkit
- `psycopg2-binary>=2.9.0` - PostgreSQL adapter
- `requests>=2.32.0` - HTTP client for eCFR API

**Development:**
- `ruff>=0.14.10` - Linting and formatting
- `mypy>=1.19.1` - Static type checking
- `pytest>=9.0.2` + `pytest-cov>=7.0.0` - Testing

## Code Quality Configuration

### Ruff
- Line length: 120 characters
- Target version: Python 3.14
- Auto-fix enabled
- Tests directory: S101 (assert statements) allowed

### MyPy
- Strict type checking enabled (`disallow_untyped_defs`, `disallow_any_unimported`)
- Scope: `src/` directory only (scripts excluded)

### Pre-commit Hooks
- Ruff check and format
- Standard checks: trailing whitespace, EOF fixer, merge conflict detection
- YAML, TOML, JSON validation

## Project Structure

```
src/
  app/                 # All application code
    main.py           # FastAPI app definition
    models.py         # SQLAlchemy ORM models
    database.py       # DB session management
    schemas.py        # Pydantic models
    routers/          # API route handlers
scripts/
  create_db.py        # Database schema creation
  fetch_ecfr.py       # eCFR data ingestion
tests/                # pytest tests
docs/                 # MkDocs documentation
```

## Database Schema Notes

- **Agency hierarchy**: Self-referential `parent_id` foreign key with CASCADE delete
- **CFR references**: Shared across agencies via junction table (not unique per agency)
- **Title uniqueness**: Primary key is `number` (not auto-increment ID)
- **Upsert patterns**: Scripts use `ON CONFLICT` for idempotent re-runs
- **Indexes**: Created on `agencies.slug`, `agencies.parent_id`, and junction table foreign keys

## API Design Patterns

- **Read-only**: All endpoints are GET (CORS restricted to GET methods)
- **Pagination**: Most list endpoints support `skip` and `limit` query parameters
- **Relationship loading**: Detail endpoints use `selectinload()` to eagerly load relationships
- **Error handling**: 404 HTTPException for missing resources
- **Dependency injection**: Database sessions provided via `Depends(get_db)`

## CI/CD Pipeline

GitHub Actions with three jobs:

1. **quality**: Runs `make check` on Ubuntu
2. **tests-and-type-check**: Matrix job across Python 3.10-3.14
3. **check-docs**: Validates MkDocs documentation builds

Coverage reports upload to Codecov on Python 3.11.
