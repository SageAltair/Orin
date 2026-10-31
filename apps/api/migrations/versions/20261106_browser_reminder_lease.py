"""Short-lived browser reminder leases for Windows workspace isolation.

Revision ID: 20261106_browser_reminder_lease
Revises: 20261105_priority_guidance
"""
from alembic import op
import sqlalchemy as sa

revision = "20261106_browser_reminder_lease"
down_revision = "20261105_priority_guidance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "browser_reminder_leases",
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("browser_reminder_leases")
