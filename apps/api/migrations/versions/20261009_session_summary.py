"""Persist a bounded continuity summary for long-running sessions."""
from alembic import op
import sqlalchemy as sa


revision = "20261009_session_summary"
down_revision = "20261009_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "summary")
