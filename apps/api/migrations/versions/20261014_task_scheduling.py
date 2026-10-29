"""Add optional scheduled time blocks for existing tasks."""

from alembic import op
import sqlalchemy as sa


revision = "20261014_task_scheduling"
down_revision = "20261013_calendar_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("end_at > start_at", name="ck_task_schedules_time_order"),
        sa.CheckConstraint("estimated_minutes > 0", name="ck_task_schedules_estimated_positive"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_task_schedules_task"),
    )
    op.create_index("ix_task_schedules_user_start", "task_schedules", ["user_id", "start_at"])


def downgrade() -> None:
    op.drop_index("ix_task_schedules_user_start", table_name="task_schedules")
    op.drop_table("task_schedules")
