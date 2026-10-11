"""Add task verification criteria."""

from alembic import op
import sqlalchemy as sa


revision = "20261017_task_verification_criteria"
down_revision = "20261016_project_milestones"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("verification_criteria", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_column("verification_criteria")
