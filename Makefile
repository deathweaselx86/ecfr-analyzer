.PHONY: install
install: ## Install the virtual environment and install the pre-commit hooks
	@echo "🚀 Creating virtual environment using uv"
	@uv sync
	@uv run pre-commit install

.PHONY: check
check: ## Run code quality tools.
	@echo "🚀 Checking lock file consistency with 'pyproject.toml'"
	@uv lock --locked
	@echo "🚀 Linting code: Running pre-commit"
	@uv run pre-commit run -a
	@echo "🚀 Static type checking: Running mypy"
	@uv run mypy
	@echo "🚀 Checking for obsolete dependencies: Running deptry"
	@uv run deptry src

.PHONY: test
test: ## Test the code with pytest
	@echo "🚀 Testing code: Running pytest"
	@uv run python -m pytest --cov --cov-config=pyproject.toml --cov-report=xml

.PHONY: docs-test
docs-test: ## Test if documentation can be built without warnings or errors
	@uv run mkdocs build -s

.PHONY: docs
docs: ## Build and serve the documentation
	@uv run mkdocs serve

.PHONY: createdb
createdb: ## Create database schema
	@echo "🚀 Creating database schema"
	@uv run python scripts/create_db.py

.PHONY: migrate
migrate: ## Apply database migrations
	@echo "🚀 Running database migrations"
	@uv run alembic upgrade head

.PHONY: migrate-create
migrate-create: ## Create a new migration (use MESSAGE="description")
	@echo "🚀 Creating new migration"
	@uv run alembic revision --autogenerate -m "$(MESSAGE)"

.PHONY: migrate-history
migrate-history: ## Show migration history
	@uv run alembic history

.PHONY: migrate-current
migrate-current: ## Show current migration version
	@uv run alembic current

.PHONY: migrate-downgrade
migrate-downgrade: ## Downgrade one migration version
	@echo "⚠️  Downgrading database by one version"
	@uv run alembic downgrade -1

.PHONY: fetch
fetch: ## Fetch all eCFR data (titles, agencies, and CFR content with AI summaries)
	@echo "🚀 Fetching eCFR data"
	@uv run python scripts/fetch_ecfr.py

.PHONY: serve
serve: ## Run FastAPI development server
	@echo "🚀 Starting FastAPI development server"
	@cd src && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: help
help:
	@uv run python -c "import re; \
	[[print(f'\033[36m{m[0]:<20}\033[0m {m[1]}') for m in re.findall(r'^([a-zA-Z_-]+):.*?## (.*)$$', open(makefile).read(), re.M)] for makefile in ('$(MAKEFILE_LIST)').strip().split()]"

.DEFAULT_GOAL := help
