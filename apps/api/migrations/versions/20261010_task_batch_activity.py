"""Add TASKS_CREATED_BATCH activity type."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261010_task_batch_activity"
down_revision = "20261009_activity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TYPE activity_type ADD VALUE IF NOT EXISTS 'tasks_created_batch'"))


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP TYPE IF EXISTS activity_type WHERE 'tasks_created_batch' = ANY(enum_range('activity_type'))"
            )
        )
