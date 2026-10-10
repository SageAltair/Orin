"""Add optional reminder offsets to calendar events."""

from alembic import op
import sqlalchemy as sa


revision = "20261015_calendar_ai_reminders"
down_revision = "20261014_task_scheduling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("calendar_events") as batch_op:
        batch_op.add_column(sa.Column("reminder_minutes", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_calendar_events_reminder_minutes",
            "reminder_minutes IS NULL OR reminder_minutes IN (5, 10, 15, 30, 60)",
        )


def downgrade() -> None:
    with op.batch_alter_table("calendar_events") as batch_op:
        batch_op.drop_constraint("ck_calendar_events_reminder_minutes", type_="check")
        batch_op.drop_column("reminder_minutes")
