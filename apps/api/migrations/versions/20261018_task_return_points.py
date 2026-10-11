"""Add persistent task return points."""

from alembic import op
import sqlalchemy as sa


revision = "20261018_task_return_points"
down_revision = "20261017_task_verification_criteria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_return_points",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("accomplished", sa.Text(), nullable=True),
        sa.Column("stopped_at", sa.Text(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("references", sa.Text(), nullable=True),
        sa.Column("blocker", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_task_return_points_user_idempotency"),
    )
    op.create_index("ix_task_return_points_task_created", "task_return_points", ["task_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_task_return_points_task_created", table_name="task_return_points")
    op.drop_table("task_return_points")
