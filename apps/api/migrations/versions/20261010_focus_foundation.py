"""Add focus task state, daily planning, drift, and settings records."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261010_focus_foundation"
down_revision = "20261010_task_batch_activity"
branch_labels = None
depends_on = None


def _enum(name: str, values: tuple[str, ...], dialect: str) -> sa.types.TypeEngine:
    if dialect == "postgresql":
        return postgresql.ENUM(*values, name=name, create_type=False)
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def backfill_task_focus_state(connection: sa.Connection) -> None:
    """Backfill focus state without altering legacy task status or timestamps."""
    if connection.dialect.name == "postgresql":
        statement = """
        UPDATE tasks SET
            focus_state = CASE status
                WHEN 'todo' THEN 'later'::focus_state
                WHEN 'in_progress' THEN 'active'::focus_state
                WHEN 'blocked' THEN 'later'::focus_state
                WHEN 'cancelled' THEN 'released'::focus_state
                ELSE NULL
            END,
            last_touched_at = COALESCE(updated_at, created_at),
            decay_review_at = COALESCE(updated_at, created_at) + INTERVAL '30 days',
            completed_at = CASE WHEN status = 'done' THEN COALESCE(updated_at, created_at) ELSE NULL END,
            released_at = CASE WHEN status = 'cancelled' THEN COALESCE(updated_at, created_at) ELSE NULL END
        """
    else:
        statement = """
        UPDATE tasks SET
            focus_state = CASE status
                WHEN 'todo' THEN 'later'
                WHEN 'in_progress' THEN 'active'
                WHEN 'blocked' THEN 'later'
                WHEN 'cancelled' THEN 'released'
                ELSE NULL
            END,
            last_touched_at = COALESCE(updated_at, created_at),
            decay_review_at = datetime(COALESCE(updated_at, created_at), '+30 days'),
            completed_at = CASE WHEN status = 'done' THEN COALESCE(updated_at, created_at) ELSE NULL END,
            released_at = CASE WHEN status = 'cancelled' THEN COALESCE(updated_at, created_at) ELSE NULL END
        """
    connection.execute(sa.text(statement))


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        for name, values in (
            ("focus_state", ("inbox", "later", "today", "active", "released")),
            ("task_energy_level", ("low", "medium", "high")),
            ("drift_trigger", ("app", "thought", "emotion", "person", "tired", "other")),
            ("daily_energy_level", ("low", "medium", "high")),
            ("user_energy_level", ("low", "medium", "high")),
        ):
            postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.add_column("tasks", sa.Column("focus_state", _enum("focus_state", ("inbox", "later", "today", "active", "released"), dialect), nullable=True))
    op.add_column("tasks", sa.Column("first_step", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("why", sa.String(500), nullable=True))
    op.add_column("tasks", sa.Column("energy_level", _enum("task_energy_level", ("low", "medium", "high"), dialect), nullable=True))
    op.add_column("tasks", sa.Column("estimated_minutes", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("is_anchor", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("tasks", sa.Column("trigger", sa.String(240), nullable=True))
    op.add_column("tasks", sa.Column("last_touched_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("decay_review_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("skip_count_today", sa.Integer(), server_default="0", nullable=False))
    op.add_column("tasks", sa.Column("skip_day_key", sa.String(10), nullable=True))
    op.add_column("tasks", sa.Column("today_day_key", sa.String(10), nullable=True))
    op.add_column("tasks", sa.Column("today_position", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("released_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_tasks_estimated_minutes_positive", "tasks", "estimated_minutes IS NULL OR estimated_minutes > 0")
    op.create_check_constraint("ck_tasks_skip_count_today_range", "tasks", "skip_count_today BETWEEN 0 AND 2")
    backfill_task_focus_state(bind)

    op.add_column("focus_sessions", sa.Column("task_id", sa.Uuid(), nullable=True))
    op.alter_column("focus_sessions", "project_id", existing_type=sa.Uuid(), nullable=True)
    op.create_foreign_key("fk_focus_sessions_task_id_tasks", "focus_sessions", "tasks", ["task_id"], ["id"], ondelete="SET NULL")

    op.create_table("user_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("timezone", sa.String(64), server_default="UTC", nullable=False),
        sa.Column("day_key", sa.String(10), nullable=True),
        sa.Column("energy_today", _enum("user_energy_level", ("low", "medium", "high"), dialect), nullable=True),
        sa.Column("preferred_anchor_time", sa.String(5), nullable=True),
        sa.Column("quiet_hours", sa.JSON(), nullable=True),
        sa.Column("reduced_motion", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("sound_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("haptics_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("theme", sa.String(8), server_default="auto", nullable=False),
        sa.Column("body_doubling_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("accountability_contact", sa.String(240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("user_id"))

    op.create_table("daily_plans",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("day_key", sa.String(10), nullable=False),
        sa.Column("energy_level", _enum("daily_energy_level", ("low", "medium", "high"), dialect), nullable=True),
        sa.Column("swapped_task_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "day_key", name="uq_daily_plans_user_day"))
    op.create_table("daily_plan_tasks",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False), sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False), sa.Column("is_anchor", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["daily_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "task_id", name="uq_daily_plan_task"),
        sa.UniqueConstraint("plan_id", "position", name="uq_daily_plan_position"))
    op.create_table("daily_closes",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("day_key", sa.String(10), nullable=False), sa.Column("done_list", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("drift_summary", sa.Text(), nullable=True), sa.Column("tomorrow_task_id", sa.Uuid(), nullable=True),
        sa.Column("reflection", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tomorrow_task_id"], ["tasks.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "day_key", name="uq_daily_closes_user_day"))
    op.create_table("drift_events",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True), sa.Column("focus_session_id", sa.Uuid(), nullable=True),
        sa.Column("day_key", sa.String(10), nullable=False),
        sa.Column("trigger_type", _enum("drift_trigger", ("app", "thought", "emotion", "person", "tired", "other"), dialect), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["focus_session_id"], ["focus_sessions.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_drift_events_user_created", "drift_events", ["user_id", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("ix_drift_events_user_created", table_name="drift_events")
    op.drop_table("drift_events")
    op.drop_table("daily_closes")
    op.drop_table("daily_plan_tasks")
    op.drop_table("daily_plans")
    op.drop_table("user_settings")
    op.drop_constraint("fk_focus_sessions_task_id_tasks", "focus_sessions", type_="foreignkey")
    op.drop_column("focus_sessions", "task_id")
    op.alter_column("focus_sessions", "project_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_constraint("ck_tasks_skip_count_today_range", "tasks", type_="check")
    op.drop_constraint("ck_tasks_estimated_minutes_positive", "tasks", type_="check")
    for column in ("focus_state", "first_step", "why", "energy_level", "estimated_minutes", "is_anchor", "trigger", "last_touched_at", "decay_review_at", "skip_count_today", "skip_day_key", "today_day_key", "today_position", "completed_at", "released_at"):
        op.drop_column("tasks", column)
    if bind.dialect.name == "postgresql":
        for name in ("drift_trigger", "user_energy_level", "daily_energy_level", "task_energy_level", "focus_state"):
            postgresql.ENUM(name=name).drop(bind, checkfirst=True)
