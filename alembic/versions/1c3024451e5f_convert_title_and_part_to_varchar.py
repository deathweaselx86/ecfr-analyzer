"""convert_title_and_part_to_varchar

Revision ID: 1c3024451e5f
Revises: 1db8fa14de36
Create Date: 2026-01-16 11:57:40.378975

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1c3024451e5f"
down_revision: str | Sequence[str] | None = "1db8fa14de36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - convert title and part columns from INTEGER to VARCHAR."""
    # Convert title from INTEGER to VARCHAR while preserving values
    op.execute("ALTER TABLE cfr_references ALTER COLUMN title TYPE VARCHAR USING title::VARCHAR")

    # Convert part from INTEGER to VARCHAR while preserving values
    op.execute("ALTER TABLE cfr_references ALTER COLUMN part TYPE VARCHAR USING part::VARCHAR")


def downgrade() -> None:
    """Downgrade schema - convert title and part columns from VARCHAR to INTEGER."""
    # Convert part from VARCHAR to INTEGER while preserving values
    op.execute("ALTER TABLE cfr_references ALTER COLUMN part TYPE INTEGER USING part::INTEGER")

    # Convert title from VARCHAR to INTEGER while preserving values
    op.execute("ALTER TABLE cfr_references ALTER COLUMN title TYPE INTEGER USING title::INTEGER")
