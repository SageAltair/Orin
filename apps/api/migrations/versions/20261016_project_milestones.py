"""Add project milestones and optional task milestone links."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261016_project_milestones"
down_revision = "20261015_calendar_ai_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_type = sa.Uuid(as_uuid=True).with_variant(postgresql.UUID(as_uuid=True), "postgresql")
    priority_enum = sa.Enum("low", "normal", "high", "urgent", name="project_priority")
    priority_enum.create(op.get_bind(), checkfirst=True)
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("priority", priority_enum, server_default="normal", nullable=False))
        batch_op.add_column(sa.Column("target_date", sa.Date(), nullable=True))
    op.create_table(
        "milestones",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("project_id", uuid_type, nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("completion_criteria", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_milestones_title_nonempty"),
        sa.CheckConstraint("status IN ('pending', 'completed')", name="ck_milestones_status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_milestones_project_target", "milestones", ["project_id", "target_date"])
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("milestone_id", uuid_type, nullable=True))
        batch_op.create_foreign_key("fk_tasks_milestone_id_milestones", "milestones", ["milestone_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_constraint("fk_tasks_milestone_id_milestones", type_="foreignkey")
        batch_op.drop_column("milestone_id")
    op.drop_index("ix_milestones_project_target", table_name="milestones")
    op.drop_table("milestones")
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("target_date")
        batch_op.drop_column("priority")
    sa.Enum(name="project_priority").drop(op.get_bind(), checkfirst=True)
