"""Persist the timer number visibility preference."""

from alembic import op
import sqlalchemy as sa


revision = "20261010_focus_timer_preference"
down_revision = "20261010_focus_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_settings", sa.Column("hide_timer_numbers", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("user_settings", "hide_timer_numbers")
