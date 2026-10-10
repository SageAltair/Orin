"""Add user-owned calendar events and the Calendar workspace capability."""

import uuid

from alembic import op
import sqlalchemy as sa


revision = "20261013_calendar_foundation"
down_revision = "20261012_focus_behavior"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_all_day", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_calendar_events_title_nonempty"),
        sa.CheckConstraint(
            "(is_all_day = true AND start_date IS NOT NULL AND end_date IS NOT NULL AND start_at IS NULL AND end_at IS NULL) OR "
            "(is_all_day = false AND start_at IS NOT NULL AND end_at IS NOT NULL AND start_date IS NULL AND end_date IS NULL)",
            name="ck_calendar_events_date_shape",
        ),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_calendar_events_date_order"),
        sa.CheckConstraint("end_at IS NULL OR end_at >= start_at", name="ck_calendar_events_time_order"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calendar_events_user_start", "calendar_events", ["user_id", "start_at"])
    op.create_index("ix_calendar_events_user_date", "calendar_events", ["user_id", "start_date"])

    bind = op.get_bind()
    capability_id = uuid.uuid4()
    bind.execute(sa.text(
        "INSERT INTO capabilities (id, code, name, description, is_enabled) "
        "VALUES (:id, 'calendar', 'Calendar', 'See your commitments and plans', true) "
        "ON CONFLICT (code) DO NOTHING"
    ), {"id": str(capability_id)})
    capability_id = bind.execute(sa.text("SELECT id FROM capabilities WHERE code = 'calendar'")).scalar_one()
    for user_id in bind.execute(sa.text("SELECT id FROM users")).scalars():
        bind.execute(sa.text(
            "INSERT INTO user_capabilities (id, user_id, capability_id, granted, visible, pinned, created_at, updated_at) "
            "VALUES (:id, :user_id, :capability_id, true, true, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
        ), {"id": str(uuid.uuid4()), "user_id": user_id, "capability_id": capability_id})


def downgrade() -> None:
    bind = op.get_bind()
    capability_id = bind.execute(sa.text("SELECT id FROM capabilities WHERE code = 'calendar'")).scalar_one_or_none()
    if capability_id is not None:
        bind.execute(sa.text("DELETE FROM user_capabilities WHERE capability_id = :id"), {"id": capability_id})
        bind.execute(sa.text("DELETE FROM capabilities WHERE id = :id"), {"id": capability_id})
    op.drop_index("ix_calendar_events_user_date", table_name="calendar_events")
    op.drop_index("ix_calendar_events_user_start", table_name="calendar_events")
    op.drop_table("calendar_events")
