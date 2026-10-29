"""Durable reminders and shared authentication throttling."""
from alembic import op
import sqlalchemy as sa

revision = "20261024_reliability"
down_revision = "20261023_creative_activity_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("anonymous_rate_windows",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column("route", sa.String(120), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("subject_hash", "route", "window_start", name="uq_anonymous_rate_window"))
    op.create_table("notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("calendar_events.id", ondelete="CASCADE")),
        sa.Column("delivery_key", sa.String(200), unique=True, nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("anonymous_rate_windows")
