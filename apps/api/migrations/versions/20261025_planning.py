"""Opportunities, risks and timezone-aware recurring routines."""

from alembic import op
import sqlalchemy as sa

revision = "20261025_planning"
down_revision = "20261024_reliability"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "opportunities",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column(
            "task_id",
            sa.Uuid(),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column("title", sa.String(240), nullable=False, primary_key=False),
        sa.Column("category", sa.String(32), nullable=False, primary_key=False),
        sa.Column("stage", sa.String(24), nullable=False, primary_key=False),
        sa.Column("description", sa.Text(), nullable=False, primary_key=False),
        sa.Column("source_url", sa.String(2000), nullable=False, primary_key=False),
        sa.Column("contact", sa.String(240), nullable=False, primary_key=False),
        sa.Column("next_action", sa.String(240), nullable=False, primary_key=False),
        sa.Column("decision_notes", sa.Text(), nullable=False, primary_key=False),
        sa.Column("deadline", sa.Date(), nullable=True, primary_key=False),
        sa.Column("review_on", sa.Date(), nullable=True, primary_key=False),
        sa.Column("value", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("fit", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("effort", sa.Integer(), nullable=False, primary_key=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            primary_key=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            primary_key=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_opportunities_user_id", "opportunities", ["user_id"])
    op.create_table(
        "risks",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "opportunity_id",
            sa.Uuid(),
            sa.ForeignKey("opportunities.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column("title", sa.String(240), nullable=False, primary_key=False),
        sa.Column("likelihood", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("impact", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("status", sa.String(24), nullable=False, primary_key=False),
        sa.Column("response", sa.String(24), nullable=False, primary_key=False),
        sa.Column("trigger", sa.String(500), nullable=False, primary_key=False),
        sa.Column("mitigation", sa.Text(), nullable=False, primary_key=False),
        sa.Column("review_on", sa.Date(), nullable=True, primary_key=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            primary_key=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            primary_key=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_risks_user_id", "risks", ["user_id"])
    op.create_table(
        "routines",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("title", sa.String(240), nullable=False, primary_key=False),
        sa.Column("timezone", sa.String(64), nullable=False, primary_key=False),
        sa.Column("weekdays", sa.JSON(), nullable=False, primary_key=False),
        sa.Column("start_date", sa.Date(), nullable=False, primary_key=False),
        sa.Column("end_date", sa.Date(), nullable=True, primary_key=False),
        sa.Column("time_of_day", sa.String(5), nullable=False, primary_key=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("minimum_minutes", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("cue", sa.String(500), nullable=False, primary_key=False),
        sa.Column("steps", sa.Text(), nullable=False, primary_key=False),
        sa.Column("minimum_action", sa.String(500), nullable=False, primary_key=False),
        sa.Column("reward", sa.String(500), nullable=False, primary_key=False),
        sa.Column("reminder_minutes", sa.Integer(), nullable=True, primary_key=False),
        sa.Column("paused", sa.Boolean(), nullable=False, primary_key=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            primary_key=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            primary_key=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_routines_user_id", "routines", ["user_id"])
    op.create_table(
        "routine_checkins",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "routine_id",
            sa.Uuid(),
            sa.ForeignKey("routines.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("day", sa.Date(), nullable=False, primary_key=False),
        sa.Column("status", sa.String(16), nullable=False, primary_key=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            primary_key=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            primary_key=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("routine_id", "day", name="uq_routine_checkin_day"),
    )
    op.create_index("ix_routine_checkins_user_id", "routine_checkins", ["user_id"])


def downgrade():
    op.drop_table("routine_checkins")
    op.drop_table("routines")
    op.drop_table("risks")
    op.drop_table("opportunities")
