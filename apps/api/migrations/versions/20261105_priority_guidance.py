"""Persist independent priority guidance mode, balanced by default.

Revision ID: 20261105_priority_guidance
Revises: 20261104_admin_audit
"""
from alembic import op
import sqlalchemy as sa

revision = "20261105_priority_guidance"
down_revision = "20261104_admin_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_preferences", sa.Column(
        "priority_guidance_mode", sa.String(20), nullable=False, server_default="balanced",
    ))


def downgrade() -> None:
    op.drop_column("user_preferences", "priority_guidance_mode")
