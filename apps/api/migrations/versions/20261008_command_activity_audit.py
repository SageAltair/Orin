"""Link command-driven activity to its command and intent."""
from alembic import op
import sqlalchemy as sa


revision = "20261008_audit"
down_revision = "a588883a35b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activity", sa.Column("command_id", sa.Uuid(), nullable=True))
    op.add_column("activity", sa.Column("intent", sa.String(length=40), nullable=True))
    op.add_column("activity", sa.Column("result_status", sa.String(length=20), server_default="succeeded", nullable=False))
    op.create_foreign_key("fk_activity_command_id_commands", "activity", "commands", ["command_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_activity_command_id_commands", "activity", type_="foreignkey")
    op.drop_column("activity", "result_status")
    op.drop_column("activity", "intent")
    op.drop_column("activity", "command_id")
