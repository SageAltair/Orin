"""Persist autonomy preferences and approval expiration/lifecycle."""
from alembic import op
import sqlalchemy as sa

revision = "20261008_approval_policy"
down_revision = "20261008_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_preferences", sa.Column("autonomy_mode", sa.String(20), nullable=False, server_default="balanced"))
    op.add_column("user_preferences", sa.Column("custom_autonomy", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("approvals", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("ALTER TYPE approval_status ADD VALUE IF NOT EXISTS 'expired'")
    op.execute("ALTER TYPE approval_status ADD VALUE IF NOT EXISTS 'executed'")


def downgrade() -> None:
    op.drop_column("approvals", "expires_at")
    op.drop_column("user_preferences", "custom_autonomy")
    op.drop_column("user_preferences", "autonomy_mode")
