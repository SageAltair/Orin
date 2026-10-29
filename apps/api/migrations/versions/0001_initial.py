"""Initial empty schema baseline.

Revision ID: 0001_initial
Revises:
"""
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial schema (currently no product tables)."""


def downgrade() -> None:
    """Revert initial schema."""
