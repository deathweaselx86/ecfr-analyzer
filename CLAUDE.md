# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ecfr-analyzer is a web application for analyzing federal regulations by agency. It fetches data from the eCFR (electronic Code of Federal Regulations) API and provides a REST API for querying agencies, titles, and CFR references.

## Architecture

### Application Layer (src/app/)
All application code lives under `src/app/`:

- **Models** (`src/app/models.py`): SQLAlchemy ORM models defining database schema
  - `Agency`: Federal agencies with hierarchical parent-child relationships
  - `CFRReference`: CFR title/chapter/part/subchapter references with AI-generated summaries
    - `title` and `part` are VARCHAR (not INTEGER) - stored as strings for flexibility
    - `content` field stores AI-generated summaries from Claude 3.5 Haiku
    - `search_vector` computed field (TSVECTOR) provides PostgreSQL full-text search via GIN index
      - Automatically generated from `content` field using `to_tsvector('english', ...)`
      - Used by `/search/local` endpoint for fast full-text search of AI summaries
  - `AgencyCFRReference`: Many-to-many junction table
  - `TitleMetadata`: CFR titles with metadata (amendment dates, reserved status, keywords)
    - `keywords` field for searchable keywords (VARCHAR)
  - All models include SQLAlchemy relationships for ORM queries

- **API** (`src/app/main.py`): FastAPI app with CORS middleware
- **Database** (`src/app/database.py`): Session management and dependency injection
- **Schemas** (`src/app/schemas.py`): Pydantic models for API request/response validation
- **Config** (`src/app/config.py`): Pydantic settings loaded from `.env` file at project root
- **Routers**:
  - `src/app/routers/agencies.py`: Agency endpoints with filtering, pagination, relationship loading
  - `src/app/routers/titles.py`: Title endpoints with reserved title filtering
  - `src/app/routers/web.py`: Web frontend with Jinja2 templates for browsing agencies, titles, and full-text search

### Data Ingestion Scripts
- **`scripts/create_db.py`**: Creates database schema from SQLAlchemy models (deprecated - use Alembic migrations)
- **`scripts/fetch_ecfr.py`**: Async script that fetches titles, agencies, and CFR content from eCFR API
  - **Technology**: Uses `httpx` for async HTTP requests, `aiolimiter` for rate limiting, `defusedxml` for safe XML parsing, `anthropic` SDK for AI summarization, and `argparse` for CLI
  - **CLI Arguments**: Supports selective fetching via command-line flags
    - `--titles`: Fetch only title metadata
    - `--agencies`: Fetch only agencies
    - `--cfr-references`: Fetch only CFR content with AI summaries
    - No flags: Fetch everything (default)
    - Flags can be combined (e.g., `--titles --agencies`)
  - **Three-phase execution**: `ingest_ecfr_data()` orchestrates the pipeline based on CLI arguments
    1. `fetch_and_store_title_metadata()` - Fetches title metadata from `/api/versioner/v1/titles.json`
    2. `fetch_and_store_agencies()` - Fetches agency hierarchy from `/api/admin/v1/agencies.json`
    3. `fetch_and_populate_cfr_content()` - Fetches XML content and generates AI summaries for each CFR reference
  - **XML content retrieval and summarization**: Uses title-specific dates from `TitleMetadata.up_to_date_as_of` for accurate versioning
    - Endpoint: `/api/versioner/v1/full/{date}/title-{title}.xml` with optional chapter/part/subchapter params
    - Text extraction strips XML tags using `defusedxml`
    - **AI Summarization**: Uses Claude 3.5 Haiku to generate concise summaries (<500 words) of regulation text
    - Summaries stored in `CFRReference.content` field for searchability
    - Falls back to truncated text if AI summarization fails
  - Uses upsert logic for re-runs (idempotent operations)
  - Handles hierarchical agency data recursively via `upsert_agency()`
  - **Rate limiting**: Uses `AsyncLimiter` (100 calls per 60 seconds) to respect eCFR API limits
  - Progress saved every 10 records during content population

### Database Migrations
- **Alembic** integration for schema migrations
- Migration files in `alembic/versions/`
- `alembic/env.py` automatically loads database URL from `settings.ecfr_database_url`
- Uses same path management pattern as scripts (`sys.path.insert()` to import from `src/`)
- **Current migrations**:
  - `dea0cacdf16b`: Initial schema
  - `1db8fa14de36`: Add keywords column to TitleMetadata
  - `1c3024451e5f`: Convert title and part columns to VARCHAR (preserving data)

### Path Management
All scripts add `src/` to Python path using:
```python
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
```
This allows imports like `from app.models import Agency` from scripts directory.

## Development Environment

Uses `uv` for dependency management. Python 3.10-3.14 supported (tested in CI).

### Initial Setup
```bash
make install  # Creates virtual environment, installs dependencies, sets up pre-commit hooks
```

### Environment Variables
- `ECFR_DATABASE_URL`: PostgreSQL connection string (required for all database operations)
  - Format: `postgresql://user:password@localhost:5432/dbname`
- `ANTHROPIC_API_KEY`: Anthropic API key (required for data ingestion)
  - Used by `scripts/fetch_ecfr.py` to generate AI summaries of regulation text
  - Get your API key from https://console.anthropic.com/

## Common Commands

### Database Operations
```bash
export ECFR_DATABASE_URL="postgresql://user:password@localhost:5432/dbname"
export ANTHROPIC_API_KEY="sk-ant-..."  # Required for CFR content fetching

# Migrations
make migrate           # Apply database migrations (recommended)
make createdb          # Create database schema (deprecated - use migrations)
make migrate-create MESSAGE="description"  # Create new migration
make migrate-history   # Show migration history
make migrate-current   # Show current migration version
make migrate-downgrade # Downgrade one migration version

# Data Fetching
make fetch             # Fetch everything (titles, agencies, and CFR content with AI summaries)

# Or use the script directly with selective fetching:
uv run python scripts/fetch_ecfr.py                    # Fetch everything (default)
uv run python scripts/fetch_ecfr.py --titles           # Fetch only titles
uv run python scripts/fetch_ecfr.py --agencies         # Fetch only agencies
uv run python scripts/fetch_ecfr.py --cfr-references   # Fetch only CFR content (summaries)
uv run python scripts/fetch_ecfr.py --titles --agencies  # Fetch titles and agencies only
```

**Data Fetching Process**:

The `make fetch` command (or running the script directly) can perform three steps:

1. **Titles** (`--titles`): Fetches and stores CFR title metadata (including `up_to_date_as_of` dates)
2. **Agencies** (`--agencies`): Fetches and stores agencies with their CFR references
3. **CFR Content** (`--cfr-references`): Fetches XML content and generates AI summaries
   - **Processes ALL CFR references** - regenerates summaries even for existing content
   - Each CFR reference uses its title's `up_to_date_as_of` date for accurate versioning
   - Extracts plain text from XML using `defusedxml`
   - **Generates AI summaries** using Claude 3.5 Haiku (<500 words per regulation)
   - Stores summaries in `CFRReference.content` field (overwrites existing content)
   - Skips references with missing title metadata
   - **Requires `ANTHROPIC_API_KEY`** to be set

**Performance Notes**:
- Respects eCFR API rate limits (100 calls/minute)
- CFR content fetching uses Anthropic API for summarization (additional cost)
- **Regenerates ALL summaries on each run** - useful for updating summaries with improved prompts
- May take significant time for large datasets due to AI processing
- Progress saved every 10 records to avoid data loss

### API Development
```bash
make serve     # Run FastAPI dev server at http://0.0.0.0:8000
# Web Frontend Endpoints:
#   GET /                            - Home page with statistics and dual search (local + eCFR.gov)
#   GET /agencies                    - Browse agencies with filtering
#   GET /agencies/{id}/details       - Agency detail page with CFR references and word count
#   GET /titles                      - Browse titles with filtering
#   GET /cfr/{id}                    - CFR reference detail page with AI summary, agencies, corrections
#   GET /search                      - Search form
#   GET /search/local?q=query        - Local search of AI summaries using PostgreSQL full-text search
#   GET /search/results?q=query      - External search from eCFR.gov API with AI summary previews
#
# REST API Endpoints:
#   GET /health                      - Health check
#   GET /docs                        - Swagger UI
#   GET /api/v1/agencies/            - List agencies (paginated, filterable by parent_id)
#   GET /api/v1/agencies/{id}        - Get agency with children and CFR references
#   GET /api/v1/agencies/slug/{slug} - Get agency by slug
#   GET /api/v1/titles/              - List titles (filterable by reserved status)
#   GET /api/v1/titles/{number}      - Get specific title
```

### Code Quality
```bash
make check              # Run all quality checks: lock file consistency, pre-commit, mypy, deptry
uv run pre-commit run -a  # Run pre-commit hooks on all files
uv run mypy             # Type checking (src/ directory only)
uv run deptry src       # Check for obsolete dependencies
```

### Testing

**Requirements:**
- PostgreSQL database (tests use PostgreSQL-specific features like TSVECTOR and Computed columns)
- Set `TEST_DATABASE_URL` environment variable (or `ECFR_DATABASE_URL` as fallback)

```bash
# Set up test database
export TEST_DATABASE_URL="postgresql://user:password@localhost:5432/ecfr_test"

# Run tests
make test               # Run pytest with coverage
uv run python -m pytest tests  # Run all tests without coverage
uv run python -m pytest tests/test_models.py  # Run specific test file
uv run python -m pytest tests/test_models.py::TestAgency::test_create_agency  # Run single test
tox                     # Run tests across multiple Python versions
```

**Test Coverage:**
- Unit tests for SQLAlchemy models (models, relationships, constraints)
- Integration tests for REST API endpoints (agencies, titles, CFR references)
- Integration tests for web routes (HTML pages, search, CFR details)
- Unit tests for data ingestion functions (XML parsing, API calls, upserts)

**Note:** SQLite is not supported for tests due to PostgreSQL-specific database features.

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
- `alembic>=1.18.1` - Database migration tool
- `requests>=2.32.0` - HTTP client (legacy, kept for compatibility)
- `httpx>=0.28.1` - Async HTTP client for eCFR API and web search
- `aiolimiter>=1.2.1` - Async rate limiting
- `defusedxml>=0.7.1` - Safe XML parsing
- `anthropic>=0.40.0` - Anthropic SDK for AI summarization
- `pydantic-settings>=2.12.0` - Settings management
- `jinja2>=3.1.5` - Template engine for web frontend
- `markdown>=3.5.0` - Markdown to HTML conversion for CFR summaries

**Development:**
- `ruff>=0.14.10` - Linting and formatting
- `mypy>=1.19.1` - Static type checking
- `pytest>=9.0.2` + `pytest-cov>=7.0.0` - Testing
- `pytest-asyncio>=0.25.2` - Async test support
- `pytest-mock>=3.14.0` - Mocking capabilities
- `httpx>=0.28.1` - Async HTTP client (also used in tests)

## Code Quality Configuration

### Ruff
- Line length: 120 characters
- Target version: Python 3.14
- Auto-fix enabled
- Per-file ignores:
  - Tests directory: S101 (assert statements) allowed
  - Routers: B008 (Depends() in function defaults) allowed

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
    config.py         # Pydantic settings (loads from .env)
    models.py         # SQLAlchemy ORM models
    database.py       # DB session management
    schemas.py        # Pydantic models for API
    templates/        # Jinja2 HTML templates for web frontend
    routers/          # Route handlers
      agencies.py     # REST API for agencies
      titles.py       # REST API for titles
      web.py          # Web frontend routes
scripts/
  create_db.py        # Database schema creation (deprecated)
  fetch_ecfr.py       # eCFR data ingestion
alembic/              # Database migrations
  versions/           # Migration files
  env.py             # Alembic environment configuration
tests/                # pytest tests
docs/                 # MkDocs documentation
.env                  # Environment variables (not in repo)
```

## Database Schema Notes

- **Agency hierarchy**: Self-referential `parent_id` foreign key with CASCADE delete
- **CFR references**: Shared across agencies via junction table (not unique per agency)
  - `title` and `part` columns are VARCHAR (not INTEGER) for flexibility with string identifiers
  - `content` field stores AI-generated summaries from Claude 3.5 Haiku (<500 words per regulation)
  - `search_vector` computed column (TSVECTOR) enables full-text search with GIN index
    - **Actively used** by `/search/local` endpoint for searching AI summaries
    - Automatically updated when `content` changes (PostgreSQL computed column)
    - Supports ranking, highlighting, and advanced search operators
  - Summaries are more concise and searchable than raw regulation text
- **TitleMetadata uniqueness**: Primary key is `number` (INTEGER, not auto-increment)
  - `up_to_date_as_of` date used for versioned XML retrieval per title
  - `keywords` field (TEXT) for searchable metadata
  - Relationship to CFRReference uses type casting: `cast(number, String) == CFRReference.title`
- **Upsert patterns**: Scripts use `ON CONFLICT` for idempotent re-runs
- **Indexes**: Created on `agencies.slug`, `agencies.parent_id`, `cfr_references.search_vector` (GIN), and junction table foreign keys

## API Design Patterns

- **Read-only**: All endpoints are GET (CORS restricted to GET methods)
- **Pagination**: Most list endpoints support `skip` and `limit` query parameters
- **Relationship loading**: Detail endpoints use `selectinload()` to eagerly load relationships
- **Error handling**: 404 HTTPException for missing resources
- **Dependency injection**: Database sessions provided via `Depends(get_db)`

## Web Frontend Features

The application includes a web UI (`src/app/routers/web.py`) built with Jinja2 templates and Tailwind CSS:

- **Home page**: Displays statistics (total agencies, titles) with **dual search options**
  - Radio buttons to choose between "AI Summaries" (local) or "eCFR.gov Official" (external)
  - Search form uses HTMX to load results dynamically into `#search-results` div without page refresh
  - JavaScript dynamically updates form endpoint, placeholder text, and button styling based on selection
- **Agency browsing**: Filter by name/slug, toggle parent-only view, see CFR reference counts
- **Title browsing**: Filter titles, toggle reserved titles, view associated CFR references
- **Search functionality** (dual modes):
  - **Local search** (`/search/local`):
    - Uses PostgreSQL full-text search on `search_vector` column
    - Searches AI-generated summaries stored locally
    - Uses `plainto_tsquery()` for query parsing and `@@` operator for matching
    - Ranks results by relevance using `ts_rank()`
    - Generates highlighted excerpts using `ts_headline()` (max 50 words)
    - Shows matching excerpt, associated agencies, and relevance score
    - Links to full CFR summary and eCFR.gov
    - Pagination with HTMX (updates results div without page reload)
  - **External search** (`/search/results`):
    - Uses eCFR.gov API (`/api/search/v1/results`) for official content search
    - Queries local database to find matching CFR references for AI summary previews
    - Shows first 2 sentences of AI summaries when available
    - Links to both eCFR.gov (official) and local CFR detail pages (AI summary)
    - Pagination support via query parameters
- **Detail pages**:
  - Agency details with word count across all CFR references
  - CFR reference details with:
    - AI-generated summaries (first 500 chars visible, expandable with HTML `<details>`)
    - Associated agencies with links
    - Links to eCFR.gov XML source (versioned by `up_to_date_as_of` date)
    - **Historical corrections** fetched from eCFR API showing corrective actions, dates, and Federal Register citations
    - Corrections are collapsible by default using HTML `<details>` element
- **Content rendering**: CFR summaries use `|safe` filter (HTML from AI, not markdown)
- **Helper functions**:
  - `calculate_word_count()`: Counts words in CFR content
  - `extract_first_sentences()`: Extracts first N sentences from text (strips HTML tags)
- Templates use `include_in_schema=False` to hide from OpenAPI docs

## CI/CD Pipeline

GitHub Actions with three jobs:

1. **quality**: Runs `make check` on Ubuntu
2. **tests-and-type-check**: Matrix job across Python 3.10-3.14
3. **check-docs**: Validates MkDocs documentation builds
