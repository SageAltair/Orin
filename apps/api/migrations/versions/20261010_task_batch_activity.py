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
        downgrade_batch_activity_types(op.get_bind())


def downgrade_batch_activity_types(connection: sa.Connection) -> None:
    """Map batch events to a legacy type; PostgreSQL enum labels are retained on downgrade."""
    connection.execute(sa.text(
        "UPDATE activity SET activity_type = 'task_created' "
        "WHERE activity_type = 'tasks_created_batch'"
    ))
