"""Intelligent notification preferences, snooze and escalation state."""

from alembic import op
import sqlalchemy as sa

revision = "20261026_notifications"
down_revision = "20261025_planning"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("category", sa.String(32), nullable=False, server_default="calendar"),
        sa.Column("source_id", sa.Uuid()),
        sa.Column("snoozed_until", sa.DateTime(timezone=True)),
        sa.Column("attention_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("repeats", sa.Integer(), nullable=False, server_default="0"),
    ):
        op.add_column("notifications", column)
    op.execute("UPDATE notifications SET attention_at = due_at")
    op.execute(
        "UPDATE notifications SET category = 'routines' WHERE delivery_key LIKE 'routine:%'"
    )
    op.create_table(
        "notification_preferences",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("persistent", sa.Boolean(), nullable=False),
        sa.Column("repeat_minutes", sa.Integer(), nullable=False),
        sa.Column("max_repeats", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("quiet_enabled", sa.Boolean(), nullable=False),
        sa.Column("quiet_start", sa.String(5), nullable=False),
        sa.Column("quiet_end", sa.String(5), nullable=False),
        sa.Column("respect_focus", sa.Boolean(), nullable=False),
        sa.Column("browser_alerts", sa.Boolean(), nullable=False),
        sa.Column("sound", sa.Boolean(), nullable=False),
        sa.Column("repeat_day", sa.Date()),
        sa.Column("repeats_today", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade():
    op.drop_table("notification_preferences")
    for name in (
        "repeats",
        "revision",
        "attention_at",
        "snoozed_until",
        "source_id",
        "category",
    ):
        op.drop_column("notifications", name)
