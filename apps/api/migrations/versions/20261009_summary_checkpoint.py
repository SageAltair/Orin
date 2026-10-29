"""Track which turns are covered by each rolling work-session summary."""
from alembic import op
import sqlalchemy as sa


revision = "20261009_summary_checkpoint"
down_revision = "20261009_session_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("summary_through_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "summary_through_at")
